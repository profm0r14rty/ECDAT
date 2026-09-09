"""API tests for scan creation, listing, and status/summary endpoints.

Uses a throwaway SQLite database (dependency override + patched job session
factory) and fakeredis in place of a real Redis server. The scan itself runs
for real against the ``ecdat_core`` demo_repo fixture via the FastAPI
background task machinery.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Iterator

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.app.jobs as jobs
from backend.app.db import Base, get_db
from backend.app.main import app

# ecdat_core/tests/fixtures/demo_repo — the planted-vulnerability fixture.
DEMO_REPO = Path(__file__).resolve().parents[2] / "ecdat_core" / "tests" / "fixtures" / "demo_repo"


@pytest.fixture
def client(monkeypatch) -> Iterator[TestClient]:
    """TestClient wired to a throwaway SQLite DB with fakeredis.

    Patches:

    - ``jobs._new_session`` so the background ``run_scan_job`` writes to the
      same throwaway engine the API's ``get_db`` dependency serves.
    - ``jobs._get_redis`` so status transitions use fakeredis instead of a
      real Redis server.
    - ``app.dependency_overrides[get_db]`` so API requests read from the
      throwaway engine rather than the module-level default database.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    if os.path.exists(db_path):
        os.unlink(db_path)

    engine = create_engine(
        f"sqlite:///{db_path}",
        future=True,
        echo=False,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        autocommit=False, autoflush=False, bind=engine, future=True
    )

    server = fakeredis.FakeServer()
    redis_client = fakeredis.FakeRedis(server=server, decode_responses=True)

    monkeypatch.setattr(jobs, "_new_session", session_factory)
    monkeypatch.setattr(jobs, "_get_redis", lambda: redis_client)

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        if os.path.exists(db_path):
            os.unlink(db_path)


def _wait_for_done(
    client: TestClient, scan_id: str, timeout: float = 30.0
) -> dict:
    """Poll GET /api/scans/{scan_id} until status is 'done' or timeout hits.

    Fails the test clearly on timeout or on a terminal 'failed' status
    (including the recorded error message) so the test never hangs forever.
    """
    deadline = time.monotonic() + timeout
    while True:
        response = client.get(f"/api/scans/{scan_id}")
        assert response.status_code == 200, (
            f"GET /api/scans/{scan_id} returned {response.status_code}"
        )
        body = response.json()
        if body["status"] == "done":
            return body
        if body["status"] == "failed":
            pytest.fail(
                f"scan {scan_id} failed: {body.get('error_message')!r}"
            )
        if time.monotonic() >= deadline:
            pytest.fail(
                f"scan {scan_id} did not reach 'done' within {timeout}s; "
                f"last status: {body['status']!r}"
            )
        time.sleep(0.05)


def test_create_scan_returns_202_and_done_summary_matches_fixture(client):
    """POST a local_path scan of demo_repo and assert the final summary.

    Expected numbers come from the Fix Batch's corrected detector/risk-engine
    output for this fixture: 4 files scanned, 17 detections, 7 critical
    (RSA-1024 + MD5 x5 + DES), 10 quantum-safe, 1 quantum-vulnerable.
    """
    response = client.post(
        "/api/scans",
        json={"source_type": "local_path", "target": str(DEMO_REPO)},
    )
    assert response.status_code == 202
    created = response.json()
    assert set(created) == {"id", "status"}
    assert created["status"] == "queued"
    scan_id = created["id"]
    assert scan_id

    detail = _wait_for_done(client, scan_id)

    assert detail["id"] == scan_id
    assert detail["target"] == str(DEMO_REPO)
    assert detail["source_type"] == "local_path"
    assert detail["status"] == "done"
    assert detail["files_scanned"] == 4
    assert detail["created_at"] is not None
    assert detail["completed_at"] is not None
    assert detail["error_message"] is None

    summary = detail["summary"]
    assert summary is not None
    assert summary["total_detections"] == 17
    assert summary["quantum_vulnerable_count"] == 1
    assert summary["quantum_vulnerable_percentage"] == pytest.approx(
        100.0 / 17, abs=0.01
    )
    assert summary["risk_level_counts"] == {
        "critical": 7,
        "high": 0,
        "medium": 0,
        "low": 0,
        "quantum-safe": 10,
    }
    assert summary["algorithm_family_counts"] == {
        "RSA": 1,
        "AES": 6,
        "MD5": 5,
        "DES": 1,
        "ML-KEM": 4,
    }
    assert sum(summary["risk_level_counts"].values()) == summary["total_detections"]

    top_5 = summary["top_5_urgency"]
    assert len(top_5) == 5
    # Top urgency is the five MD5 finds: critical, urgency 5.5, sorted desc.
    assert all(item["risk_level"] == "critical" for item in top_5)
    assert all(item["algorithm_family"] == "MD5" for item in top_5)
    assert all(item["urgency_ratio"] == pytest.approx(5.5) for item in top_5)
    assert [item["urgency_ratio"] for item in top_5] == sorted(
        (item["urgency_ratio"] for item in top_5), reverse=True
    )
    assert all(item["file_path"].endswith("demo_repo/utils/hasher.py") for item in top_5)


def test_create_scan_rejects_invalid_source_type(client):
    """POST /api/scans with a bad source_type must be a 422."""
    response = client.post(
        "/api/scans",
        json={"source_type": "tarball", "target": str(DEMO_REPO)},
    )
    assert response.status_code == 422


def test_list_scans_returns_scan_most_recent_first(client):
    """GET /api/scans lists the completed scan with its key fields."""
    scan_id = client.post(
        "/api/scans",
        json={"source_type": "local_path", "target": str(DEMO_REPO)},
    ).json()["id"]
    _wait_for_done(client, scan_id)

    response = client.get("/api/scans")
    assert response.status_code == 200
    items = response.json()
    assert items, "expected at least one scan run in the list"
    # Newest first — our just-created scan must be the first entry.
    assert items[0]["id"] == scan_id

    item = items[0]
    assert item["target"] == str(DEMO_REPO)
    assert item["source_type"] == "local_path"
    assert item["status"] == "done"
    assert item["files_scanned"] == 4
    assert item["created_at"] is not None
    assert item["completed_at"] is not None
    assert set(item) == {
        "id",
        "target",
        "source_type",
        "status",
        "created_at",
        "completed_at",
        "files_scanned",
    }


def test_get_scan_unknown_id_returns_404(client):
    """GET /api/scans/{bad-id} must return 404 for a nonexistent scan."""
    response = client.get("/api/scans/does-not-exist")
    assert response.status_code == 404