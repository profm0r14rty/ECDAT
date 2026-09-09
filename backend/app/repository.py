"""Repository layer: translate between ecdat_core Pydantic models and SQLAlchemy ORM rows.

Provides functions to create, read, update, and persist scan runs and their
associated detection/risk/recommendation rows using a SQLAlchemy session.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.models_orm import (
    DetectionAssetType,
    DetectionRow,
    RiskAssessmentRow,
    RecommendationRow,
    RiskLevel,
    ScanRun,
    ScanStatus,
    SourceType,
)
from ecdat_core.models import Detection, RiskAssessment, Recommendation, ScanResult


def create_scan_run(session: Session, target: str, source_type: str) -> ScanRun:
    """Create a new scan run with status="queued".

    Args:
        session: SQLAlchemy session.
        target: Path or URL that was scanned.
        source_type: Either "git_url" or "local_path".

    Returns:
        The newly created ScanRun ORM row (status="queued").
    """
    scan_run = ScanRun(
        target=target,
        source_type=SourceType(source_type),
        status=ScanStatus.queued,
    )
    session.add(scan_run)
    session.commit()
    session.refresh(scan_run)
    return scan_run


def mark_scan_running(session: Session, scan_id: str) -> None:
    """Mark a scan run as running."""
    scan_run = session.get(ScanRun, scan_id)
    assert scan_run is not None, f"ScanRun {scan_id} not found"
    scan_run.status = ScanStatus.running
    session.commit()


def mark_scan_done(session: Session, scan_id: str, files_scanned: int) -> None:
    """Mark a scan run as done with the number of files scanned."""
    scan_run = session.get(ScanRun, scan_id)
    assert scan_run is not None, f"ScanRun {scan_id} not found"
    scan_run.status = ScanStatus.done
    scan_run.files_scanned = files_scanned
    scan_run.completed_at = datetime.now(timezone.utc)
    session.commit()


def mark_scan_failed(session: Session, scan_id: str, error_message: str) -> None:
    """Mark a scan run as failed with an error message."""
    scan_run = session.get(ScanRun, scan_id)
    assert scan_run is not None, f"ScanRun {scan_id} not found"
    scan_run.status = ScanStatus.failed
    scan_run.error_message = error_message
    scan_run.completed_at = datetime.now(timezone.utc)
    session.commit()


def persist_scan_result(
    session: Session,
    scan_id: str,
    result: ScanResult,
) -> None:
    """Reset session state to ensure fresh DB reads for upsert operations."""
    session.expire_all()

    # ... rest of the function remains the same
    """Persist an ecdat_core ScanResult into ORM rows.

    Writes DetectionRow, RiskAssessmentRow, and RecommendationRow entries
    for every item in the ecdat_core ScanResult, linked to scan_id.

    If a DetectionRow already exists for a given scan_id + detection id, it is
    updated (upsert behaviour). Similarly for RiskAssessmentRow and
    RecommendationRow — they are replaced if they already exist (unique FK
    constraint on detection_id).

    Args:
        session: SQLAlchemy session.
        scan_id: The scan run ID to link all rows to.
        result: The ecdat_core ScanResult instance.
    """
    # --- Persist detections (upsert) ---
    for det in result.detections:
        # Use explicit DB query to find existing row (avoids session state issues)
        existing = (
            session.query(DetectionRow)
            .filter(DetectionRow.id == det.id, DetectionRow.scan_id == scan_id)
            .first()
        )
        if existing is None:
            existing = DetectionRow(scan_id=scan_id, id=det.id)
            session.add(existing)
        # Map fields from ecdat_core Detection to ORM DetectionRow
        existing.file_path = det.file_path
        existing.line_number = det.line_number
        existing.matched_text = det.matched_text
        existing.asset_type = DetectionAssetType(det.asset_type)
        existing.algorithm_family = det.algorithm_family
        existing.key_size_bits = det.key_size_bits
        existing.quantum_vulnerable = det.quantum_vulnerable
        existing.classically_broken = det.classically_broken
        existing.confidence = det.confidence
        existing.language = det.language
        existing.detection_method = det.detection_method

    # --- Persist risk assessments (replace if exists) ---
    for risk in result.risk_assessments:
        # Use explicit DB query to find existing row
        existing = (
            session.query(RiskAssessmentRow)
            .filter(RiskAssessmentRow.detection_id == risk.detection_id)
            .first()
        )
        if existing is None:
            existing = RiskAssessmentRow(detection_id=risk.detection_id)
            session.add(existing)
        existing.migration_time_years = risk.migration_time_years
        existing.shelf_life_years = risk.shelf_life_years
        existing.threat_horizon_years = risk.threat_horizon_years
        existing.urgency_ratio = risk.urgency_ratio
        existing.risk_level = RiskLevel(risk.risk_level)
        existing.mosca_violation = risk.mosca_violation

    # --- Persist recommendations (replace if exists) ---
    for rec in result.recommendations:
        # Use explicit DB query to find existing row
        existing = (
            session.query(RecommendationRow)
            .filter(RecommendationRow.detection_id == rec.detection_id)
            .first()
        )
        if existing is None:
            existing = RecommendationRow(detection_id=rec.detection_id)
            session.add(existing)
        existing.recommended_algorithm = rec.recommended_algorithm
        existing.fips_reference = rec.fips_reference
        existing.rationale = rec.rationale
        existing.latency_note = rec.latency_note
        existing.migration_note = rec.migration_note

    session.commit()


def get_scan_run(session: Session, scan_id: str) -> ScanRun | None:
    """Get a ScanRun by its ID."""
    return session.get(ScanRun, scan_id)


def list_scan_runs(session: Session, limit: int = 50) -> list[ScanRun]:
    """List scan runs, newest first, limited by count."""
    return (
        session.query(ScanRun)
        .order_by(ScanRun.created_at.desc())
        .limit(limit)
        .all()
    )


def get_detections(
    session: Session,
    scan_id: str,
    risk_level: str | None = None,
    algorithm_family: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[DetectionRow], int]:
    """Get paginated detections for a scan, with optional filters.

    Args:
        session: SQLAlchemy session.
        scan_id: Filter to a specific scan.
        risk_level: Optional filter by risk level string (e.g. "critical").
        algorithm_family: Optional filter by algorithm family.
        page: 1-indexed page number.
        page_size: Number of items per page.

    Returns:
        Tuple of (page of DetectionRow rows, total count).
    """
    query = session.query(DetectionRow).filter(DetectionRow.scan_id == scan_id)

    # risk_level lives on RiskAssessmentRow (whose detection_id FK is UNIQUE,
    # so this inner join is 1:1 and count() is unaffected).
    if risk_level is not None:
        query = query.join(
            RiskAssessmentRow, DetectionRow.id == RiskAssessmentRow.detection_id
        ).filter(RiskAssessmentRow.risk_level == RiskLevel(risk_level))

    if algorithm_family is not None:
        query = query.filter(DetectionRow.algorithm_family == algorithm_family)

    total_count = query.count()

    # Apply pagination
    offset = (page - 1) * page_size
    rows = query.offset(offset).limit(page_size).all()

    return rows, total_count


def get_detection_with_risk_and_recommendation(
    session: Session, detection_id: str
) -> tuple[DetectionRow, RiskAssessmentRow, RecommendationRow] | None:
    """Get a detection along with its risk assessment and recommendation.

    Uses explicit DB queries to avoid session state issues.

    Args:
        session: SQLAlchemy session.
        detection_id: The detection row ID.

    Returns:
        Tuple of (DetectionRow, RiskAssessmentRow, RecommendationRow) or None
        if any of the rows are missing.
    """
    detection = (
        session.query(DetectionRow)
        .filter(DetectionRow.id == detection_id)
        .first()
    )
    if detection is None:
        return None

    risk = (
        session.query(RiskAssessmentRow)
        .filter(RiskAssessmentRow.detection_id == detection_id)
        .first()
    )
    if risk is None:
        return None

    rec = (
        session.query(RecommendationRow)
        .filter(RecommendationRow.detection_id == detection_id)
        .first()
    )
    if rec is None:
        return None

    return detection, risk, rec


def detection_row_to_model(row: DetectionRow) -> Detection:
    """Convert a DetectionRow ORM row into an ecdat_core Detection model.

    Args:
        row: The persisted detection row.

    Returns:
        The equivalent :class:`ecdat_core.models.Detection`.
    """
    return Detection(
        id=row.id,
        file_path=row.file_path,
        line_number=row.line_number,
        matched_text=row.matched_text,
        asset_type=row.asset_type.value,
        algorithm_family=row.algorithm_family,
        key_size_bits=row.key_size_bits,
        quantum_vulnerable=row.quantum_vulnerable,
        classically_broken=row.classically_broken,
        confidence=row.confidence,
        language=row.language,
        detection_method=row.detection_method,
    )


def get_detection_for_scan(
    session: Session, scan_id: str, detection_id: str
) -> DetectionRow | None:
    """Get a detection row that belongs to a specific scan.

    Args:
        session: SQLAlchemy session.
        scan_id: The scan run the detection must belong to.
        detection_id: The detection row ID.

    Returns:
        The DetectionRow, or None when no such detection exists for *scan_id*.
    """
    return (
        session.query(DetectionRow)
        .filter(DetectionRow.id == detection_id, DetectionRow.scan_id == scan_id)
        .first()
    )


def get_detection_triples(
    session: Session,
    scan_id: str,
    risk_level: str | None = None,
    algorithm_family: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[tuple[DetectionRow, RiskAssessmentRow, RecommendationRow]], int]:
    """Get one page of (detection, risk assessment, recommendation) triples.

    Filters and pagination behave exactly like :func:`get_detections`. A
    detection whose risk assessment or recommendation row is missing is
    skipped (mirrors the incomplete-tuple contract of
    :func:`get_detection_with_risk_and_recommendation`).

    Args:
        session: SQLAlchemy session.
        scan_id: Filter to a specific scan.
        risk_level: Optional filter by risk level string (e.g. "critical").
        algorithm_family: Optional filter by algorithm family.
        page: 1-indexed page number.
        page_size: Number of items per page.

    Returns:
        Tuple of (list of complete (detection, risk, recommendation) triples
        in the requested page, total matching detection count).
    """
    rows, total = get_detections(
        session,
        scan_id,
        risk_level=risk_level,
        algorithm_family=algorithm_family,
        page=page,
        page_size=page_size,
    )
    if not rows:
        return [], total

    detection_ids = [row.id for row in rows]
    risks = {
        risk.detection_id: risk
        for risk in session.query(RiskAssessmentRow)
        .filter(RiskAssessmentRow.detection_id.in_(detection_ids))
        .all()
    }
    recs = {
        rec.detection_id: rec
        for rec in session.query(RecommendationRow)
        .filter(RecommendationRow.detection_id.in_(detection_ids))
        .all()
    }
    triples = [
        (row, risks[row.id], recs[row.id])
        for row in rows
        if row.id in risks and row.id in recs
    ]
    return triples, total


def update_risk_assessment(
    session: Session,
    detection_id: str,
    new_assessment: RiskAssessment,
) -> RiskAssessmentRow:
    """Update a risk assessment for a detection, overwriting the existing row.

    Uses explicit DB queries to avoid session state issues.

    If a RiskAssessmentRow already exists for this detection_id, it is replaced.
    If not, a new one is created.

    Args:
        session: SQLAlchemy session.
        detection_id: The detection row ID.
        new_assessment: The new RiskAssessment value from ecdat_core.

    Returns:
        The updated RiskAssessmentRow.
    """
    # Use explicit DB query to find existing row
    existing = (
        session.query(RiskAssessmentRow)
        .filter(RiskAssessmentRow.detection_id == detection_id)
        .first()
    )
    if existing is None:
        existing = RiskAssessmentRow(detection_id=detection_id)
        session.add(existing)
    existing.migration_time_years = new_assessment.migration_time_years
    existing.shelf_life_years = new_assessment.shelf_life_years
    existing.threat_horizon_years = new_assessment.threat_horizon_years
    existing.urgency_ratio = new_assessment.urgency_ratio
    existing.risk_level = RiskLevel(new_assessment.risk_level)
    existing.mosca_violation = new_assessment.mosca_violation
    session.commit()
    return existing