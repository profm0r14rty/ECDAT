"""ECDAT scanner service.

Wraps :func:`ecdat_core.cli.run_scan` with:
- A Rich ``Progress`` bar on **stderr** (payloads go to stdout).
- Optional automatic history saving via :func:`ecdat.services.history.save_scan`.

Public API:
    - :func:`perform_scan` — run a scan with visual progress and history.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import Optional

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)

from ecdat_core.cli import run_scan
from ecdat_core.models import ScanResult
from ecdat_core.progress import ProgressCallback, ScanProgress

# ---------------------------------------------------------------------------
# Rich Console — stderr only so stdout stays clean for payloads.
# ---------------------------------------------------------------------------

_stderr = Console(stderr=True, highlight=False)

# ---------------------------------------------------------------------------
# Stage → display label mapping
# ---------------------------------------------------------------------------

_STAGE_LABELS: dict[str, str] = {
    "clone": "Cloning",
    "ingest": "Indexing files",
    "detect": "Scanning for crypto",
    "assess": "Assessing risk",
    "recommend": "Generating recommendations",
    "assemble": "Assembling result",
    "done": "Complete",
}

_STAGE_SPINNER_MAP: set[str] = {"clone", "ingest", "recommend", "assemble"}
_STAGE_COUNT_MAP: set[str] = {"detect", "assess"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def perform_scan(
    target: str,
    *,
    is_git_url: bool = False,
    save_history: bool = True,
    exclude: Sequence[str] = (),
) -> ScanResult:
    """Run an ECDAT scan with a Rich progress bar on stderr.

    Args:
        target: Local directory path or git URL (with ``is_git_url``).
        is_git_url: When ``True``, treat *target* as a git URL.
        save_history: When ``True`` (default), persist the result to the
            scan history after completion.  History save failures are
            silently logged — they never abort the scan.
        exclude: ``fnmatch`` patterns passed to the scanner.

    Returns:
        The assembled :class:`ScanResult`.

    Raises:
        Same exceptions as :func:`ecdat_core.cli.run_scan`.
    """
    # We use a single Rich Progress context that manages task lifecycle.
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=_stderr,
        transient=False,
    ) as progress:
        # The callback closure — maps ScanProgress → Rich task updates.
        current_task_id: TaskID | None = None  # noqa: E0601  (simulating nonlocal)
        _state = {"task_id": None}

        def _on_progress(sp: ScanProgress) -> None:
            nonlocal current_task_id
            label = _STAGE_LABELS.get(sp.stage, sp.stage)

            if sp.stage == "done":
                # Finalise the current task.
                if _state["task_id"] is not None:
                    tid = _state["task_id"]
                    progress.update(tid, description=f"[green]{label}", completed=sp.total if sp.total else 100)
                return

            # Decide if we should create a new task or update existing.
            if _state["task_id"] is None or sp.stage in _STAGE_SPINNER_MAP or sp.stage in _STAGE_COUNT_MAP:
                # Close previous task if it's a spinner/transient stage.
                if _state["task_id"] is not None and sp.stage not in _STAGE_SPINNER_MAP:
                    # Keep count-based tasks; replace spinners.
                    pass

                if sp.stage in _STAGE_COUNT_MAP and sp.total:
                    # Count-based progress bar.
                    if _state["task_id"] is not None and progress._tasks:
                        progress.remove_task(_state["task_id"])
                    tid = progress.add_task(
                        f"[bold blue]{label}",
                        total=sp.total,
                    )
                    _state["task_id"] = tid
                elif sp.stage in _STAGE_SPINNER_MAP:
                    # Spinner-only (no known total).
                    if _state["task_id"] is not None and progress._tasks:
                        progress.remove_task(_state["task_id"])
                    tid = progress.add_task(
                        f"[bold blue]{label}",
                        total=None,
                    )
                    _state["task_id"] = tid

            # Update the current task.
            if _state["task_id"] is not None:
                desc = f"[bold blue]{label}"
                if sp.message and sp.stage in _STAGE_COUNT_MAP:
                    # Show the file being scanned in the description.
                    pass  # Keep label clean during count stages
                if sp.stage in _STAGE_SPINNER_MAP:
                    # Mark spinner stages complete when they report current=total.
                    if sp.current >= (sp.total or 1) and sp.total is not None and sp.total > 0:
                        desc = f"[green]{label}"
                        progress.update(_state["task_id"], description=desc, completed=sp.total, total=sp.total)
                    else:
                        progress.update(_state["task_id"], description=desc, total=sp.total)
                elif sp.total:
                    progress.update(_state["task_id"], completed=sp.current, total=sp.total, description=desc)
                else:
                    progress.update(_state["task_id"], description=desc)

        # --- run the actual scan ---
        result = run_scan(
            target,
            is_git_url=is_git_url,
            on_progress=_on_progress,
            exclude=exclude,
        )

        # Finalise any remaining task.
        if _state["task_id"] is not None and progress._tasks:
            progress.update(_state["task_id"], description="[green]Complete", completed=100, total=100)

    # --- save to history (best-effort) ---
    if save_history:
        try:
            from ecdat.services.history import save_scan as _history_save
            _history_save(result)
        except Exception:
            # History save never fails a scan.
            pass

    return result