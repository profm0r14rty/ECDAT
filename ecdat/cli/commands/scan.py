"""``ecdat scan`` — run a scan and render/emit the result.

The command module is deliberately thin at import time: Rich, the scanner
engine, and the renderers are imported inside :func:`run` so that
``import ecdat.cli`` stays fast and never pulls in UI frameworks.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ecdat.services.viewmodel import ScanVM
    from ecdat_core.models import ScanResult

NAME = "scan"

_FORMATS = ("pretty", "json", "cbom", "summary")

# Most-severe first.  "quantum-safe" is intentionally absent: a quantum-safe
# finding must never trip --fail-on.
_SEVERITY = ("critical", "high", "medium", "low")


def register(subparsers: "argparse._SubParsersAction") -> None:
    """Attach the ``scan`` subcommand to *subparsers*."""
    parser = subparsers.add_parser(
        "scan",
        help="Scan a local directory or git repository",
        description=(
            "Scan a directory (or an https:// Git repository) for "
            "cryptographic artefacts and report their post-quantum risk."
        ),
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Directory to scan, or a Git URL with --git-url (default: .)",
    )
    parser.add_argument(
        "--git-url",
        action="store_true",
        help="Treat TARGET as an https:// Git repository to clone and scan",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=_FORMATS,
        default="pretty",
        help="Output format (default: pretty)",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="DIR",
        default=None,
        help="Also write cbom.json and summary.json into DIR",
    )
    parser.add_argument(
        "--fail-on",
        choices=_SEVERITY,
        default=None,
        metavar="LEVEL",
        help="Exit 1 when a finding is at or above LEVEL "
        "(critical|high|medium|low); quantum-safe findings never count",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Never show the progress spinner",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress banner, progress, and status messages",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=15,
        metavar="N",
        help="Maximum findings shown in the pretty table (default: 15)",
    )


def run(args) -> int:
    """Execute a scan for the parsed *args*; return the process exit code.

    Raises:
        ScanError: Propagated to :func:`ecdat.cli.main`, which maps it to the
            exit code carried on the exception.  ``BrokenPipeError`` and
            ``KeyboardInterrupt`` likewise propagate to ``main``.
    """
    from rich.text import Text

    from ecdat.services.scanner import classify_target, perform_scan
    from ecdat.ui.console import make_console

    no_color = True if getattr(args, "no_color", False) else None
    out_console = make_console(no_color=no_color)
    err_console = make_console(stderr=True, no_color=no_color)

    quiet = bool(getattr(args, "quiet", False))
    target = classify_target(args.target, force_git=args.git_url)

    show_progress = (
        not quiet
        and not getattr(args, "no_progress", False)
        and err_console.is_terminal
    )

    if show_progress:
        with err_console.status("Scanning \u2026", spinner="dots"):
            outcome = perform_scan(target, force_git=args.git_url)
    else:
        outcome = perform_scan(target, force_git=args.git_url)

    result = outcome.result
    vm = outcome.vm

    if args.output:
        _write_outputs(Path(args.output), result, err_console, quiet)

    output_format = args.format
    if output_format == "json":
        _emit_json(result.model_dump(mode="json"))
    elif output_format == "cbom":
        from ecdat_core.cbom_export import export_cbom

        _emit_json(export_cbom(result))
    elif output_format == "summary":
        from ecdat_core.cbom_export import export_summary

        _emit_json(export_summary(result))
    else:
        _render_pretty(out_console, vm, limit=args.limit, quiet=quiet)

    if vm.total == 0 and not quiet:
        err_console.print(
            Text(
                f"Warning: no cryptographic artefacts detected in "
                f"{vm.files_scanned} files.",
                style="yellow",
            ),
        )

    if args.fail_on is not None and _fails_at_or_above(vm, args.fail_on):
        return 1
    return 0


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _emit_json(payload: dict) -> None:
    """Write *payload* as pretty JSON to stdout — the ONLY thing on stdout."""
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")


def _write_outputs(directory: Path, result, err_console, quiet: bool) -> None:
    """Write ``cbom.json`` and ``summary.json`` into *directory* (UTF-8)."""
    from ecdat.services.scanner import ScanError
    from ecdat_core.cbom_export import export_cbom, export_summary

    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ScanError(
            f"Could not create output directory {directory}: {exc}",
            exit_code=3,
        ) from exc

    payloads = (
        ("cbom.json", export_cbom(result)),
        ("summary.json", export_summary(result)),
    )
    for filename, payload in payloads:
        path = directory / filename
        try:
            path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise ScanError(
                f"Could not write {path}: {exc}",
                exit_code=3,
            ) from exc
        if not quiet:
            err_console.print(f"Wrote {path}")


def _render_pretty(
    console,
    vm: "ScanVM",
    *,
    limit: int,
    quiet: bool,
) -> None:
    """Render the banner (unless quiet) and the scan report to stdout."""
    from ecdat import __version__
    from ecdat.ui.banner import render_banner
    from ecdat.ui.render import scan_report

    if not quiet:
        console.print(render_banner(version=__version__))
    console.print(scan_report(vm, limit=limit))


def _fails_at_or_above(vm: "ScanVM", level: str) -> bool:
    """Return ``True`` when any non-quantum-safe finding is at/above *level*."""
    try:
        threshold = _SEVERITY.index(level)
    except ValueError:
        return False
    for finding in vm.findings:
        rank = _SEVERITY.index(finding.risk_level) if finding.risk_level in _SEVERITY else None
        if rank is not None and rank <= threshold:
            return True
    return False
