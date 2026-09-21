"""Tests for ecdat.services.exporters."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ecdat.services.exporters import export_html, export_markdown
from ecdat_core.cli import run_scan
from ecdat_core.models import ScanResult


@pytest.fixture(scope="module")
def demo_result() -> ScanResult:
    """Run a scan against the demo fixture once for all exporter tests."""
    fixture_root = (
        Path(__file__).resolve().parents[2]
        / "ecdat_core" / "tests" / "fixtures" / "demo_repo"
    )
    import os
    os.environ["SCAN_WORKSPACE_ROOT"] = str(fixture_root.parent)
    return run_scan(str(fixture_root))


# ---- Markdown ------------------------------------------------------------


def test_markdown_has_title(demo_result: ScanResult) -> None:
    md = export_markdown(demo_result)
    assert md.startswith("# ECDAT Scan Report")


def test_markdown_has_scan_info(demo_result: ScanResult) -> None:
    md = export_markdown(demo_result)
    assert demo_result.scan_id in md
    assert "## Scan Information" in md


def test_markdown_escapes_pipe() -> None:
    """Pipe characters in file paths must be escaped."""
    from ecdat_core.models import Detection
    det = Detection(
        file_path="src/a|b.py",
        line_number=1,
        matched_text="md5",
        asset_type="algorithm",
        algorithm_family="MD5",
        quantum_vulnerable=False,
        classically_broken=True,
        confidence=0.9,
        language="python",
        detection_method="regex",
    )
    from datetime import datetime, timezone
    result = ScanResult(
        scan_id="test-id",
        target="/tmp",
        detections=[det],
        risk_assessments=[],
        recommendations=[],
        scanned_at=datetime.now(timezone.utc).isoformat(),
        files_scanned=1,
    )
    md = export_markdown(result)
    assert "a\\|b" in md
    assert "a|b.py" not in md  # unescaped pipe must not appear


def test_markdown_escapes_leading_hash() -> None:
    """Leading # must be escaped to avoid accidental headings."""
    from ecdat_core.models import Detection
    det = Detection(
        file_path="src/test.py",
        line_number=1,
        matched_text="## heading",
        asset_type="algorithm",
        algorithm_family="#evil",
        quantum_vulnerable=False,
        confidence=0.5,
        language="python",
        detection_method="regex",
    )
    from datetime import datetime, timezone
    result = ScanResult(
        scan_id="test-id",
        target="/tmp",
        detections=[det],
        risk_assessments=[],
        recommendations=[],
        scanned_at=datetime.now(timezone.utc).isoformat(),
        files_scanned=1,
    )
    md = export_markdown(result)
    # The escaped version should appear; bare # at start of line after pipe should not.
    assert "\\#evil" in md or "\\\\#evil" in md


def test_markdown_has_table_structure(demo_result: ScanResult) -> None:
    md = export_markdown(demo_result)
    assert "|---" in md  # at least one table separator


# ---- HTML ----------------------------------------------------------------


def test_html_has_doctype(demo_result: ScanResult) -> None:
    html = export_html(demo_result)
    assert html.strip().startswith("<!DOCTYPE html>")


def test_html_has_no_script_tags(demo_result: ScanResult) -> None:
    html = export_html(demo_result)
    assert "<script" not in html.lower()


def test_html_has_csp_meta(demo_result: ScanResult) -> None:
    html = export_html(demo_result)
    assert 'http-equiv="Content-Security-Policy"' in html
    assert "default-src 'none'" in html


def test_html_has_inline_css(demo_result: ScanResult) -> None:
    html = export_html(demo_result)
    assert "<style>" in html
    assert "font-family" in html


def test_html_escapes_content(demo_result: ScanResult) -> None:
    """Raw angle brackets in user content must be html-escaped."""
    from ecdat_core.models import Detection
    det = Detection(
        file_path="<script>alert(1)</script>.py",
        line_number=1,
        matched_text="md5",
        asset_type="algorithm",
        algorithm_family="<evil>",
        quantum_vulnerable=False,
        confidence=0.5,
        language="python",
        detection_method="regex",
    )
    from datetime import datetime, timezone
    result = ScanResult(
        scan_id="test-id",
        target="/tmp",
        detections=[det],
        risk_assessments=[],
        recommendations=[],
        scanned_at=datetime.now(timezone.utc).isoformat(),
        files_scanned=1,
    )
    html = export_html(result)
    assert "&lt;script&gt;" in html
    assert "<script>" not in html
    assert "&lt;evil&gt;" in html


def test_html_has_title(demo_result: ScanResult) -> None:
    html = export_html(demo_result)
    assert "<title>ECDAT Scan Report" in html


def test_html_has_footer(demo_result: ScanResult) -> None:
    html = export_html(demo_result)
    assert "ECDAT" in html  # footer mention