"""``ecdat scan`` — run a scan with Rich progress and optional bundle output."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ecdat.services.scanner import perform_scan
from ecdat.services.exporters import export_html, export_markdown
from ecdat_core.cbom_export import export_cbom, export_summary
from ecdat_core.models import ScanResult


def run(args: object) -> int:
    """Execute the ``scan`` subcommand.

    Args:
        args: Parsed arguments with attributes ``path``, ``git_url``,
              ``no_history``, ``output_dir``, ``format``.

    Returns:
        Exit code (0 on success, 1/2/3 on error).
    """
    target: str = args.path  # type: ignore[union-attr]
    is_git_url: bool = args.git_url  # type: ignore[union-attr]
    no_history: bool = args.no_history  # type: ignore[union-attr]
    output_dir: str | None = args.output_dir  # type: ignore[union-attr]
    fmt: str = args.format  # type: ignore[union-attr]

    # Validate: -o and -f are mutually exclusive in meaning.
    # Actually, the spec says: -o writes full bundle; without -o, -f selects
    # single payload on stdout.  Both can be set (e.g. -o /tmp/out -f html
    # would write bundle to /tmp/out AND print html to stdout — but actually
    # the spec says "-o writes the full bundle" so let's keep them separate.)

    try:
        result = perform_scan(
            target,
            is_git_url=is_git_url,
            save_history=not no_history,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 3

    # --- output ---
    if output_dir is not None:
        _write_bundle(result, Path(output_dir))
    else:
        _write_single_payload(result, fmt)

    return 0


def _write_bundle(result: ScanResult, out_dir: Path) -> None:
    """Write the full bundle: cbom.json, summary.json, report.md, report.html."""
    out_dir.mkdir(parents=True, exist_ok=True)

    _write_json(out_dir / "cbom.json", export_cbom(result))
    _write_json(out_dir / "summary.json", export_summary(result))

    md = export_markdown(result)
    (out_dir / "report.md").write_text(md, encoding="utf-8")

    html = export_html(result)
    (out_dir / "report.html").write_text(html, encoding="utf-8")

    print(f"wrote {out_dir / 'cbom.json'}", file=sys.stderr)
    print(f"wrote {out_dir / 'summary.json'}", file=sys.stderr)
    print(f"wrote {out_dir / 'report.md'}", file=sys.stderr)
    print(f"wrote {out_dir / 'report.html'}", file=sys.stderr)


def _write_single_payload(result: ScanResult, fmt: str) -> None:
    """Write a single payload to stdout based on format."""
    if fmt == "json":
        # Full scan result as JSON.
        payload = result.model_dump_json(indent=2)
        sys.stdout.write(payload)
        sys.stdout.write("\n")
    elif fmt == "cbom":
        payload = json.dumps(export_cbom(result), indent=2, sort_keys=True)
        sys.stdout.write(payload)
        sys.stdout.write("\n")
    elif fmt == "summary":
        payload = json.dumps(export_summary(result), indent=2, sort_keys=True)
        sys.stdout.write(payload)
        sys.stdout.write("\n")
    elif fmt == "markdown":
        sys.stdout.write(export_markdown(result))
    elif fmt == "html":
        sys.stdout.write(export_html(result))
    else:
        # Should not happen — argparse validates.
        print(f"Error: unknown format {fmt!r}", file=sys.stderr)
        sys.exit(2)


def _write_json(path: Path, payload: dict) -> None:
    """Write a dict as pretty-printed JSON to *path*."""
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")