"""Command-line interface and scan orchestrator for ECDAT.

Public API:
    - :func:`run_scan` — orchestrate a full scan (ingest -> detect -> assess
      -> recommend -> assemble) and return a :class:`ScanResult`.
    - :func:`main` — console entrypoint for ``python -m ecdat_core.cli``.

The ``scan`` subcommand runs :func:`run_scan` over a local directory or git
URL, writes ``cbom.json`` and ``summary.json`` to the current working
directory, and prints a human-readable summary table to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ecdat_core.cbom_export import export_cbom, export_summary
from ecdat_core.detector import scan_file_content
from ecdat_core.ingestion import ingest_git_url, ingest_local_directory
from ecdat_core.models import Detection, ScanResult
from ecdat_core.recommender import recommend
from ecdat_core.risk_engine import assess_risk
from ecdat_core.signature_loader import SignatureEntry, get_all_signatures

_RISK_ORDER = ("critical", "high", "medium", "low", "quantum-safe")


def run_scan(target: str, is_git_url: bool = False) -> ScanResult:
    """Orchestrate a full ECDAT scan and return the assembled result.

    Args:
        target: A local directory path, or a Git repository URL when
            ``is_git_url`` is ``True``.
        is_git_url: When ``True``, treat *target* as a Git URL to shallow
            clone before scanning.

    Returns:
        A fully populated :class:`ScanResult` with detections, risk
        assessments, and recommendations for every cryptographic artefact
        discovered, plus a ``files_scanned`` count.
    """
    if is_git_url:
        scan_target = target
        local_path = ingest_git_url(target)
    else:
        scan_target = str(Path(target).resolve())
        local_path = target

    signatures = _signature_lookup()

    detections: list[Detection] = []
    files_scanned = 0

    for file_path, content, language in ingest_local_directory(local_path):
        files_scanned += 1
        detections.extend(scan_file_content(file_path, content, language))

    return _assemble(scan_target, detections, signatures, files_scanned)


def _signature_lookup() -> dict[str, SignatureEntry]:
    """Return a map of signature name -> entry for fast lookups."""
    return {entry.name: entry for entry in get_all_signatures()}


def _assemble(
    target: str,
    detections: list[Detection],
    signatures: dict[str, SignatureEntry],
    files_scanned: int,
) -> ScanResult:
    """Assess risk, recommend, and package everything into a ScanResult."""
    risk_assessments = []
    recommendations = []

    for detection in detections:
        entry = signatures.get(detection.algorithm_family)
        if entry is None:
            continue
        risk_assessments.append(assess_risk(detection, entry))
        recommendations.append(recommend(detection, entry))

    return ScanResult(
        scan_id=str(uuid4()),
        target=target,
        detections=detections,
        risk_assessments=risk_assessments,
        recommendations=recommendations,
        scanned_at=datetime.now(timezone.utc).isoformat(),
        files_scanned=files_scanned,
    )


def main(argv: list[str] | None = None) -> int:
    """Run the ECDAT CLI; return a process exit code.

    Args:
        argv: Argument list; defaults to ``sys.argv[1:]``.

    Returns:
        ``0`` on success, ``2`` on argument misuse, ``1`` on scan failure.
    """
    parser = argparse.ArgumentParser(
        prog="ecdat",
        description="Cryptographic Discovery & Analysis Tool",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser(
        "scan", help="Scan a local directory or git repository"
    )
    scan_parser.add_argument(
        "path", help="Local directory path, or git URL with --git-url"
    )
    scan_parser.add_argument(
        "--git-url",
        action="store_true",
        help="Treat PATH as a git repository URL to clone",
    )

    args = parser.parse_args(argv)
    if args.command != "scan":
        parser.error("unknown command")

    try:
        result = run_scan(args.path, is_git_url=args.git_url)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    _write_outputs(result)
    _print_summary(result)
    return 0


def _write_outputs(result: ScanResult) -> None:
    """Write cbom.json and summary.json into the current directory."""
    _write_json("cbom.json", export_cbom(result))
    _write_json("summary.json", export_summary(result))


def _write_json(filename: str, payload: dict) -> None:
    """Write a dict as pretty-printed JSON to *filename* in the cwd."""
    with Path(filename).open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(f"wrote {filename}")


def _print_summary(result: ScanResult) -> None:
    """Print a human-readable scan summary table to stdout."""
    counts = {level: 0 for level in _RISK_ORDER}
    for assessment in result.risk_assessments:
        counts[assessment.risk_level] = counts.get(assessment.risk_level, 0) + 1

    print()
    print(f"Scan target : {result.target}")
    print(f"Files scanned: {result.files_scanned}")
    print(f"Detections  : {len(result.detections)}")
    print("-" * 32)
    print(f"{'Risk level':<16}{'Count':>6}")
    print("-" * 32)
    for level in _RISK_ORDER:
        print(f"{level:<16}{counts[level]:>6}")
    print("-" * 32)


if __name__ == "__main__":
    sys.exit(main())
