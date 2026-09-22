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


def test_html_detections_and_recommendations_sections_are_byte_exact() -> None:
    """Pin the exact rendered Detections/Recommendations sections.

    These sections are built by joining rows with ``"\\n"``. They used to be
    assembled inline inside the HTML f-string, which put a backslash in an
    f-string replacement field -- syntax that only parses on Python 3.12+
    (PEP 701) and broke import on 3.10/3.11. The join now happens in plain
    locals, so this test also serves as the regression guard: the rendered
    bytes must not change.
    """
    from datetime import datetime, timezone

    from ecdat_core.models import Detection, Recommendation, RiskAssessment

    dets = [
        Detection(
            id="d1",
            file_path="src/a.py",
            line_number=3,
            matched_text="RSA",
            asset_type="algorithm",
            algorithm_family="RSA",
            key_size_bits=2048,
            quantum_vulnerable=True,
            classically_broken=False,
            confidence=0.9,
            language="python",
            detection_method="regex",
        ),
        Detection(
            id="d2",
            file_path="src/b.py",
            line_number=7,
            matched_text="MD5",
            asset_type="algorithm",
            algorithm_family="MD5",
            key_size_bits=None,
            quantum_vulnerable=False,
            classically_broken=True,
            confidence=0.5,
            language="python",
            detection_method="regex",
        ),
    ]
    ras = [
        RiskAssessment(
            detection_id="d1",
            migration_time_years=3.0,
            shelf_life_years=5.0,
            threat_horizon_years=8.0,
            urgency_ratio=1.0,
            risk_level="critical",
            mosca_violation=True,
        ),
        RiskAssessment(
            detection_id="d2",
            migration_time_years=0.5,
            shelf_life_years=0.5,
            threat_horizon_years=10.0,
            urgency_ratio=0.1,
            risk_level="quantum-safe",
            mosca_violation=False,
        ),
    ]
    recs = [
        Recommendation(
            detection_id="d1",
            recommended_algorithm="ML-KEM-768",
            fips_reference="FIPS 203",
            rationale="Replace RSA with ML-KEM.",
            latency_note="fast",
            migration_note="swap",
        ),
        Recommendation(
            detection_id="d2",
            recommended_algorithm="SHA-256",
            fips_reference="FIPS 180-4",
            rationale="Replace MD5.",
            latency_note="fast",
            migration_note="swap",
        ),
    ]
    result = ScanResult(
        scan_id="scan-1",
        target="relative/path",
        detections=dets,
        risk_assessments=ras,
        recommendations=recs,
        scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        files_scanned=2,
    )

    html = export_html(result)

    expected_detections = (
        "<h2>Detections</h2><table>"
        "<tr><th>#</th><th>File</th><th>Algorithm</th><th>Key Size</th>"
        "<th>Quantum Vuln</th><th>Classical Broken</th>"
        "<th>Confidence</th><th>Risk</th></tr>"
        '<tr><td>1</td><td><code>src/a.py</code></td><td>RSA</td>'
        '<td>2048</td><td>true</td><td>false</td><td>0.90</td>'
        '<td class="risk-critical">critical</td></tr>\n'
        '<tr><td>2</td><td><code>src/b.py</code></td><td>MD5</td>'
        '<td>\u2014</td><td>false</td><td>true</td><td>0.50</td>'
        '<td class="risk-safe">quantum-safe</td></tr></table>'
    )
    expected_recommendations = (
        "<h2>Recommendations</h2><ul>"
        "<li><strong>RSA</strong> (src/a.py:3) \u2192 ML-KEM-768 (FIPS 203)</li>\n"
        "<li><strong>MD5</strong> (src/b.py:7) \u2192 SHA-256 (FIPS 180-4)</li>"
        "</ul>"
    )

    assert expected_detections in html
    assert expected_recommendations in html


def test_html_empty_result_neither_section_is_rendered() -> None:
    """An empty scan renders the fallback paragraph and no recommendations block."""
    from datetime import datetime, timezone

    result = ScanResult(
        scan_id="scan-empty",
        target="relative/path",
        detections=[],
        risk_assessments=[],
        recommendations=[],
        scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        files_scanned=0,
    )

    html = export_html(result)

    assert "<p>No detections found.</p>" in html
    assert "<h2>Recommendations</h2>" not in html