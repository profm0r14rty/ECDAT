"""Pytest tests for the Redis-backed job status and background scan layer.

Uses ``fakeredis`` for an in-memory Redis emulation so tests pass without a
local Redis server, and a throwaway SQLite engine for the ScanRun rows.
"""

from __future__ import annotations

import os
import tempfile
from typing import Iterator

import fakeredis
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.jobs import get_job_status, set_job_status, run_scan_job
from backend.app.models_orm import Base, ScanRun, ScanStatus, SourceType
from ecdat_core.models import Detection, RiskAssessment, Recommendation, ScanResult


@pytest.fixture
def redis_client() -> Iterator[fakeredis.FakeRedis]:
    """Yield a fakeredis client preconfigured with decode_responses=True."""
    server = fakeredis.FakeServer()
    client = fakeredis.FakeRedis(server=server, decode_responses=True)
    yield client


def _use_redis(monkeypatch, client) -> None:
    """Point jobs._get_redis at a caller-supplied client."""
    import backend.app.jobs as jobs

    monkeypatch.setattr(jobs, "_get_redis", lambda: client)


@pytest.fixture
def patch_redis(monkeypatch, redis_client):
    """Application of _use_redis for tests that only exercise status helpers."""
    _use_redis(monkeypatch, redis_client)
    return redis_client


@pytest.fixture
def job_db(monkeypatch) -> Iterator[str]:
    """Yield a scan id whose ScanRun row lives in a throwaway SQLite DB."""
    import backend.app.jobs as jobs

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    if os.path.exists(tmp.name):
        os.unlink(tmp.name)

    engine = create_engine(f"sqlite:///{tmp.name}", future=True, echo=False)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        autocommit=False, autoflush=False, bind=engine, future=True
    )
    session = session_factory()

    monkeypatch.setattr(jobs, "_new_session", session_factory)

    scan_id = "test-scan-001"
    scan_run = ScanRun(
        id=scan_id,
        target="/test/path",
        source_type=SourceType.local_path,
        status=ScanStatus.queued,
    )
    session.add(scan_run)
    session.commit()
    session.close()

    try:
        yield scan_id
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)


def _make_scan_result(scan_id: str, files_scanned: int = 4) -> ScanResult:
    """Build a small ScanResult suitable for persistence assertions."""
    det = Detection(
        file_path="/src/demo.py",
        line_number=1,
        matched_text="crypto_key",
        asset_type="algorithm",
        algorithm_family="AES",
        key_size_bits=256,
        quantum_vulnerable=False,
        classically_broken=False,
        confidence=0.95,
        language="Python",
        detection_method="regex",
    )
    ra = RiskAssessment(
        detection_id=det.id,
        migration_time_years=1.0,
        shelf_life_years=2.0,
        threat_horizon_years=5.0,
        urgency_ratio=0.6,
        risk_level="quantum-safe",
        mosca_violation=False,
    )
    rec = Recommendation(
        detection_id=det.id,
        recommended_algorithm="ML-KEM-512",
        fips_reference="FIPS 203",
        rationale="Migration to post-quantum KEM",
        latency_note="~2x overhead",
        migration_note="Moderate effort",
    )
    return ScanResult(
        scan_id=scan_id,
        target="/test/path",
        detections=[det],
        risk_assessments=[ra],
        recommendations=[rec],
        scanned_at="2026-01-01T00:00:00Z",
        files_scanned=files_scanned,
    )


def test_set_and_get_job_status_roundtrip(patch_redis):
    """set_job_status then get_job_status returns the same value."""
    set_job_status("s1", "queued")
    assert get_job_status("s1") == "queued"


def test_job_status_ttl_is_24h(patch_redis):
    """set_job_status writes ex=86400 so the key expires in 24h."""
    set_job_status("s-ttl", "running")
    assert patch_redis.ttl("scan:s-ttl:status") == 86400


def test_get_job_status_missing_returns_none(patch_redis):
    """get_job_status returns None when the key does not exist."""
    assert get_job_status("no-such-scan") is None


def test_set_get_job_key_pattern(patch_redis):
    """Status is stored under the scan:{scan_id}:status key pattern."""
    set_job_status("abc", "running")
    assert patch_redis.get("scan:abc:status") == "running"


def test_run_scan_job_queued_running_done(redis_client, job_db, monkeypatch):
    """run_scan_job transitions queued -> running -> done and persists on success."""
    import backend.app.jobs as jobs

    _use_redis(monkeypatch, redis_client)
    result = _make_scan_result(scan_id=job_db, files_scanned=4)
    monkeypatch.setattr(jobs, "ecdat_run_scan", lambda target, is_git_url: result)

    run_scan_job(scan_id=job_db, target="/test/path", source_type="local_path")

    assert get_job_status(job_db) == "done"
    assert redis_client.get(f"scan:{job_db}:status") == "done"

    session = jobs._new_session()
    try:
        refreshed = session.get(ScanRun, job_db)
        assert refreshed is not None
        assert refreshed.status == "done"
        assert refreshed.files_scanned == 4
        assert refreshed.completed_at is not None
    finally:
        session.close()


def test_run_scan_job_records_running_then_done_sequence(
    redis_client, job_db, monkeypatch
):
    """Both 'running' and 'done' are recorded in Redis in order."""
    import backend.app.jobs as jobs

    _use_redis(monkeypatch, redis_client)
    result = _make_scan_result(scan_id=job_db)
    monkeypatch.setattr(jobs, "ecdat_run_scan", lambda target, is_git_url: result)

    run_scan_job(scan_id=job_db, target="/test/path", source_type="local_path")

    assert redis_client.get(f"scan:{job_db}:status") == "done"


def test_run_scan_job_queued_running_failed_on_exception(
    redis_client, job_db, monkeypatch
):
    """run_scan_job transitions queued -> running -> failed on a forced exception."""
    import backend.app.jobs as jobs

    _use_redis(monkeypatch, redis_client)

    def boom(target, is_git_url):
        del target, is_git_url
        raise RuntimeError("Simulated scan failure")

    monkeypatch.setattr(jobs, "ecdat_run_scan", boom)

    run_scan_job(scan_id=job_db, target="/test/path", source_type="local_path")

    assert get_job_status(job_db) == "failed"
    assert redis_client.get(f"scan:{job_db}:status") == "failed"


def test_run_scan_job_fails_fast_when_redis_down(job_db, monkeypatch):
    """When Redis is unreachable at start, the job fails clearly and early."""
    import backend.app.jobs as jobs

    def no_redis():
        raise RuntimeError("Cannot connect to Redis at redis://localhost:6379/0")

    monkeypatch.setattr(jobs, "_get_redis", no_redis)

    run_scan_job(scan_id=job_db, target="/test/path", source_type="local_path")

    session = jobs._new_session()
    try:
        refreshed = session.get(ScanRun, job_db)
        assert refreshed is not None
        assert refreshed.status == "failed"
        assert "Cannot connect to Redis" in refreshed.error_message
    finally:
        session.close()