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
        ``report``, ``rules``, ``explain``, and ``mosca`` already registered.
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

    # ---- rules --------------------------------------------------------------
    rules_parser = sub.add_parser(
        "rules", help="Browse the cryptographic signature knowledge base"
    )
    rules_parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Case-insensitive substring over signature name/family",
    )
    rules_parser.add_argument(
        "--family",
        default=None,
        help="Only signatures whose family contains this value",
    )
    rules_parser.add_argument(
        "--language",
        default=None,
        help="Only signatures with detection patterns for this language",
    )
    rules_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the results as JSON on stdout",
    )

    # ---- explain ------------------------------------------------------------
    explain_parser = sub.add_parser(
        "explain", help="Explain an algorithm in plain English"
    )
    explain_parser.add_argument(
        "name",
        help="Signature name or family to explain (case-insensitive)",
    )

    # ---- mosca --------------------------------------------------------------
    mosca_parser = sub.add_parser(
        "mosca", help="Mosca's-inequality calculator with a visual timeline"
    )
    mosca_parser.add_argument(
        "-x",
        "--shelf-life",
        type=float,
        default=None,
        dest="x",
        help="X — data lifetime in years (data must stay secret)",
    )
    mosca_parser.add_argument(
        "-y",
        "--migration",
        type=float,
        default=None,
        dest="y",
        help="Y — migration time in years",
    )
    mosca_parser.add_argument(
        "-z",
        "--threat",
        type=float,
        default=None,
        dest="z",
        help="Z — quantum threat horizon in years",
    )

    return parser