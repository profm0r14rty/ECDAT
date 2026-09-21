"""ECDAT CLI argument parser.

Builds the argparse tree shared by all subcommands.

Public API:
    - :func:`build_parser` — return the configured ArgumentParser.
"""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Build and return the ECDAT CLI argument parser.

    Returns:
        An ``ArgumentParser`` with subcommands ``scan``, ``history``,
        and ``report`` already registered.
    """
    parser = argparse.ArgumentParser(
        prog="ecdat",
        description="Enterprise Cryptographic Discovery & Analysis Tool",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- scan ---------------------------------------------------------------
    scan_parser = sub.add_parser("scan", help="Scan a directory or git repo")
    scan_parser.add_argument(
        "path",
        help="Local directory path, or git URL with --git-url",
    )
    scan_parser.add_argument(
        "--git-url",
        action="store_true",
        help="Treat PATH as a git repository URL to clone",
    )
    scan_parser.add_argument(
        "--no-history",
        action="store_true",
        help="Do not save this scan to history",
    )
    scan_parser.add_argument(
        "-o",
        metavar="OUTPUT_DIR",
        dest="output_dir",
        default=None,
        help="Write full output bundle (cbom.json, summary.json, report.md, "
             "report.html) to OUTPUT_DIR instead of CWD",
    )
    scan_parser.add_argument(
        "-f",
        metavar="FORMAT",
        dest="format",
        choices=["json", "cbom", "summary", "markdown", "html"],
        default="summary",
        help="Payload format when no -o is given (default: summary)",
    )

    # ---- history ------------------------------------------------------------
    history_parser = sub.add_parser("history", help="Show scan history")

    # ---- report -------------------------------------------------------------
    report_parser = sub.add_parser("report", help="Show a report for a scan")
    report_parser.add_argument(
        "scan_ref",
        help="'latest' or a scan ID",
    )
    report_parser.add_argument(
        "-f",
        "--format",
        choices=["markdown", "html"],
        default="markdown",
        dest="format",
        help="Output format (default: markdown)",
    )

    return parser