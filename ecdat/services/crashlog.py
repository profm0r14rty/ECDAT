"""Crash-log writer for unexpected ECDAT failures.

When :func:`ecdat.cli.main` catches an exception it cannot attribute to a
known user error, it records a crash report under
:func:`ecdat.services.paths.logs_dir` and points the user at it.  Writing a
crash log must never mask the original failure, so :func:`write_crash_log`
swallows *every* error and returns ``None`` instead of raising.

Only the newest :data:`_MAX_CRASH_LOGS` reports are retained.
"""

from __future__ import annotations

import platform
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from ecdat.services.paths import logs_dir

__all__ = ["write_crash_log"]

_MAX_CRASH_LOGS = 20


def _utc_stamp() -> str:
    """Return a sortable UTC timestamp (microsecond precision)."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _format_report(exc: BaseException, argv: Sequence[str]) -> str:
    """Build the human-readable crash report body."""
    from ecdat import __version__

    tb = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    python = sys.version.replace("\n", " ")
    return (
        "ECDAT crash report\n"
        "==================\n"
        f"ecdat:    {__version__}\n"
        f"python:   {python}\n"
        f"platform: {platform.platform()}\n"
        f"argv:     {list(argv)!r}\n"
        f"error:    {type(exc).__name__}: {exc}\n"
        "\n"
        "traceback:\n"
        f"{tb}"
    )


def _trim(directory: Path, keep: int) -> None:
    """Delete the oldest ``crash-*.log`` files, keeping the newest *keep*.

    Ordering is by modification time (nanosecond resolution) with the
    timestamp-prefixed name as tiebreaker.  Best-effort: unlink failures are
    ignored.
    """

    def _sort_key(path: Path):
        try:
            return (path.stat().st_mtime_ns, path.name)
        except OSError:
            return (0, path.name)

    logs = sorted(directory.glob("crash-*.log"), key=_sort_key)
    stale = logs[:-keep] if keep > 0 else logs
    for old in stale:
        try:
            old.unlink()
        except OSError:
            pass


def write_crash_log(
    exc: BaseException,
    argv: Sequence[str],
) -> Optional[Path]:
    """Write a crash report for *exc* and return its path (or ``None``).

    Args:
        exc: The unexpected exception to record.
        argv: The command-line arguments the process was launched with.

    Returns:
        The path of the newly written log file, or ``None`` if the log could
        not be written (e.g. the data directory is not writable).  This
        function never raises.
    """
    try:
        directory = logs_dir()
        directory.mkdir(parents=True, exist_ok=True)

        stamp = _utc_stamp()
        path = directory / f"crash-{stamp}.log"
        suffix = 0
        while path.exists():
            suffix += 1
            path = directory / f"crash-{stamp}-{suffix}.log"

        path.write_text(_format_report(exc, argv), encoding="utf-8")
        _trim(directory, _MAX_CRASH_LOGS)
        return path
    except Exception:
        # A crash logger that raises is worse than no crash logger.
        return None
