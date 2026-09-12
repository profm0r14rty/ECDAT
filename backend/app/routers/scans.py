"""HTTP API for scan runs: create, list, inspect, and export scans.

Endpoints:

- ``POST /api/scans`` — create a ScanRun (status=``queued``), schedule
  :func:`backend.app.jobs.run_scan_job` as a FastAPI ``BackgroundTask``, and
  return ``202`` with the created scan's id and status.
- ``GET /api/scans`` — list scan runs, most recent first.
- ``GET /api/scans/{scan_id}`` — full scan run detail; when the scan is
  ``done`` the response also carries the ``export_summary()``-shaped summary
  computed on the fly from the persisted rows.
- ``GET /api/scans/{scan_id}/artefacts`` — paginated, filterable list of
  artefacts (detection + linked risk assessment + recommendation flattened
  into one object per artefact).
- ``GET /api/scans/{scan_id}/cbom`` — the full CycloneDX 1.6 CBOM as a
  downloadable JSON attachment.
- ``GET /api/scans/{scan_id}/report`` — the ``export_summary()``-shaped
  summary alone (same payload as the detail endpoint's ``summary`` field).
- ``PATCH /api/scans/{scan_id}/artefacts/{detection_id}`` — re-run the risk
  engine with explicit shelf-life / migration-time overrides and persist the
  updated assessment.

Every artefact-level endpoint returns ``404`` for an unknown scan and ``409``
("Scan not complete") when the scan's status is not ``done`` yet.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.jobs import run_scan_job
from backend.app.models_orm import (
    DetectionRow,
    RecommendationRow,
    RiskAssessmentRow,
    ScanRun,
    ScanStatus,
)
from backend.app.repository import (
    create_scan_run,
    detection_row_to_model,
    get_detection_for_scan,
    get_detection_triples,
    get_detection_with_risk_and_recommendation,
    get_scan_run,
    list_scan_runs,
    update_risk_assessment,
)
from backend.app.summary import build_scan_result_from_rows, build_summary_from_rows
from ecdat_core.cbom_export import export_cbom
from ecdat_core.ingestion import validate_git_url, validate_local_path
from ecdat_core.risk_engine import assess_risk
from ecdat_core.signature_loader import get_all_signatures

router = APIRouter(prefix="/api/scans", tags=["scans"])

DbSession = Annotated[Session, Depends(get_db)]

# Signature entries keyed by name: detector.py sets Detection.algorithm_family
# equal to the entry's name, so a persisted detection can be re-assessed.
_SIGNATURE_LOOKUP: dict[str, object] = {
    entry.name: entry for entry in get_all_signatures()
}


class CreateScanRequest(BaseModel):
    """Request body for ``POST /api/scans``."""

    source_type: Literal["git_url", "local_path"]
    target: str = Field(min_length=1)


class ScanCreatedResponse(BaseModel):
    """``202`` response body for ``POST /api/scans``."""

    id: str
    status: str


class ScanRunListItem(BaseModel):
    """One entry of ``GET /api/scans``."""

    id: str
    target: str
    source_type: str
    status: str
    created_at: datetime
    completed_at: datetime | None
    files_scanned: int | None


class ScanRunDetail(ScanRunListItem):
    """Full scan run detail; includes ``summary`` when the scan is done."""

    error_message: str | None = None
    summary: dict | None = None


class ArtefactRiskAssessment(BaseModel):
    """Risk assessment portion of a flattened artefact response."""

    migration_time_years: float
    shelf_life_years: float
    threat_horizon_years: float
    urgency_ratio: float
    risk_level: str
    mosca_violation: bool


class ArtefactRecommendation(BaseModel):
    """Recommendation portion of a flattened artefact response."""

    recommended_algorithm: str
    fips_reference: str
    rationale: str
    latency_note: str
    migration_note: str


class Artefact(BaseModel):
    """One artefact: detection fields plus its risk assessment and recommendation."""

    id: str
    file_path: str
    line_number: int
    matched_text: str
    asset_type: str
    algorithm_family: str
    key_size_bits: int | None
    quantum_vulnerable: bool
    classically_broken: bool
    confidence: float
    language: str
    detection_method: str
    risk_assessment: ArtefactRiskAssessment
    recommendation: ArtefactRecommendation


class ArtefactListResponse(BaseModel):
    """Paginated artefact listing with count and page metadata."""

    items: list[Artefact]
    total: int
    page: int
    page_size: int
    total_pages: int


class ArtefactOverrideRequest(BaseModel):
    """PATCH body: explicit risk-engine overrides (``None`` = use heuristics)."""

    shelf_life_years: float | None = Field(default=None, ge=0)
    migration_time_years: float | None = Field(default=None, ge=0)


def _validate_scan_target(source_type: str, target: str) -> None:
    """Reject scan targets that fail :mod:`ecdat_core.ingestion`'s security checks.

    Delegates to ecdat_core's validation (the API never re-implements scanner
    logic): local paths must resolve inside ``SCAN_WORKSPACE_ROOT`` and git
    URLs must be public ``https://`` targets.  Rejecting the request up-front
    with a 400 is cleaner than letting the background job fail asynchronously.

    Args:
        source_type: ``"git_url"`` or ``"local_path"``.
        target: The scan target string from the request body.

    Raises:
        HTTPException: 400 with ecdat_core's rejection message.
    """
    try:
        if source_type == "local_path":
            validate_local_path(target)
        else:
            validate_git_url(target)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


def _require_done_scan(session: Session, scan_id: str) -> ScanRun:
    """Return the scan run for *scan_id*, raising 404/409 when unavailable.

    Args:
        session: SQLAlchemy session.
        scan_id: The scan run ID.

    Returns:
        The ScanRun, guaranteed to have status ``done``.

    Raises:
        HTTPException: 404 when no scan exists, 409 when it is not done.
    """
    scan_run = get_scan_run(session, scan_id)
    if scan_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found"
        )
    if scan_run.status != ScanStatus.done:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Scan not complete"
        )
    return scan_run


def _artefact_from_rows(
    detection: DetectionRow,
    risk_assessment: RiskAssessmentRow,
    recommendation: RecommendationRow,
) -> Artefact:
    """Flatten one (detection, risk, recommendation) triple into an Artefact."""
    return Artefact(
        id=detection.id,
        file_path=detection.file_path,
        line_number=detection.line_number,
        matched_text=detection.matched_text,
        asset_type=detection.asset_type.value,
        algorithm_family=detection.algorithm_family,
        key_size_bits=detection.key_size_bits,
        quantum_vulnerable=detection.quantum_vulnerable,
        classically_broken=detection.classically_broken,
        confidence=detection.confidence,
        language=detection.language,
        detection_method=detection.detection_method,
        risk_assessment=ArtefactRiskAssessment(
            migration_time_years=risk_assessment.migration_time_years,
            shelf_life_years=risk_assessment.shelf_life_years,
            threat_horizon_years=risk_assessment.threat_horizon_years,
            urgency_ratio=risk_assessment.urgency_ratio,
            risk_level=risk_assessment.risk_level.value,
            mosca_violation=risk_assessment.mosca_violation,
        ),
        recommendation=ArtefactRecommendation(
            recommended_algorithm=recommendation.recommended_algorithm,
            fips_reference=recommendation.fips_reference,
            rationale=recommendation.rationale,
            latency_note=recommendation.latency_note,
            migration_note=recommendation.migration_note,
        ),
    )


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ScanCreatedResponse,
)
def create_scan(
    payload: CreateScanRequest,
    background_tasks: BackgroundTasks,
    session: DbSession,
) -> ScanCreatedResponse:
    """Create a queued scan run and schedule the scan as a background task.

    Args:
        payload: The scan request (source type + target path/URL).
        background_tasks: FastAPI background task scheduler.
        session: SQLAlchemy session from the ``get_db`` dependency.

    Returns:
        The created scan's id and ``"queued"`` status.

    Raises:
        HTTPException: 400 when the target fails the ingestion security
            validation — a local path outside ``SCAN_WORKSPACE_ROOT``, or a
            git URL with a non-https scheme / non-public resolved address /
            host not on the ``GIT_URL_ALLOWED_HOSTS`` allowlist.
    """
    _validate_scan_target(payload.source_type, payload.target)

    scan_run = create_scan_run(session, payload.target, payload.source_type)
    background_tasks.add_task(
        run_scan_job, scan_run.id, payload.target, payload.source_type
    )
    return ScanCreatedResponse(id=scan_run.id, status=scan_run.status.value)


@router.get("", response_model=list[ScanRunListItem])
def list_scans(session: DbSession) -> list[ScanRunListItem]:
    """List scan runs, most recent first.

    Args:
        session: SQLAlchemy session from the ``get_db`` dependency.

    Returns:
        Scan run summaries (id, target, source_type, status, created_at,
        completed_at, files_scanned) ordered by ``created_at`` descending.
    """
    return [
        ScanRunListItem(
            id=run.id,
            target=run.target,
            source_type=run.source_type.value,
            status=run.status.value,
            created_at=run.created_at,
            completed_at=run.completed_at,
            files_scanned=run.files_scanned,
        )
        for run in list_scan_runs(session)
    ]


@router.get("/{scan_id}", response_model=ScanRunDetail)
def get_scan(scan_id: str, session: DbSession) -> ScanRunDetail:
    """Return full scan run detail for one scan.

    When the scan's status is ``done``, the response additionally includes the
    ``export_summary()``-shaped summary (risk counts, quantum-vulnerable %,
    top-5 urgency) computed on the fly from the persisted rows.

    Args:
        scan_id: The scan run ID.
        session: SQLAlchemy session from the ``get_db`` dependency.

    Returns:
        The scan run detail plus an optional summary dict.

    Raises:
        HTTPException: 404 when no scan run exists for *scan_id*.
    """
    scan_run = get_scan_run(session, scan_id)
    if scan_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found"
        )

    summary = None
    if scan_run.status.value == "done":
        summary = build_summary_from_rows(session, scan_run)

    return ScanRunDetail(
        id=scan_run.id,
        target=scan_run.target,
        source_type=scan_run.source_type.value,
        status=scan_run.status.value,
        created_at=scan_run.created_at,
        completed_at=scan_run.completed_at,
        files_scanned=scan_run.files_scanned,
        error_message=scan_run.error_message,
        summary=summary,
    )


@router.get("/{scan_id}/artefacts", response_model=ArtefactListResponse)
def list_artefacts(
    scan_id: str,
    session: DbSession,
    risk_level: str | None = Query(default=None),
    algorithm_family: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
) -> ArtefactListResponse:
    """List a done scan's artefacts, paginated and filterable.

    Each response item flattens one detection together with its linked risk
    assessment and recommendation. Filters join against the persisted risk
    assessments, so ``risk_level`` matches arbitrary risk levels.

    Args:
        scan_id: The scan run ID.
        session: SQLAlchemy session from the ``get_db`` dependency.
        risk_level: Optional risk level filter (e.g. "critical").
        algorithm_family: Optional algorithm family filter (e.g. "RSA").
        page: 1-indexed page number.
        page_size: Items per page (1-500).

    Returns:
        The page of artefacts plus ``total``, ``page``, ``page_size`` and
        ``total_pages`` metadata.

    Raises:
        HTTPException: 404 when no scan exists, 409 when it is not done.
    """
    _require_done_scan(session, scan_id)
    triples, total = get_detection_triples(
        session,
        scan_id,
        risk_level=risk_level,
        algorithm_family=algorithm_family,
        page=page,
        page_size=page_size,
    )
    items = [_artefact_from_rows(det, risk, rec) for det, risk, rec in triples]
    total_pages = (total + page_size - 1) // page_size if total else 0
    return ArtefactListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{scan_id}/cbom")
def get_scan_cbom(scan_id: str, session: DbSession) -> JSONResponse:
    """Download the full CycloneDX 1.6 CBOM for a done scan as JSON.

    The ScanResult is reconstructed from the persisted rows on every request
    rather than cached at persist time, so the export always reflects later
    per-artefact risk overrides applied via ``PATCH``.

    Args:
        scan_id: The scan run ID.
        session: SQLAlchemy session from the ``get_db`` dependency.

    Returns:
        A JSON response containing the CBOM, with a
        ``Content-Disposition: attachment; filename=cbom.json`` header.

    Raises:
        HTTPException: 404 when no scan exists, 409 when it is not done.
    """
    scan_run = _require_done_scan(session, scan_id)
    result = build_scan_result_from_rows(session, scan_run)
    return JSONResponse(
        content=export_cbom(result),
        headers={"Content-Disposition": "attachment; filename=cbom.json"},
    )


@router.get("/{scan_id}/report")
def get_scan_report(scan_id: str, session: DbSession) -> dict:
    """Return the ``export_summary()``-shaped report for a done scan.

    The payload is identical to the ``summary`` field embedded in the scan
    detail endpoint, as its own endpoint for clients that want just the
    summary without the full scan metadata.

    Args:
        scan_id: The scan run ID.
        session: SQLAlchemy session from the ``get_db`` dependency.

    Returns:
        The ``export_summary()``-shaped dict for the scan.

    Raises:
        HTTPException: 404 when no scan exists, 409 when it is not done.
    """
    scan_run = _require_done_scan(session, scan_id)
    return build_summary_from_rows(session, scan_run)


@router.patch(
    "/{scan_id}/artefacts/{detection_id}",
    response_model=Artefact,
)
def override_artefact_risk(
    scan_id: str,
    detection_id: str,
    payload: ArtefactOverrideRequest,
    session: DbSession,
) -> Artefact:
    """Re-run the risk engine with explicit overrides and persist the result.

    Recomputes the detection's risk assessment via
    :func:`ecdat_core.risk_engine.assess_risk` using the persisted detection
    and its signature entry, applying *payload*'s shelf-life (Y) and
    migration-time (X) overrides (``None`` keeps the default heuristics). The
    updated assessment is persisted via
    :func:`backend.app.repository.update_risk_assessment`.

    Args:
        scan_id: The scan run ID the detection belongs to.
        detection_id: The detection row ID to re-assess.
        payload: The override body.
        session: SQLAlchemy session from the ``get_db`` dependency.

    Returns:
        The updated artefact (detection + new risk assessment +
        recommendation).

    Raises:
        HTTPException: 404 when the scan does not exist or the detection does
            not belong to the scan; 409 when the scan is not done.
    """
    _require_done_scan(session, scan_id)
    detection = get_detection_for_scan(session, scan_id, detection_id)
    if detection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Detection not found in scan",
        )

    entry = _SIGNATURE_LOOKUP.get(detection.algorithm_family)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"No signature entry for family "
                f"{detection.algorithm_family!r}; cannot re-assess"
            ),
        )

    core_detection = detection_row_to_model(detection)
    new_assessment = assess_risk(
        core_detection,
        entry,
        shelf_life_override=payload.shelf_life_years,
        migration_time_override=payload.migration_time_years,
    )
    updated_row = update_risk_assessment(session, detection_id, new_assessment)

    triple = get_detection_with_risk_and_recommendation(session, detection_id)
    if triple is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Detection is missing its recommendation row",
        )
    _, _, recommendation = triple
    return _artefact_from_rows(detection, updated_row, recommendation)