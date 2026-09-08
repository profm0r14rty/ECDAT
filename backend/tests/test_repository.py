"""Pytest tests for the backend repository layer.

Tests the translation layer between ecdat_core Pydantic models and
SQLAlchemy ORM rows, using a throwaway SQLite database.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from typing import Generator

import pytest

from ecdat_core.models import Detection, RiskAssessment, Recommendation, ScanResult


# ---------------------------------------------------------------------------
# Session helper: create a throwaway SQLite session
# ---------------------------------------------------------------------------

def _make_temp_session():
    """Create a temporary SQLite session for testing.

    Yields a SQLAlchemy Session pointing at a throwaway SQLite file.
    After the test, the file is deleted and all state is cleaned up.
    """
    # Use a temporary sqlite file per test to avoid cross-test interference
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    tmp_path = tmp.name

    # Remove if leftover
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{tmp_path}", future=True, echo=False)

    from backend.app.db import Base
    from backend.app.models_orm import DetectionRow, RiskAssessmentRow, RecommendationRow, ScanRun, ScanStatus, SourceType

    Base.metadata.create_all(engine)

    session_factory = sessionmaker(
        autocommit=False, autoflush=False, bind=engine, future=True
    )
    session = session_factory()

    yield session

    session.close()
    # Clean up temp file
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Helpers: build small hand-crafted model instances
# ---------------------------------------------------------------------------

def _make_detection(index: int) -> Detection:
    return Detection(
        file_path=f"/src/file{index}.py",
        line_number=10 + index,
        matched_text=f"crypto_key_{index}",
        asset_type="algorithm",
        algorithm_family=["RSA", "AES", "SHA-256"][index],
        key_size_bits=[2048, 256, None][index],
        quantum_vulnerable=[True, True, False][index],
        classically_broken=[False, False, True][index],
        confidence=0.95,
        language="Python",
        detection_method="regex",
    )


def _make_risk_assessment(detection_id: str) -> RiskAssessment:
    return RiskAssessment(
        detection_id=detection_id,
        migration_time_years=2.0,
        shelf_life_years=5.0,
        threat_horizon_years=10.0,
        urgency_ratio=0.6,
        risk_level="medium",
        mosca_violation=False,
    )


def _make_recommendation(detection_id: str) -> Recommendation:
    return Recommendation(
        detection_id=detection_id,
        recommended_algorithm="ML-KEM-512",
        fips_reference="FIPS 203",
        rationale="Post-quantum replacement for RSA",
        latency_note="~2x overhead",
        migration_note="Moderate effort",
    )


# ---------------------------------------------------------------------------
# Tests (each test manages its own session via _make_temp_session)
# ---------------------------------------------------------------------------

def test_create_scan_run_queued():
    """create_scan_run should set status='queued'."""
    from backend.app.repository import create_scan_run

    session = next(_make_temp_session())
    try:
        scan_run = create_scan_run(session, target="/some/path", source_type="local_path")
        assert scan_run.target == "/some/path"
        assert scan_run.source_type.value == "local_path"
        assert scan_run.status == "queued"
    finally:
        session.close()


def test_mark_scan_running():
    """mark_scan_running should set status='running'."""
    from backend.app.repository import create_scan_run, mark_scan_running

    session = next(_make_temp_session())
    try:
        scan_run = create_scan_run(session, target="/some/path", source_type="local_path")
        mark_scan_running(session, scan_run.id)
        refreshed = session.get(type(scan_run), scan_run.id)  # type: ignore
        assert refreshed.status == "running"
    finally:
        session.close()


def test_mark_scan_done():
    """mark_scan_done should set status='done' and files_scanned."""
    from backend.app.repository import create_scan_run, mark_scan_done

    session = next(_make_temp_session())
    try:
        scan_run = create_scan_run(session, target="/some/path", source_type="local_path")
        mark_scan_done(session, scan_run.id, files_scanned=42)
        refreshed = session.get(type(scan_run), scan_run.id)  # type: ignore
        assert refreshed.status == "done"
        assert refreshed.files_scanned == 42
        assert refreshed.completed_at is not None
    finally:
        session.close()


def test_mark_scan_failed():
    """mark_scan_failed should set status='failed' and error_message."""
    from backend.app.repository import create_scan_run, mark_scan_failed

    session = next(_make_temp_session())
    try:
        scan_run = create_scan_run(session, target="/some/path", source_type="local_path")
        mark_scan_failed(session, scan_run.id, error_message="something went wrong")
        refreshed = session.get(type(scan_run), scan_run.id)  # type: ignore
        assert refreshed.status == "failed"
        assert refreshed.error_message == "something went wrong"
        assert refreshed.completed_at is not None
    finally:
        session.close()


def test_persist_scan_result_basic():
    """persist_scan_result should write Detection, RiskAssessment, Recommendation rows."""
    from backend.app.repository import persist_scan_result

    session = next(_make_temp_session())
    try:
        from backend.app.repository import create_scan_run
        scan_run = create_scan_run(session, target="/some/path", source_type="local_path")

        # Build a small ScanResult with 2 detections
        det1 = _make_detection(0)
        det2 = _make_detection(1)
        ra1 = _make_risk_assessment(det1.id)
        ra2 = _make_risk_assessment(det2.id)
        rec1 = _make_recommendation(det1.id)
        rec2 = _make_recommendation(det2.id)

        scan_result = ScanResult(
            scan_id=scan_run.id,
            target="/some/path",
            detections=[det1, det2],
            risk_assessments=[ra1, ra2],
            recommendations=[rec1, rec2],
            scanned_at="2026-01-01T00:00:00Z",
            files_scanned=2,
        )

        persist_scan_result(session, scan_run.id, scan_result)

        # Verify detections were persisted
        from backend.app.models_orm import DetectionRow
        det_rows = session.query(DetectionRow).filter(
            DetectionRow.scan_id == scan_run.id
        ).all()
        assert len(det_rows) == 2, f"Expected 2 detection rows, got {len(det_rows)}"

        # Verify risk assessments were persisted
        from backend.app.models_orm import RiskAssessmentRow
        risk_rows = session.query(RiskAssessmentRow).all()
        assert len(risk_rows) == 2, f"Expected 2 risk assessment rows, got {len(risk_rows)}"

        # Verify recommendations were persisted
        from backend.app.models_orm import RecommendationRow
        rec_rows = session.query(RecommendationRow).all()
        assert len(rec_rows) == 2, f"Expected 2 recommendation rows, got {len(rec_rows)}"
    finally:
        session.close()


def test_persist_scan_result_update_overwrite():
    """persist_scan_result should overwrite existing rows (no duplication)."""
    from backend.app.repository import persist_scan_result, update_risk_assessment

    session = next(_make_temp_session())
    try:
        from backend.app.repository import create_scan_run
        scan_run = create_scan_run(session, target="/some/path", source_type="local_path")

        # First persistence
        det1 = _make_detection(0)
        ra1 = _make_risk_assessment(det1.id)
        rec1 = _make_recommendation(det1.id)

        scan_result1 = ScanResult(
            scan_id=scan_run.id,
            target="/some/path",
            detections=[det1],
            risk_assessments=[ra1],
            recommendations=[rec1],
            scanned_at="2026-01-01T00:00:00Z",
            files_scanned=1,
        )

        persist_scan_result(session, scan_run.id, scan_result1)

        # Second persistence with different data (simulating a re-scan)
        # Reuse the same detection object, just modify in-place
        det1.algorithm_family = "SHA-256"

        ra1_updated = _make_risk_assessment(det1.id)
        ra1_updated.risk_level = "high"
        ra1_updated.urgency_ratio = 0.9

        rec1_updated = _make_recommendation(det1.id)
        rec1_updated.recommended_algorithm = "ML-DSA-65"

        scan_result2 = ScanResult(
            scan_id=scan_run.id,
            target="/some/path",
            detections=[det1],
            risk_assessments=[ra1_updated],
            recommendations=[rec1_updated],
            scanned_at="2026-01-02T00:00:00Z",
            files_scanned=1,
        )

        persist_scan_result(session, scan_run.id, scan_result2)

        # Verify only ONE detection row exists (not duplicated)
        from backend.app.models_orm import DetectionRow, RiskAssessmentRow, RecommendationRow
        det_rows = session.query(DetectionRow).filter(
            DetectionRow.scan_id == scan_run.id
        ).all()
        assert len(det_rows) == 1, f"Expected 1 detection row, got {len(det_rows)}"

        # Verify risk assessment was overwritten, not duplicated
        risk_rows = session.query(RiskAssessmentRow).all()
        assert len(risk_rows) == 1, f"Expected 1 risk assessment row, got {len(risk_rows)}"
        assert risk_rows[0].risk_level == "high"
        assert risk_rows[0].urgency_ratio == 0.9

        # Verify recommendation was overwritten
        rec_rows = session.query(RecommendationRow).all()
        assert len(rec_rows) == 1, f"Expected 1 recommendation row, got {len(rec_rows)}"
        assert rec_rows[0].recommended_algorithm == "ML-DSA-65"
    finally:
        session.close()


def test_get_scan_run():
    """get_scan_run should return the ScanRun or None."""
    from backend.app.repository import create_scan_run, get_scan_run

    session = next(_make_temp_session())
    try:
        scan_run = create_scan_run(session, target="/some/path", source_type="local_path")
        retrieved = get_scan_run(session, scan_run.id)
        assert retrieved is not None
        assert retrieved.target == "/some/path"

        # Non-existent ID
        missing = get_scan_run(session, "non-existent-id")
        assert missing is None
    finally:
        session.close()


def test_list_scan_runs():
    """list_scan_runs should return scan runs ordered by created_at desc."""
    from backend.app.repository import create_scan_run, list_scan_runs

    session = next(_make_temp_session())
    try:
        r1 = create_scan_run(session, target="/path1", source_type="local_path")
        r2 = create_scan_run(session, target="/path2", source_type="git_url")
        r3 = create_scan_run(session, target="/path3", source_type="local_path")

        runs = list_scan_runs(session, limit=50)
        assert len(runs) >= 3
        # Should be ordered newest first (by created_at desc)
        assert runs[0].target == "/path3"  # most recently created
    finally:
        session.close()


def test_get_detections_pagination():
    """get_detections should return paginated results with correct count."""
    from backend.app.repository import create_scan_run, get_detections, persist_scan_result
    from backend.app.models_orm import DetectionRow, RiskAssessmentRow

    session = next(_make_temp_session())
    try:
        scan_run = create_scan_run(session, target="/some/path", source_type="local_path")

        # Persist 3 detections with risk assessments using ORM rows
        for i in range(3):
            det_row = DetectionRow(
                scan_id=scan_run.id,
                id=f"det-{i}",
                file_path=f"/src/file{i}.py",
                line_number=10 + i,
                matched_text=f"crypto_key_{i}",
                asset_type="algorithm",
                algorithm_family=["RSA", "AES", "SHA-256"][i],
                key_size_bits=[2048, 256, None][i],
                quantum_vulnerable=[True, True, False][i],
                classically_broken=[False, False, True][i],
                confidence=0.95,
                language="Python",
                detection_method="regex",
            )
            ra_row = RiskAssessmentRow(
                detection_id=det_row.id,
                migration_time_years=2.0,
                shelf_life_years=5.0,
                threat_horizon_years=10.0,
                urgency_ratio=0.6,
                risk_level="medium",
                mosca_violation=False,
            )
            session.add_all([det_row, ra_row])

        session.commit()

        # Page 1, page_size=2
        rows, total = get_detections(session, scan_run.id, page=1, page_size=2)
        assert total == 3
        assert len(rows) == 2

        # Page 2, page_size=2
        rows2, total2 = get_detections(session, scan_run.id, page=2, page_size=2)
        assert total2 == 3
        assert len(rows2) == 1
    finally:
        session.close()


def test_get_detections_filter_by_risk_level():
    """get_detections should filter by risk_level via join with risk_assessments."""
    from backend.app.repository import create_scan_run, get_detections
    from backend.app.models_orm import DetectionRow, RiskAssessmentRow, RiskLevel

    session = next(_make_temp_session())
    try:
        scan_run = create_scan_run(session, target="/some/path", source_type="local_path")

        # Create 2 detection rows
        det1 = DetectionRow(
            scan_id=scan_run.id,
            id="det-1",
            file_path="/src/file1.py",
            line_number=10,
            matched_text="crypto_key_1",
            asset_type="algorithm",
            algorithm_family="RSA",
            key_size_bits=2048,
            quantum_vulnerable=True,
            classically_broken=False,
            confidence=0.95,
            language="Python",
            detection_method="regex",
        )
        det2 = DetectionRow(
            scan_id=scan_run.id,
            id="det-2",
            file_path="/src/file2.py",
            line_number=11,
            matched_text="crypto_key_2",
            asset_type="algorithm",
            algorithm_family="AES",
            key_size_bits=256,
            quantum_vulnerable=False,
            classically_broken=False,
            confidence=0.95,
            language="Python",
            detection_method="regex",
        )
        session.add_all([det1, det2])
        session.commit()

        # Build risk assessments with different levels
        ra1 = RiskAssessmentRow(
            detection_id=det1.id,
            migration_time_years=1.0,
            shelf_life_years=2.0,
            threat_horizon_years=5.0,
            urgency_ratio=1.5,
            risk_level="critical",
            mosca_violation=True,
        )
        ra2 = RiskAssessmentRow(
            detection_id=det2.id,
            migration_time_years=0.5,
            shelf_life_years=1.0,
            threat_horizon_years=5.0,
            urgency_ratio=0.3,
            risk_level="quantum-safe",
            mosca_violation=False,
        )
        session.add_all([ra1, ra2])
        session.commit()

        # Filter by "critical" risk level
        rows, total = get_detections(session, scan_run.id, risk_level="critical")
        assert total == 1
        assert rows[0].id == det1.id

        # Filter by "quantum-safe"
        rows2, total2 = get_detections(session, scan_run.id, risk_level="quantum-safe")
        assert total2 == 1
        assert rows2[0].id == det2.id
    finally:
        session.close()


def test_get_detections_filter_by_algorithm_family():
    """get_detections should filter by algorithm_family."""
    from backend.app.repository import create_scan_run, get_detections
    from backend.app.models_orm import DetectionRow, RiskAssessmentRow, RiskLevel

    session = next(_make_temp_session())
    try:
        scan_run = create_scan_run(session, target="/some/path", source_type="local_path")

        # Create 2 detection rows with different algorithm families
        det1 = DetectionRow(
            scan_id=scan_run.id,
            id="det-1",
            file_path="/src/file1.py",
            line_number=10,
            matched_text="crypto_key_1",
            asset_type="algorithm",
            algorithm_family="RSA",
            key_size_bits=2048,
            quantum_vulnerable=True,
            classically_broken=False,
            confidence=0.95,
            language="Python",
            detection_method="regex",
        )
        det2 = DetectionRow(
            scan_id=scan_run.id,
            id="det-2",
            file_path="/src/file2.py",
            line_number=11,
            matched_text="crypto_key_2",
            asset_type="algorithm",
            algorithm_family="AES",
            key_size_bits=256,
            quantum_vulnerable=False,
            classically_broken=False,
            confidence=0.95,
            language="Python",
            detection_method="regex",
        )
        session.add_all([det1, det2])
        session.commit()

        # Build risk assessments
        ra1 = RiskAssessmentRow(
            detection_id=det1.id,
            migration_time_years=1.0,
            shelf_life_years=2.0,
            threat_horizon_years=5.0,
            urgency_ratio=1.5,
            risk_level="critical",
            mosca_violation=True,
        )
        ra2 = RiskAssessmentRow(
            detection_id=det2.id,
            migration_time_years=0.5,
            shelf_life_years=1.0,
            threat_horizon_years=5.0,
            urgency_ratio=0.3,
            risk_level="quantum-safe",
            mosca_violation=False,
        )
        session.add_all([ra1, ra2])
        session.commit()

        # Filter by algorithm_family="RSA"
        rows, total = get_detections(session, scan_run.id, algorithm_family="RSA")
        assert total == 1
        assert rows[0].algorithm_family == "RSA"
    finally:
        session.close()


def test_get_detection_with_risk_and_recommendation():
    """get_detection_with_risk_and_recommendation should return all three rows or None."""
    from backend.app.repository import create_scan_run, get_detection_with_risk_and_recommendation
    from backend.app.models_orm import DetectionRow, RiskAssessmentRow, RecommendationRow

    session = next(_make_temp_session())
    try:
        scan_run = create_scan_run(session, target="/some/path", source_type="local_path")

        # Create all three ORM rows directly
        det = DetectionRow(
            scan_id=scan_run.id,
            id="det-1",
            file_path="/src/file1.py",
            line_number=10,
            matched_text="crypto_key_1",
            asset_type="algorithm",
            algorithm_family="RSA",
            key_size_bits=2048,
            quantum_vulnerable=True,
            classically_broken=False,
            confidence=0.95,
            language="Python",
            detection_method="regex",
        )
        ra = RiskAssessmentRow(
            detection_id=det.id,
            migration_time_years=1.0,
            shelf_life_years=2.0,
            threat_horizon_years=5.0,
            urgency_ratio=0.6,
            risk_level="medium",
            mosca_violation=False,
        )
        rec = RecommendationRow(
            detection_id=det.id,
            recommended_algorithm="ML-KEM-512",
            fips_reference="FIPS 203",
            rationale="Post-quantum replacement for RSA",
            latency_note="~2x overhead",
            migration_note="Moderate effort",
        )
        session.add_all([det, ra, rec])
        session.commit()

        # Should find all three
        result = get_detection_with_risk_and_recommendation(session, det.id)
        assert result is not None
        detection, risk, recommendation = result
        assert detection.id == det.id
        assert risk.detection_id == ra.detection_id
        assert recommendation.detection_id == rec.detection_id

        # Non-existent detection_id
        missing = get_detection_with_risk_and_recommendation(session, "non-existent-id")
        assert missing is None
    finally:
        session.close()


def test_update_risk_assessment_overwrite():
    """update_risk_assessment should overwrite the existing row rather than duplicating."""
    from backend.app.repository import create_scan_run, persist_scan_result, update_risk_assessment

    session = next(_make_temp_session())
    try:
        scan_run = create_scan_run(session, target="/some/path", source_type="local_path")

        det = _make_detection(0)
        # First risk assessment
        from backend.app.models_orm import RiskAssessmentRow

        ra_first = RiskAssessmentRow(
            detection_id=det.id,
            migration_time_years=1.0,
            shelf_life_years=2.0,
            threat_horizon_years=5.0,
            urgency_ratio=0.5,
            risk_level="medium",
            mosca_violation=False,
        )
        session.add(ra_first)
        session.commit()

        # Now update it - use urgency_ratio=1.2 with mosca_violation=True
        from ecdat_core.models import RiskAssessment

        ra_update = RiskAssessment(
            detection_id=det.id,
            migration_time_years=3.0,
            shelf_life_years=7.0,
            threat_horizon_years=12.0,
            urgency_ratio=1.2,
            risk_level="high",
            mosca_violation=True,
        )

        updated = update_risk_assessment(session, det.id, ra_update)

        # Verify only one row exists
        risk_rows = session.query(RiskAssessmentRow).filter(
            RiskAssessmentRow.detection_id == det.id
        ).all()
        assert len(risk_rows) == 1, f"Expected 1 risk assessment row, got {len(risk_rows)}"

        # Verify the values were updated
        assert risk_rows[0].migration_time_years == 3.0
        assert risk_rows[0].risk_level == "high"
        assert risk_rows[0].urgency_ratio == 1.2
        assert risk_rows[0].mosca_violation is True

        # Verify the returned object matches
        assert updated.migration_time_years == 3.0
        assert updated.risk_level == "high"
    finally:
        session.close()