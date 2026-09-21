"""``ecdat history`` — list saved scan records."""

from __future__ import annotations

import sys

from ecdat.services.history import load_history


def run(args: object) -> int:
    """Execute the ``history`` subcommand.

    Args:
        args: Parsed arguments (unused for history — no options).

    Returns:
        Exit code (always 0).
    """
    records = load_history()

    if not records:
        print("No scan history found.", file=sys.stderr)
        return 0

    # Header
    header = f"{'#':<4} {'Scan ID':<38} {'Target':<36} {'Detections':>10} {'Scanned at'}"
    print(header)
    print("-" * len(header))

    for i, rec in enumerate(records, start=1):
        # Truncate long fields.
        scan_id = rec.scan_id[:36]
        target = rec.target[:34] + ".." if len(rec.target) > 36 else rec.target
        detections = str(len(rec.detections))
        scanned = rec.scanned_at[:19]  # ISO datetime (no TZ offset detail)

        print(f"{i:<4} {scan_id:<38} {target:<36} {detections:>10} {scanned}")

    return 0