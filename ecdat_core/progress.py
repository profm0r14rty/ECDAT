"""Progress reporting and cancellation hooks for the ECDAT scan pipeline.

Exposes a minimal, stdlib-only set of types so that ``ecdat_core.cli.run_scan``
can emit granular progress events without pulling in any external dependencies
(e.g. Pydantic, Rich).  Callers provide a ``ProgressCallback`` to receive
:class:`ScanProgress` snapshots; raising :class:`ScanCancelled` inside the
callback aborts the running scan cleanly.

Public API:
    - :class:`ScanStage` – literal union of all pipeline stages.
    - :class:`ScanProgress` – frozen, slotted progress snapshot.
    - :class:`ProgressCallback` – protocol for receiving progress snapshots.
    - :class:`ScanCancelled` – exception raised by callbacks to abort a scan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

# ---------------------------------------------------------------------------
# Scan stage literal — ordered phases of the ECDAT pipeline
# ---------------------------------------------------------------------------

ScanStage = Literal[
    "clone",      # cloning a git repository (git_url scans only)
    "ingest",     # walking the directory tree, reading files
    "detect",     # regex-scanning each source file for crypto artefacts
    "assess",     # running Mosca's-inequality risk assessment
    "recommend",  # looking up NIST PQC replacement recommendations
    "assemble",   # packaging everything into a ScanResult
    "done",       # scan complete (final callback with total counts)
]

# ---------------------------------------------------------------------------
# ScanProgress — frozen, allocation-light progress snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ScanProgress:
    """An immutable progress snapshot emitted by ``run_scan``.

    All fields are read-only so a callback cannot accidentally mutate shared
    state.  ``slots=True`` keeps per-snapshot memory overhead minimal for
    callbacks that fire hundreds of times during ``detect``.

    Attributes:
        stage: The current pipeline stage (one of :data:`ScanStage`).
        message: Human-readable description of the current activity.
        current: Unit count for the current stage (e.g. files scanned).
        total: Expected total for the current stage, or ``None`` if unknown.
        detections: Cumulative detections found so far.
    """

    stage: ScanStage
    message: str = ""
    current: int = 0
    total: int | None = None
    detections: int = 0


# ---------------------------------------------------------------------------
# ProgressCallback — lightweight protocol
# ---------------------------------------------------------------------------

ProgressCallback = Callable[[ScanProgress], None]

# ---------------------------------------------------------------------------
# ScanCancelled — clean abort exception
# ---------------------------------------------------------------------------


class ScanCancelled(Exception):
    """Raised by a :class:`ProgressCallback` to abort a running scan.

    The scan orchestrator catches this exception, ensures temp clone directories
    are cleaned up (in a ``try/finally`` block), and re-raises it unchanged to
    the caller.  Callbacks can inspect the :attr:`progress` snapshot to
    determine at which stage and progress point the cancellation occurred.

    Attributes:
        progress: The :class:`ScanProgress` snapshot that triggered the
            cancellation (set by the caller or automatically by ``run_scan``
            if the callback itself raises).
    """

    def __init__(self, *args: object, progress: ScanProgress | None = None) -> None:
        super().__init__(*args)
        self.progress = progress