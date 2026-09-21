"""Scan history persistence.

Each completed scan is saved as a JSON file in the history directory.
Writes are atomic (temp-file + rename) so a crash never corrupts the
store.  Reads skip corrupt files silently.  The store is capped at 50
records — the oldest entry is evicted before a new one is written.

Public API:
    - :func:`save_scan` — atomically persist a :class:`ScanResult`.
    - :func:`load_history` — return all records, newest first.
    - :func:`get_latest` — return the most recent record, or ``None``.
    - :func:`get_by_id` — return a record by ``scan_id``, or ``None``.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

from ecdat_core.models import ScanResult
from ecdat.services.paths import history_dir

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_RECORDS = 50

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def save_scan(result: ScanResult) -> None:
    """Atomically persist *result* to the history directory.

    This function **never raises** — any failure is logged to stderr and
    silently swallowed so a scan never fails because of history I/O.

    Before writing, the oldest record is evicted if the store already holds
    :data:`_MAX_RECORDS` entries.

    Args:
        result: The completed scan result to persist.
    """
    try:
        _evict_oldest()
    except OSError:
        # Eviction is best-effort — don't block the save.
        pass

    try:
        dest_dir = history_dir()
        dest_file = dest_dir / f"{result.scan_id}.json"

        # Atomic write: dump to a temp file in the same directory, then rename.
        fd, tmp_path = tempfile.mkstemp(
            suffix=".json", prefix=".history-", dir=str(dest_dir)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(result.model_dump_json(indent=2))
                f.write("\n")
            os.replace(tmp_path, str(dest_file))
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except (OSError, TypeError, ValueError) as exc:
        print(
            f"Warning: failed to save scan to history: {exc}",
            file=sys.stderr,
        )


def load_history() -> list[ScanResult]:
    """Load all scan records from the history directory.

    Records are returned newest-first (by ``scanned_at`` timestamp).
    Corrupt or unparseable files are skipped with a warning on stderr.

    Returns:
        A list of :class:`ScanResult` objects, possibly empty.
    """
    dest_dir = history_dir()
    results: list[ScanResult] = []

    # Collect .json files sorted by mtime (newest first) for a fast-path
    # ordering before falling back to scanned_at.
    json_files = sorted(
        dest_dir.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    for path in json_files:
        if path.name.startswith("."):
            continue  # skip dotfiles / temp files
        try:
            raw = path.read_text(encoding="utf-8")
            result = ScanResult.model_validate_json(raw)
            results.append(result)
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            print(
                f"Warning: skipping corrupt history file {path.name}: {exc}",
                file=sys.stderr,
            )

    # Ensure sorted by scanned_at (in case mtime order is misleading).
    results.sort(key=lambda r: r.scanned_at, reverse=True)
    return results


def get_latest() -> Optional[ScanResult]:
    """Return the most recent scan from history.

    Returns:
        The newest :class:`ScanResult`, or ``None`` if history is empty.
    """
    records = load_history()
    return records[0] if records else None


def get_by_id(scan_id: str) -> Optional[ScanResult]:
    """Return the scan with the given *scan_id*.

    Args:
        scan_id: The UUID of the scan to retrieve.

    Returns:
        The matching :class:`ScanResult`, or ``None`` if not found.
    """
    dest_dir = history_dir()
    path = dest_dir / f"{scan_id}.json"
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        return ScanResult.model_validate_json(raw)
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        print(
            f"Warning: corrupt history file {path.name}: {exc}",
            file=sys.stderr,
        )
        return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _evict_oldest() -> None:
    """Remove the oldest history record(s) if the store exceeds :data:`_MAX_RECORDS`.

    Oldest is determined by file modification time, not ``scanned_at``,
    because the file can be read without deserialising it.
    """
    dest_dir = history_dir()
    json_files = sorted(
        dest_dir.glob("[!.]*.json"),
        key=lambda p: p.stat().st_mtime,
    )

    excess = len(json_files) - (_MAX_RECORDS - 1)  # -1 for the new record
    if excess <= 0:
        return

    for path in json_files[:excess]:
        try:
            path.unlink()
        except OSError:
            pass