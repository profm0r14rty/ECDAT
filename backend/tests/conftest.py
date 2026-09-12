"""Shared fixtures and helpers for backend API tests.

Provides:

- A ``db_session_factory`` fixture: a throwaway SQLite engine/sessionmaker
  with ``jobs._new_session`` and ``jobs._get_redis`` patched so background
  scan jobs and status tracking run against the same DB and a fakeredis.
- A ``client`` fixture: ``fastapi.testclient.TestClient`` wired to that
  throwaway DB via ``app.dependency_overrides[get_db]``.
- :func:`wait_for_scan_done` — poll ``GET /api/scans/{id}`` until ``done``.
"""
import os
import sys
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

# Ensure the backend package is importable regardless of CWD.
_backend_path = str(Path(__file__).parent.parent / "backend")
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)

# ecdat_core/tests/fixtures/demo_repo — the planted-vulnerability fixture.
DEMO_REPO = (
    Path(__file__).resolve().parents[2]
    / "ecdat_core"
    / "tests"
    / "fixtures"
    / "demo_repo"
)


@pytest.fixture
def db_session_factory(monkeypatch) -> Iterator[sessionmaker]:
    """Throwaway SQLite session factory with jobs + Redis patched.

    Patches:

    - ``jobs._new_session`` so the background ``run_scan_job`` writes to the
      same throwaway engine the API's ``get_db`` dependency serves.
    - ``jobs._get_redis`` so status transitions use fakeredis instead of a
      real Redis server.

    Yields:
        A sessionmaker bound to the throwaway SQLite engine, cleaned up (and
        the temp DB file deleted) when the test ends.
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
    factory = sessionmaker(
        autocommit=False, autoflush=False, bind=engine, future=True
    )

    server = fakeredis.FakeServer()
    redis_client = fakeredis.FakeRedis(server=server, decode_responses=True)

    monkeypatch.setattr(jobs, "_new_session", factory)
    monkeypatch.setattr(jobs, "_get_redis", lambda: redis_client)

    try:
        yield factory
    finally:
        engine.dispose()
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.fixture(autouse=True)
def _reset_rate_limiter_storage() -> Iterator[None]:
    """Reset the process-wide slowapi rate-limit storage before every test.

    The :class:`slowapi.Limiter` (Phase 47) is module-global and its memory
    storage persists across requests on the same app instance. Without this,
    one test's bucket consumption — e.g. the 429-trigger tests exhausting
    ``2/minute`` — would leak into the next test, and the whole suite firing
    POSTs under the default ``10/hour`` would trip spurious 429s.
    ``Limiter.reset()`` is a logged no-op on storage backends that cannot
    reset; our default ``memory://`` backend can.
    """
    limiter = getattr(app.state, "limiter", None)
    if limiter is not None:
        limiter.reset()
    yield


@pytest.fixture
def client(db_session_factory) -> Iterator[TestClient]:
    """TestClient wired to the throwaway SQLite DB.

    Depends on :func:`db_session_factory` and overrides ``get_db`` so every
    API request reads from the same throwaway engine the background job uses.
    """
    def override_get_db():
        session = db_session_factory()
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


def wait_for_scan_done(
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