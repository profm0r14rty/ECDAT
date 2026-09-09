"""HTTP API for scan runs: create, list, and inspect scans.

Endpoints:

- ``POST /api/scans`` — create a ScanRun (status=``queued``), schedule
  :func:`backend.app.jobs.run_scan_job` as a FastAPI ``BackgroundTask``, and
  return ``202`` with the created scan's id and status.
- ``GET /api/scans`` — list scan runs, most recent first.
- ``GET /api/scans/{scan_id}`` — full scan run detail; when the scan is
  ``done`` the response also carries the ``export_summary()``-shaped summary
  computed on the fly from the persisted rows.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.jobs import run_scan_job
from backend.app.repository import create_scan_run, get_scan_run, list_scan_runs
from backend.app.summary import build_summary_from_rows

router = APIRouter(prefix="/api/scans", tags=["scans"])

DbSession = Annotated[Session, Depends(get_db)]


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
    """
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