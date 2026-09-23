"""Scan history persistence.
 
Each completed scan is saved as a JSON file in the history directory.
Writes are atomic (temp-file + rename) so a crash never corrupts the
store.  Reads skip corrupt files silently.  The store is capped at 50
records — the oldest entry is evicted before a new one is written.
 
Public API:
    - :class:`HistoryError` — user-facing error for history operations.
    - :func:`save_scan` — atomically persist a :class:`ScanResult`.
    - :func:`load_history` — return all records, newest first.
    - :func:`get_latest` — return the most recent record, or ``None``.
    - :func:`get_by_id` — return a record by ``scan_id``, or ``None``.
    - :func:`list_scans` — return at most *limit* records, newest first.
    - :func:`load_scan` — resolve a record by ``"latest"``, id, or prefix.
    - :func:`delete_scan` — remove a record from disk.
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
# Exceptions
# ---------------------------------------------------------------------------


class HistoryError(Exception):
    """A user-facing error for history operations.

    Mirrors the simple shape of :class:`ecdat.services.scanner.ScanError`:
    a single human-readable message.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


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


def list_scans(limit: int | None = None) -> list[ScanResult]:
    """Return scan records newest-first, optionally capped at *limit*.

    Built on top of :func:`load_history` — corrupt files are skipped
    silently, matching the existing behaviour.

    Args:
        limit: Maximum number of records to return.  When ``None``,
            all records are returned.

    Returns:
        A list of :class:`ScanResult` objects (possibly empty).
    """
    records = load_history()
    if limit is not None:
        records = records[:limit]
    return records


def load_scan(ref: str = "latest") -> ScanResult:
    """Resolve a scan record by reference.

    The *ref* is resolved in two ways:

    1. ``"latest"`` — returns the newest record.
    2. Otherwise, *ref* is treated as an exact ``scan_id`` **or** a
       unique prefix: every record whose ``scan_id`` starts with *ref*
       is collected.  Exactly one match → returned; zero matches →
       :class:`HistoryError`; more than one → :class:`HistoryError`
       listing the ambiguous candidates (capped at 5).

    Args:
        ref: A scan reference.  Defaults to ``"latest"``.

    Returns:
        The matching :class:`ScanResult`.

    Raises:
        HistoryError: No matching record, or an ambiguous *ref*.
    """
    if ref == "latest":
        record = get_latest()
        if record is None:
            raise HistoryError("No scan history found.")
        return record

    records = load_history()
    candidates = [r for r in records if r.scan_id.startswith(ref)]

    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) == 0:
        raise HistoryError(f'No scan found matching "{ref}".')
    # Ambiguous — list up to 5 candidate ids.
    preview = [r.scan_id for r in candidates[:5]]
    suffix = f" ({len(candidates)} total)" if len(candidates) > 5 else ""
    raise HistoryError(
        f'Ambiguous ref "{ref}" matches {len(candidates)} scans{suffix}: '
        + ", ".join(preview)
    )


def delete_scan(scan_id: str) -> bool:
    """Delete a scan record from the history directory.

    Args:
        scan_id: The UUID of the scan to delete.

    Returns:
        ``True`` if the file existed and was deleted, ``False`` if no
        matching file was found.

    Raises:
        HistoryError: An unexpected filesystem error occurred during
            deletion (e.g. permission denied).
    """
    dest_dir = history_dir()
    path = dest_dir / f"{scan_id}.json"

    # Never delete dotfiles or temp files.
    if path.name.startswith("."):
        return False

    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise HistoryError(
            f"Failed to delete scan {scan_id}: {exc}"
        ) from exc


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