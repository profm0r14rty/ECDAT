"""Command-line interface and scan orchestrator for ECDAT.

Public API:
    - :func:`run_scan` — orchestrate a full scan (ingest -> detect -> assess
      -> recommend -> assemble) and return a :class:`ScanResult`.
    - :func:`main` — console entrypoint for both the ``ecdat`` command
      (registered via ``[project.scripts]`` in pyproject.toml as
      ``ecdat = "ecdat_core.cli:main"``) and the ``python -m ecdat_core.cli``
      module invocation. Argparse resolves ``argv=None`` to ``sys.argv[1:]``,
      so the setuptools-generated wrapper calling ``main()`` with no arguments
      behaves identically to the module form.

The ``scan`` subcommand runs :func:`run_scan` over a local directory or git
URL, writes ``cbom.json`` and ``summary.json`` to the current working
directory, and prints a human-readable summary table to stdout.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ecdat_core.cbom_export import export_cbom, export_summary
from ecdat_core.detector import scan_file_content
from ecdat_core.ingestion import ingest_git_url, ingest_local_directory
from ecdat_core.models import Detection, ScanResult
from ecdat_core.progress import (
    ProgressCallback,
    ScanCancelled,
    ScanProgress,
    ScanStage,
)
from ecdat_core.recommender import recommend
from ecdat_core.risk_engine import assess_risk
from ecdat_core.signature_loader import SignatureEntry, get_all_signatures

_RISK_ORDER = ("critical", "high", "medium", "low", "quantum-safe")


def run_scan(
    target: str,
    is_git_url: bool = False,
    *,
    on_progress: ProgressCallback | None = None,
    exclude: Sequence[str] = (),
) -> ScanResult:
    """Orchestrate a full ECDAT scan and return the assembled result.

    Args:
        target: A local directory path, or a Git repository URL when
            ``is_git_url`` is ``True``.
        is_git_url: When ``True``, treat *target* as a Git URL to shallow
            clone before scanning.
        on_progress: Optional callback receiving :class:`ScanProgress`
            snapshots at each pipeline stage.  Raising :class:`ScanCancelled`
            inside the callback aborts the scan cleanly.  Callback exceptions
            other than ``ScanCancelled`` propagate unchanged.
        exclude: ``fnmatch`` glob patterns passed through to
            :func:`ingest_local_directory`.

    Returns:
        A fully populated :class:`ScanResult` with detections, risk
        assessments, and recommendations.

    Raises:
        ScanCancelled: When the caller's callback raises it.
    """
    clone_dir: str | None = None

    def _emit(stage: ScanStage, message: str = "", current: int = 0,
              total: int | None = None, detections: int = 0) -> None:
        if on_progress is None:
            return
        on_progress(ScanProgress(
            stage=stage,
            message=message,
            current=current,
            total=total,
            detections=detections,
        ))

    try:
        # --- clone -----------------------------------------------------
        if is_git_url:
            scan_target = target
            _emit("clone", f"Cloning {target}")
            clone_dir = ingest_git_url(target)
            local_path = clone_dir
            sandboxed = False
            _emit("clone", f"Cloned {target}", 1, 1)
        else:
            scan_target = str(Path(target).resolve())
            local_path = target
            sandboxed = True

        signatures = _signature_lookup()

        # --- ingest ----------------------------------------------------
        _emit("ingest", "Walking directory tree...")
        detections: list[Detection] = []
        files_scanned = 0

        # First pass: count files (optional total for detect stage).
        file_list: list[tuple[str, str, str]] = []
        for file_path, content, language in ingest_local_directory(
            local_path, sandboxed=sandboxed, exclude=exclude
        ):
            file_list.append((file_path, content, language))

        total_files = len(file_list) or None
        _emit("ingest", f"Directory walk complete: {len(file_list)} files", len(file_list), total_files)

        # --- detect ----------------------------------------------------
        _emit("detect", "Scanning files for crypto artefacts...",
              current=0, total=total_files, detections=0)
        for idx, (file_path, content, language) in enumerate(file_list, start=1):
            files_scanned = idx
            new_dets = scan_file_content(file_path, content, language)
            detections.extend(new_dets)
            _emit("detect", f"Scanning: {file_path}",
                  current=idx, total=total_files, detections=len(detections))
        _emit("detect", "Detection complete",
              current=files_scanned, total=total_files, detections=len(detections))

        # --- assess ----------------------------------------------------
        total_dets = len(detections) or None
        _emit("assess", "Assessing risk...",
              current=0, total=total_dets, detections=len(detections))
        risk_assessments = []
        recommendations = []
        for i, detection in enumerate(detections, start=1):
            entry = signatures.get(detection.algorithm_family)
            if entry is None:
                continue
            risk_assessments.append(assess_risk(detection, entry))
            recommendations.append(recommend(detection, entry))
            _emit("assess", f"Assessed: {detection.algorithm_family}",
                  current=i, total=total_dets, detections=len(detections))

        # --- recommend -------------------------------------------------
        _emit("recommend", "Generating recommendations...",
              current=0, total=total_dets, detections=len(detections))
        _emit("recommend", "Recommendations complete",
              current=total_dets, total=total_dets, detections=len(detections))

        # --- assemble --------------------------------------------------
        _emit("assemble", "Assembling result...", detections=len(detections))
        result = ScanResult(
            scan_id=str(uuid4()),
            target=scan_target,
            detections=detections,
            risk_assessments=risk_assessments,
            recommendations=recommendations,
            scanned_at=datetime.now(timezone.utc).isoformat(),
            files_scanned=files_scanned,
        )
        _emit("done", "Scan complete", total=files_scanned,
              detections=len(detections))

    except ScanCancelled:
        raise
    finally:
        if clone_dir is not None:
            shutil.rmtree(clone_dir, ignore_errors=True)

    return result


def _signature_lookup() -> dict[str, SignatureEntry]:
    """Return a map of signature name -> entry for fast lookups."""
    return {entry.name: entry for entry in get_all_signatures()}


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
