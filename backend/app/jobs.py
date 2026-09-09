"""Redis-backed job status wrapper and background scan execution for ECDAT.

Provides:
- A thin Redis client wrapper reading ``REDIS_URL`` from env (default
  ``redis://localhost:6379/0``).
- :func:`set_job_status` / :func:`get_job_status` writing to
  ``scan:{scan_id}:status`` with a 24-hour TTL so Redis doesn't grow
  unbounded.
- :func:`run_scan_job` — the function executed as a FastAPI ``BackgroundTask``
  that orchestrates a full scan and drives status transitions
  (queued -> running -> done/failed).

If Redis is not reachable, the wrapper fails *quickly* (short socket timeouts,
no retry loops) with a clear :class:`RuntimeError` rather than hanging.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

import redis
from sqlalchemy.orm import Session

from backend.app.db import session as _session_factory
from backend.app.models_orm import ScanRun, ScanStatus, SourceType
from backend.app.repository import (
    mark_scan_done,
    mark_scan_failed,
    mark_scan_running,
    persist_scan_result,
)
from ecdat_core.cli import run_scan as ecdat_run_scan

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_DEFAULT_TTL_SECONDS = 24 * 3600  # 24 hours
# Short timeouts so an unreachable Redis fails fast instead of hanging.
_SOCKET_TIMEOUT_SECONDS = 1.0
_SOCKET_CONNECT_TIMEOUT_SECONDS = 1.0


def _get_redis() -> redis.Redis:
    """Return a Redis client and verify connectivity.

    Uses short socket/connect timeouts so a down or slow Redis raises a
    :class:`RuntimeError` with a helpful message in about a second rather than
    hanging.

    Raises:
        RuntimeError: If the Redis server at ``REDIS_URL`` cannot be reached.
    """
    try:
        client = redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_timeout=_SOCKET_TIMEOUT_SECONDS,
            socket_connect_timeout=_SOCKET_CONNECT_TIMEOUT_SECONDS,
        )
        client.ping()
        return client
    except redis.exceptions.RedisError as exc:
        raise RuntimeError(
            f"Cannot connect to Redis at {REDIS_URL}: {exc}. "
            "Ensure a Redis server is running, or set REDIS_URL correctly."
        ) from exc


def _key(scan_id: str) -> str:
    """Build the Redis key for a scan's status."""
    return f"scan:{scan_id}:status"


def set_job_status(scan_id: str, status: str) -> None:
    """Set the job status for a scan in Redis with a 24-hour TTL.

    Writes ``scan:{scan_id}:status`` with ``ex=_DEFAULT_TTL_SECONDS`` so stale
    keys expire automatically.

    Args:
        scan_id: The scan identifier.
        status: The status string (e.g. ``"queued"``, ``"running"``, ``"done"``,
            ``"failed"``).

    Raises:
        RuntimeError: If Redis is unreachable.
    """
    r = _get_redis()
    r.set(_key(scan_id), status, ex=_DEFAULT_TTL_SECONDS)


def get_job_status(scan_id: str) -> Optional[str]:
    """Get the job status for a scan from Redis.

    Reads ``scan:{scan_id}:status``.

    Args:
        scan_id: The scan identifier.

    Returns:
        The status string, or ``None`` if the key does not exist or has expired.

    Raises:
        RuntimeError: If Redis is unreachable.
    """
    r = _get_redis()
    return r.get(_key(scan_id))


def _new_session() -> Session:
    """Create a new SQLAlchemy session for use inside a background task."""
    return _session_factory()


def run_scan_job(scan_id: str, target: str, source_type: str) -> None:
    """Run a full ECDAT scan as a FastAPI ``BackgroundTask``.

    Drives the status transitions ``queued -> running -> done | failed`` across
    both the Redis status keys and the SQLAlchemy ``ScanRun`` row.

    Execution flow:

    1. Open a fresh DB session.
    2. Ensure a ``ScanRun`` exists for *scan_id* (create as ``queued`` if not
       already present).
    3. **Fail-fast** set ``running`` in Redis — if Redis is down, raise
       immediately (wrapped below) so the job fails clearly and early rather
       than hanging or silently proceeding untracked.
    4. Mark ``running`` in the DB.
    5. Call :func:`ecdat_core.cli.run_scan`.
    6. On success: :func:`repository.persist_scan_result` +
       ``mark_scan_done`` + ``set_job_status("done")``.
    7. On any exception: ``mark_scan_failed`` + ``set_job_status("failed")``.

    The terminal status updates (done/failed) are best-effort so the database
    always reflects the outcome even if Redis dies mid-scan. An exception is
    deliberately **not** re-raised: it is captured and recorded so nothing
    propagates silently out of the background task.

    Args:
        scan_id: The scan run ID (ORM primary key).
        target: The path or git URL to scan.
        source_type: Either ``"git_url"`` or ``"local_path"``.
    """
    session: Session = _new_session()
    try:
        # Ensure the scan run exists (typical API flow already created it).
        existing = session.get(ScanRun, scan_id)
        if existing is None:
            scan_run = ScanRun(
                id=scan_id,
                target=target,
                source_type=SourceType(source_type),
                status=ScanStatus.queued,
            )
            session.add(scan_run)
            session.commit()

        # Fail-fast: record "running" in Redis first. If Redis is unreachable
        # this raises immediately (short timeout) so the failure is surfaced
        # clearly instead of hanging or silently running untracked.
        set_job_status(scan_id, "running")

        # Mark running in the DB.
        mark_scan_running(session, scan_id)

        # Perform the actual scan using ecdat_core's library function.
        # source_type "git_url" maps to is_git_url=True, otherwise False.
        result = ecdat_run_scan(target=target, is_git_url=(source_type == "git_url"))

        # Persist the scan result to the database, then mark done.
        persist_scan_result(session, scan_id, result)
        mark_scan_done(session, scan_id, result.files_scanned)

        # Record "done" in Redis (best-effort).
        try:
            set_job_status(scan_id, "done")
        except RuntimeError:
            print(
                f"Warning: cannot record 'done' in Redis for scan {scan_id}; "
                "DB status is authoritative.",
                file=sys.stderr,
            )

    except Exception as exc:
        # Record the failure in the DB (best-effort) so the outcome is always
        # persisted, even if Redis is the component that failed.
        try:
            mark_scan_failed(session, scan_id, str(exc))
        except Exception as inner:
            print(
                f"Warning: failed to mark scan {scan_id} as failed in DB: "
                f"{inner}",
                file=sys.stderr,
            )

        # Record "failed" in Redis (best-effort).
        try:
            set_job_status(scan_id, "failed")
        except RuntimeError:
            print(
                f"Warning: cannot record 'failed' in Redis for scan {scan_id}; "
                "DB status is authoritative.",
                file=sys.stderr,
            )

        # Deliberately do NOT re-raise: the exception has been caught and
        # recorded. Re-raising would make the background-task framework log an
        # unhandled error, masking the already-recorded failure.

    finally:
        session.close()