"""``ecdat demo`` — scan the bundled sample project.

A zero-setup "try it now" command: copies the demo project shipped inside the
package to a temporary directory, scans it through the same
:func:`~ecdat.services.scanner.perform_scan` path as ``ecdat scan``, and
renders the usual report.  ``--path`` instead materialises a persistent copy
under ``ECDAT_HOME/demo`` and prints its location.
"""

from __future__ import annotations

import argparse
import json
import sys

NAME = "demo"

_FORMATS = ("pretty", "json", "summary")

_PRETTY_NOTE = "Bundled sample code \u2014 intentionally insecure, never run it."
_LABEL = "demo project (bundled sample)"


def register(subparsers: "argparse._SubParsersAction") -> None:
    """Attach the ``demo`` subcommand to *subparsers*."""
    parser = subparsers.add_parser(
        "demo",
        help="Scan the bundled sample project (zero setup)",
        description=(
            "Scan ECDAT's bundled, deliberately-insecure sample project. "
            "With --path, materialise a persistent copy under ECDAT_HOME/demo "
            "instead of scanning."
        ),
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=_FORMATS,
        default="pretty",
        help="Output format (default: pretty)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=15,
        metavar="N",
        help="Maximum findings shown in the pretty table (default: 15)",
    )
    parser.add_argument(
        "--path",
        action="store_true",
        help="Copy the sample under ECDAT_HOME/demo and print its path",
    )


def run(args) -> int:
    """Run the demo scan (or materialise it); return the process exit code."""
    from rich.style import Style
    from rich.text import Text

    from ecdat.services.paths import home_dir
    from ecdat.ui.console import make_console
    from ecdat.ui.theme import PALETTE

    no_color = True if getattr(args, "no_color", False) else None
    out_console = make_console(no_color=no_color)
    err_console = make_console(stderr=True, no_color=no_color)

    if getattr(args, "path", False):
        from ecdat.services.demo import materialize_demo

        destination = materialize_demo(home_dir() / "demo")
        sys.stdout.write(str(destination) + "\n")
        return 0

    from ecdat.services.demo import demo_project
    from ecdat.services.scanner import classify_target, perform_scan

    with demo_project() as path:
        target = classify_target(str(path))
        outcome = perform_scan(target, label=_LABEL)
        result = outcome.result
        vm = outcome.vm

        output_format = getattr(args, "format", "pretty")
        if output_format == "json":
            _emit_json(result.model_dump(mode="json"))
        elif output_format == "summary":
            from ecdat_core.cbom_export import export_summary

            _emit_json(export_summary(result))
        else:
            _render_pretty(out_console, vm, limit=getattr(args, "limit", 15))

    err_console.print(Text(_PRETTY_NOTE, style=Style(color=PALETTE.muted, dim=True)))
    return 0


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _emit_json(payload: dict) -> None:
    """Write *payload* as pretty JSON to stdout — the ONLY thing on stdout."""
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")


def _render_pretty(console, vm, *, limit: int) -> None:
    """Render the banner plus the standard scan report to stdout."""
    from ecdat import __version__
    from ecdat.ui.banner import render_banner
    from ecdat.ui.render import scan_report

    console.print(render_banner(version=__version__))
    console.print(scan_report(vm, limit=limit))
