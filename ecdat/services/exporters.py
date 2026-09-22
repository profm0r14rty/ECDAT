"""Markdown and HTML exporters for ECDAT scan results.
 
Public API:
    - :func:`export_markdown` — produce a Markdown report string.
    - :func:`export_html` — produce a standalone HTML page (zero scripts).
    - :func:`write_bundle` — atomically write a multi-format report bundle to disk.
"""

from __future__ import annotations

import html as _html
import json
import os
import tempfile
from pathlib import Path

from ecdat_core.cbom_export import export_cbom, export_summary
from ecdat_core.models import Detection, RiskAssessment, ScanResult
from ecdat.services.viewmodel import ScanVM

# ---------------------------------------------------------------------------
# Markdown safe-string helpers
# ---------------------------------------------------------------------------


def _md_escape(text: str) -> str:
    """Escape a string for safe inclusion in a Markdown table cell.

    Replaces ``|`` with ``\\|``, newlines with ``<br>``, and backslash-escapes
    leading characters that would be interpreted as Markdown block markers
    (``#``, ``>``, ``-``, ``*``, ``+``).
    """
    text = text.replace("\\", "\\\\")
    text = text.replace("|", "\\|")
    text = text.replace("\r\n", "<br>")
    text = text.replace("\n", "<br>")
    text = text.replace("\r", "<br>")
    # Escape leading block markers.
    if text and text[0] in "#>-*+":
        text = "\\" + text
    return text


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------


def export_markdown(result: ScanResult) -> str:
    """Export a :class:`ScanResult` as a Markdown report.

    Tables use safe escaping for ``|``, newlines, and leading ``#>-*``
    characters so that user-controlled content (file paths, matched text)
    never breaks the Markdown structure.

    Args:
        result: The scan result to export.

    Returns:
        A Markdown string.
    """
    lines: list[str] = []

    # Title
    lines.append("# ECDAT Scan Report")
    lines.append("")

    # Scan info
    lines.append("## Scan Information")
    lines.append("")
    lines.append(f"| Field | Value |")
    lines.append(f"|-------|-------|")
    lines.append(f"| Scan ID | `{_md_escape(result.scan_id)}` |")
    lines.append(f"| Target | `{_md_escape(result.target)}` |")
    lines.append(f"| Scanned at | {_md_escape(result.scanned_at)} |")
    lines.append(f"| Files scanned | {result.files_scanned} |")
    lines.append(f"| Detections | {len(result.detections)} |")
    lines.append("")

    # Risk summary
    risk_counts: dict[str, int] = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "quantum-safe": 0,
    }
    for ra in result.risk_assessments:
        risk_counts[ra.risk_level] = risk_counts.get(ra.risk_level, 0) + 1

    lines.append("## Risk Summary")
    lines.append("")
    lines.append(f"| Risk Level | Count |")
    lines.append(f"|------------|-------|")
    for level in ("critical", "high", "medium", "low", "quantum-safe"):
        lines.append(f"| {level.capitalize()} | {risk_counts[level]} |")
    lines.append("")

    # Detections table
    if result.detections:
        lines.append("## Detections")
        lines.append("")
        lines.append(
            "| # | File | Algorithm | Key Size | Quantum Vuln | Classical Broken | Confidence | Risk |"
        )
        lines.append(
            "|---|------|-----------|----------|--------------|------------------|------------|------|"
        )

        # Build lookup maps
        risk_lookup: dict[str, RiskAssessment] = {
            ra.detection_id: ra for ra in result.risk_assessments
        }

        for i, det in enumerate(result.detections, start=1):
            ra = risk_lookup.get(det.id)
            risk_level = ra.risk_level if ra else "—"
            key_size = str(det.key_size_bits) if det.key_size_bits is not None else "—"
            lines.append(
                f"| {i} "
                f"| `{_md_escape(det.file_path)}` "
                f"| {_md_escape(det.algorithm_family)} "
                f"| {key_size} "
                f"| {str(det.quantum_vulnerable).lower()} "
                f"| {str(det.classically_broken).lower()} "
                f"| {det.confidence:.2f} "
                f"| {_md_escape(risk_level)} |"
            )
        lines.append("")

    # Recommendations
    if result.recommendations:
        rec_lookup: dict[str, str] = {}
        for rec in result.recommendations:
            name = rec.recommended_algorithm or "—"
            nist = rec.fips_reference or "—"
            rec_lookup[rec.detection_id] = f"{name} ({nist})"

        lines.append("## Recommendations")
        lines.append("")
        for det in result.detections:
            rec_text = rec_lookup.get(det.id, "—")
            lines.append(
                f"- **{_md_escape(det.algorithm_family)}** "
                f"({_md_escape(det.file_path)}:{det.line_number}) "
                f"→ {_md_escape(rec_text)}"
            )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML theme palette (inline, zero external resources)
# ---------------------------------------------------------------------------

_CSS = """\
:root {
  --bg: #0d1117;
  --fg: #c9d1d9;
  --accent: #58a6ff;
  --border: #30363d;
  --row-alt: #161b22;
  --critical: #f85149;
  --high: #d29922;
  --medium: #58a6ff;
  --low: #3fb950;
  --safe: #8b949e;
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: var(--font);
  background: var(--bg);
  color: var(--fg);
  line-height: 1.6;
  padding: 2rem;
  max-width: 960px;
  margin: 0 auto;
}
h1 { border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1rem; }
h2 { margin: 1.5rem 0 0.75rem; }
table { width: 100%; border-collapse: collapse; margin: 0.75rem 0; }
th, td { padding: 0.5rem 0.75rem; text-align: left; border: 1px solid var(--border); }
th { background: var(--row-alt); font-weight: 600; }
tr:nth-child(even) td { background: var(--row-alt); }
td code { background: rgba(110,118,129,0.2); padding: 0.15em 0.4em; border-radius: 3px; font-size: 0.9em; }
ul { padding-left: 1.5rem; margin: 0.5rem 0; }
li { margin: 0.25rem 0; }
.risk-critical { color: var(--critical); font-weight: 600; }
.risk-high { color: var(--high); font-weight: 600; }
.risk-medium { color: var(--medium); }
.risk-low { color: var(--low); }
.risk-safe { color: var(--safe); }
.footer { margin-top: 2rem; padding-top: 1rem; border-top: 1px solid var(--border); font-size: 0.85em; color: var(--safe); }
"""


def _risk_css_class(risk_level: str) -> str:
    """Map a risk level to its CSS class name."""
    mapping = {
        "critical": "risk-critical",
        "high": "risk-high",
        "medium": "risk-medium",
        "low": "risk-low",
        "quantum-safe": "risk-safe",
    }
    return mapping.get(risk_level, "")


# ---------------------------------------------------------------------------
# HTML export
# ---------------------------------------------------------------------------


def export_html(result: ScanResult) -> str:
    """Export a :class:`ScanResult` as a standalone HTML page.

    The output contains **zero ``<script>`` elements**, a Content-Security-Policy
    ``<meta>`` tag, and all styling is inline CSS.  Every user-controlled value
    is escaped via :func:`html.escape` with ``quote=True``.

    Args:
        result: The scan result to export.

    Returns:
        A complete HTML document string.
    """
    esc = _html.escape
    quote_esc = lambda s: _html.escape(s, quote=True)

    risk_counts: dict[str, int] = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "quantum-safe": 0,
    }
    for ra in result.risk_assessments:
        risk_counts[ra.risk_level] = risk_counts.get(ra.risk_level, 0) + 1

    risk_lookup: dict[str, RiskAssessment] = {
        ra.detection_id: ra for ra in result.risk_assessments
    }

    # Build detections table rows.
    detection_rows: list[str] = []
    for i, det in enumerate(result.detections, start=1):
        ra = risk_lookup.get(det.id)
        risk_level = ra.risk_level if ra else "—"
        css_cls = _risk_css_class(risk_level)
        key_size = str(det.key_size_bits) if det.key_size_bits is not None else "—"
        detection_rows.append(
            f"<tr>"
            f"<td>{i}</td>"
            f"<td><code>{esc(det.file_path)}</code></td>"
            f"<td>{esc(det.algorithm_family)}</td>"
            f"<td>{key_size}</td>"
            f"<td>{str(det.quantum_vulnerable).lower()}</td>"
            f"<td>{str(det.classically_broken).lower()}</td>"
            f"<td>{det.confidence:.2f}</td>"
            f'<td class="{css_cls}">{esc(risk_level)}</td>'
            f"</tr>"
        )

    # Build recommendations list.
    rec_items: list[str] = []
    for det in result.detections:
        rec_text = "—"
        for rec in result.recommendations:
            if rec.detection_id == det.id:
                name = rec.recommended_algorithm or "—"
                nist = rec.fips_reference or ""
                rec_text = f"{esc(name)}" + (f" ({esc(nist)})" if nist else "")
                break
        rec_items.append(
            f"<li><strong>{esc(det.algorithm_family)}</strong> "
            f"({esc(det.file_path)}:{det.line_number}) → {rec_text}</li>"
        )

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ECDAT Scan Report — {quote_esc(result.target)}</title>
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'self';">
<style>
{_CSS}
</style>
</head>
<body>

<h1>ECDAT Scan Report</h1>

<h2>Scan Information</h2>
<table>
<tr><th>Field</th><th>Value</th></tr>
<tr><td>Scan ID</td><td><code>{esc(result.scan_id)}</code></td></tr>
<tr><td>Target</td><td><code>{esc(result.target)}</code></td></tr>
<tr><td>Scanned at</td><td>{esc(result.scanned_at)}</td></tr>
<tr><td>Files scanned</td><td>{result.files_scanned}</td></tr>
<tr><td>Detections</td><td>{len(result.detections)}</td></tr>
</table>

<h2>Risk Summary</h2>
<table>
<tr><th>Risk Level</th><th>Count</th></tr>
<tr><td class="risk-critical">Critical</td><td>{risk_counts['critical']}</td></tr>
<tr><td class="risk-high">High</td><td>{risk_counts['high']}</td></tr>
<tr><td class="risk-medium">Medium</td><td>{risk_counts['medium']}</td></tr>
<tr><td class="risk-low">Low</td><td>{risk_counts['low']}</td></tr>
<tr><td class="risk-safe">Quantum-safe</td><td>{risk_counts['quantum-safe']}</td></tr>
</table>

{"<h2>Detections</h2><table><tr><th>#</th><th>File</th><th>Algorithm</th><th>Key Size</th><th>Quantum Vuln</th><th>Classical Broken</th><th>Confidence</th><th>Risk</th></tr>" + "\n".join(detection_rows) + "</table>" if result.detections else "<p>No detections found.</p>"}

{"<h2>Recommendations</h2><ul>" + "\n".join(rec_items) + "</ul>" if result.recommendations else ""}

<div class="footer">
Generated by ECDAT — Enterprise Cryptographic Discovery &amp; Analysis Tool
</div>

</body>
</html>"""


# ---------------------------------------------------------------------------
# Multi-format bundle writer
# ---------------------------------------------------------------------------

# Mapping from format name → (filename, writer callable).
# Each writer receives ``result`` and returns the file content as a string.
_BUNDLE_FORMATS: dict[str, tuple[str, object]] = {
    "cbom": ("cbom.json", lambda r: json.dumps(export_cbom(r), indent=2, sort_keys=True) + "\n"),
    "summary": ("summary.json", lambda r: json.dumps(export_summary(r), indent=2, sort_keys=True) + "\n"),
    "markdown": ("report.md", export_markdown),
    "html": ("report.html", export_html),
}


def write_bundle(
    result: ScanResult,
    vm: ScanVM,
    out_dir: str | Path,
    formats: tuple[str, ...] = ("cbom", "summary", "markdown", "html"),
) -> list[Path]:
    """Atomically write a multi-format report bundle to *out_dir*.

    Creates *out_dir* (including parents) if it does not already exist, then
    writes the requested format files using atomic temp-file + rename, so a
    crash never leaves a partial file behind.

    Args:
        result: The :class:`~ecdat_core.models.ScanResult` to export.
        vm: The :class:`~ecdat.services.viewmodel.ScanVM` view-model
            (available for future format writers; currently unused by the
            built-in formats).
        out_dir: Destination directory (created if necessary).
        formats: Which formats to write.  Unknown format names are silently
            ignored.  Defaults to all four built-in formats.

    Returns:
        The list of written :class:`~pathlib.Path` objects, in the order of
        the *formats* argument and deduplicated by format name.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    seen: set[str] = set()

    for fmt_name in formats:
        if fmt_name in seen:
            continue
        entry = _BUNDLE_FORMATS.get(fmt_name)
        if entry is None:
            continue  # unknown format → silently skip
        seen.add(fmt_name)

        filename, writer = entry
        content = writer(result)

        # Atomic write: temp file in the destination dir, then os.replace.
        fd, tmp_path = tempfile.mkstemp(
            suffix=".tmp", prefix=f".{filename}-", dir=str(out)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            dest = out / filename
            os.replace(tmp_path, str(dest))
            written.append(dest)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    return written