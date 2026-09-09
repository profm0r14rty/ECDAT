"""Build ``export_summary()``-shaped summaries from persisted ORM rows.

The API layer must never duplicate ``ecdat_core`` aggregation logic. This
module reconstructs an in-memory :class:`ecdat_core.models.ScanResult` from
the persisted ``DetectionRow`` / ``RiskAssessmentRow`` / ``RecommendationRow``
rows for a scan run and delegates to
:func:`ecdat_core.cbom_export.export_summary`, so the summary shape is always
exactly what the scanner core itself produces.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.models_orm import (
    DetectionRow,
    RecommendationRow,
    RiskAssessmentRow,
    ScanRun,
)
from ecdat_core.cbom_export import export_summary
from ecdat_core.models import Detection, Recommendation, RiskAssessment, ScanResult


def build_summary_from_rows(session: Session, scan_run: ScanRun) -> dict:
    """Reconstruct a ScanResult from persisted rows and summarise it.

    Args:
        session: SQLAlchemy session bound to the database holding the scan's
            persisted rows.
        scan_run: The completed ``ScanRun`` row to summarise.

    Returns:
        An ``export_summary()``-shaped dict (risk-level counts,
        quantum-vulnerable statistics, algorithm family counts, top-5 urgency)
        computed entirely from the persisted rows for *scan_run*.
    """
    result = ScanResult(
        scan_id=scan_run.id,
        target=scan_run.target,
        detections=_detections_for_scan(session, scan_run.id),
        risk_assessments=_risk_assessments_for_scan(session, scan_run.id),
        recommendations=_recommendations_for_scan(session, scan_run.id),
        scanned_at=(
            scan_run.completed_at.isoformat()
            if scan_run.completed_at is not None
            else datetime.now(timezone.utc).isoformat()
        ),
        files_scanned=scan_run.files_scanned or 0,
    )
    return export_summary(result)


def _detections_for_scan(session: Session, scan_id: str) -> list[Detection]:
    """Load all DetectionRow rows for a scan as ecdat_core Detection models."""
    rows = (
        session.query(DetectionRow)
        .filter(DetectionRow.scan_id == scan_id)
        .all()
    )
    return [
        Detection(
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
        for row in rows
    ]


def _risk_assessments_for_scan(session: Session, scan_id: str) -> list[RiskAssessment]:
    """Load the risk assessments belonging to a scan's detections."""
    rows = (
        session.query(RiskAssessmentRow)
        .join(DetectionRow, RiskAssessmentRow.detection_id == DetectionRow.id)
        .filter(DetectionRow.scan_id == scan_id)
        .all()
    )
    return [
        RiskAssessment(
            detection_id=row.detection_id,
            migration_time_years=row.migration_time_years,
            shelf_life_years=row.shelf_life_years,
            threat_horizon_years=row.threat_horizon_years,
            urgency_ratio=row.urgency_ratio,
            risk_level=row.risk_level.value,
            mosca_violation=row.mosca_violation,
        )
        for row in rows
    ]


def _recommendations_for_scan(
    session: Session, scan_id: str
) -> list[Recommendation]:
    """Load the recommendations belonging to a scan's detections."""
    rows = (
        session.query(RecommendationRow)
        .join(DetectionRow, RecommendationRow.detection_id == DetectionRow.id)
        .filter(DetectionRow.scan_id == scan_id)
        .all()
    )
    return [
        Recommendation(
            detection_id=row.detection_id,
            recommended_algorithm=row.recommended_algorithm,
            fips_reference=row.fips_reference,
            rationale=row.rationale,
            latency_note=row.latency_note,
            migration_note=row.migration_note,
        )
        for row in rows
    ]