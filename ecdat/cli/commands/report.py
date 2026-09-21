"""``ecdat report`` — show a Markdown or HTML report for a scan."""

from __future__ import annotations

import sys

from ecdat.services.exporters import export_html, export_markdown
from ecdat.services.history import get_by_id, get_latest


def run(args: object) -> int:
    """Execute the ``report`` subcommand.

    Args:
        args: Parsed arguments with attributes ``scan_ref`` and ``format``.

    Returns:
        Exit code (0 on success, 1 if scan not found, 2 on usage error).
    """
    scan_ref: str = args.scan_ref  # type: ignore[union-attr]
    fmt: str = args.format  # type: ignore[union-attr]

    if scan_ref == "latest":
        result = get_latest()
    else:
        result = get_by_id(scan_ref)

    if result is None:
        if scan_ref == "latest":
            print("Error: no scan history found", file=sys.stderr)
        else:
            print(f"Error: scan {scan_ref!r} not found in history", file=sys.stderr)
        return 1

    if fmt == "markdown":
        sys.stdout.write(export_markdown(result))
    elif fmt == "html":
        sys.stdout.write(export_html(result))
    else:
        print(f"Error: unknown format {fmt!r}", file=sys.stderr)
        return 2

    return 0