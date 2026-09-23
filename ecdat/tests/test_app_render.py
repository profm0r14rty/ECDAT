"""Tests for render.py — scan report renderers, smooth_bar, hostile content safety."""

from __future__ import annotations

import io
import re

import pytest
from rich.text import Text

from ecdat.services.viewmodel import FindingVM, PriorityAction, ScanVM
from ecdat.ui.console import make_console
from ecdat.ui.render import (
    _ellipsis_path,
    _safe,
    findings_table,
    legend,
    priority_actions_panel,
    recommendations_table,
    risk_bars,
    risk_chip,
    scan_report,
    smooth_bar,
    summary_panel,
)
from ecdat.ui.theme import RISK_COLORS, RISK_LABELS, strip_control_chars


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(
    id: str = "det-1",
    risk_level: str = "critical",
    algorithm: str = "RSA-2048",
    family: str = "RSA",
    file_path: str = "src/main.py",
    line: int = 42,
    language: str = "python",
    confidence: float = 0.9,
    quantum_vulnerable: bool = True,
    classically_broken: bool = False,
    urgency_ratio: float = 0.85,
    recommended: str = "ML-KEM-768",
    snippet: str | None = None,
    rationale: str = "RSA broken by Shor's algorithm",
) -> FindingVM:
    return FindingVM(
        id=id,
        risk_level=risk_level,
        algorithm=algorithm,
        family=family,
        file_path=file_path,
        line=line,
        language=language,
        confidence=confidence,
        quantum_vulnerable=quantum_vulnerable,
        classically_broken=classically_broken,
        urgency_ratio=urgency_ratio,
        mosca_x=3.0,
        mosca_y=5.0,
        mosca_z=10.0,
        mosca_violation=urgency_ratio >= 0.8,
        rationale=rationale,
        recommended=recommended,
        fips_reference="FIPS 203",
        snippet=snippet,
    )


def _make_vm(
    findings: list[FindingVM] | None = None,
    target: str = "/tmp/repo",
    files_scanned: int = 50,
    duration_s: float = 2.5,
) -> ScanVM:
    findings = findings or []
    counts: dict[str, int] = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "quantum-safe": 0,
    }
    for f in findings:
        counts[f.risk_level] = counts.get(f.risk_level, 0) + 1

    total = len(findings)
    safe_ratio = counts["quantum-safe"] / total if total > 0 else 0.0

    by_file: dict[str, list[FindingVM]] = {}
    for f in findings:
        by_file.setdefault(f.file_path, []).append(f)

    by_rec: dict[str, list[FindingVM]] = {}
    for f in findings:
        key = f.recommended or "(none)"
        by_rec.setdefault(key, []).append(f)

    # Build priority actions (non-quantum-safe groups).
    groups: dict[tuple[str, str], list[FindingVM]] = {}
    for f in findings:
        if f.risk_level == "quantum-safe":
            continue
        groups.setdefault((f.family, f.file_path), []).append(f)

    pa: list[PriorityAction] = []
    for (fam, fp), g in groups.items():
        worst = min(g, key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3, "quantum-safe": 4}.get(x.risk_level, 99))
        pa.append(
            PriorityAction(
                family=fam,
                file_path=fp,
                worst_risk=worst.risk_level,
                count=len(g),
                recommended=g[0].recommended,
            )
        )
    pa.sort(key=lambda x: (
        {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(x.worst_risk, 99),
        -x.count,
    ))

    return ScanVM(
        target=target,
        duration_s=duration_s,
        files_scanned=files_scanned,
        findings=findings,
        counts=counts,
        total=total,
        safe_ratio=safe_ratio,
        by_file=by_file,
        by_recommendation=by_rec,
        priority_actions=pa[:10],
    )


def _render_to_string(renderable) -> str:
    """Render a Rich renderable to a plain string (no color, no markup)."""
    buf = io.StringIO()
    c = make_console(no_color=True, width=100)
    # Override file to capture output.
    saved = c.file
    try:
        c.file = buf  # type: ignore[assignment]
        c.print(renderable)
    finally:
        c.file = saved
    return buf.getvalue()


# ---------------------------------------------------------------------------
# smooth_bar
# ---------------------------------------------------------------------------


class TestSmoothBar:
    def test_fraction_0(self) -> None:
        bar = smooth_bar(0.0, 10)
        assert len(bar.plain) == 10
        # All should be empty blocks or spaces.
        assert "\u2588" not in bar.plain  # no full block

    def test_fraction_1(self) -> None:
        bar = smooth_bar(1.0, 10)
        assert len(bar.plain) == 10
        assert "\u2588" in bar.plain  # has full blocks

    def test_fraction_05(self) -> None:
        bar = smooth_bar(0.5, 20)
        assert len(bar.plain) == 20
        # Half should be filled, half empty.
        full_count = bar.plain.count("\u2588")
        assert 8 <= full_count <= 10, f"Expected ~10 full blocks, got {full_count}"

    def test_clamp_to_1(self) -> None:
        bar = smooth_bar(5.0, 10)
        assert bar.plain.count("\u2588") == 10

    def test_clamp_to_0(self) -> None:
        bar = smooth_bar(-0.5, 10)
        assert "\u2588" not in bar.plain

    def test_ascii_mode(self) -> None:
        bar = smooth_bar(1.0, 5, unicode=False)
        assert bar.plain == "#####"

    def test_ascii_empty(self) -> None:
        bar = smooth_bar(0.0, 5, unicode=False)
        assert bar.plain == "-----"

    def test_width_1_unicode(self) -> None:
        bar = smooth_bar(0.6, 1, unicode=True)
        assert len(bar.plain) == 1


# ---------------------------------------------------------------------------
# risk_chip
# ---------------------------------------------------------------------------


class TestRiskChip:
    def test_critical(self) -> None:
        chip = risk_chip("critical")
        assert "CRITICAL" in chip.plain

    def test_unknown_level(self) -> None:
        chip = risk_chip("bogus")
        assert "BOGUS" in chip.plain or "bogus" in chip.plain


# ---------------------------------------------------------------------------
# summary_panel
# ---------------------------------------------------------------------------


class TestSummaryPanel:
    def test_with_findings(self) -> None:
        vm = _make_vm([
            _make_finding(risk_level="critical"),
            _make_finding(risk_level="high", id="det-2", family="ECC"),
        ])
        output = _render_to_string(summary_panel(vm))
        assert "CRITICAL" in output
        assert "HIGH" in output

    def test_safe_vm(self) -> None:
        vm = _make_vm([
            _make_finding(
                risk_level="quantum-safe",
                quantum_vulnerable=False,
                urgency_ratio=0.0,
            ),
        ])
        output = _render_to_string(summary_panel(vm))
        assert "good" in output.lower() or "100%" in output


# ---------------------------------------------------------------------------
# risk_bars
# ---------------------------------------------------------------------------


class TestRiskBars:
    def test_mixed(self) -> None:
        vm = _make_vm([
            _make_finding(risk_level="critical"),
            _make_finding(risk_level="low", id="det-2", family="AES"),
        ])
        output = _render_to_string(risk_bars(vm))
        assert "CRITICAL" in output
        assert "LOW" in output

    def test_empty(self) -> None:
        vm = _make_vm([])
        output = _render_to_string(risk_bars(vm))
        # Should not crash, should produce something.
        assert len(output) > 0


# ---------------------------------------------------------------------------
# findings_table
# ---------------------------------------------------------------------------


class TestFindingsTable:
    def test_rows(self) -> None:
        vm = _make_vm([
            _make_finding(),
            _make_finding(
                id="det-2", risk_level="high", algorithm="ECC-P256", family="ECC"
            ),
        ])
        output = _render_to_string(findings_table(vm))
        assert "RSA-2048" in output
        assert "ECC-P256" in output

    def test_truncation(self) -> None:
        """When findings exceed limit, '+N more' should appear."""
        findings = [_make_finding(id=f"det-{i}") for i in range(20)]
        vm = _make_vm(findings)
        output = _render_to_string(findings_table(vm, limit=5))
        assert "15 more" in output

    def test_flags(self) -> None:
        vm = _make_vm([
            _make_finding(quantum_vulnerable=True, classically_broken=True),
        ])
        output = _render_to_string(findings_table(vm))
        assert "Q" in output
        assert "!" in output

    def test_no_flags(self) -> None:
        vm = _make_vm([
            _make_finding(
                risk_level="quantum-safe",
                quantum_vulnerable=False,
                classically_broken=False,
                urgency_ratio=0.0,
            ),
        ])
        output = _render_to_string(findings_table(vm))
        assert "\u2014" in output  # em dash for no flags


# ---------------------------------------------------------------------------
# priority_actions_panel
# ---------------------------------------------------------------------------


class TestPriorityActionsPanel:
    def test_with_actions(self) -> None:
        vm = _make_vm([
            _make_finding(),
            _make_finding(id="det-2", risk_level="medium", family="ECC"),
        ])
        output = _render_to_string(priority_actions_panel(vm))
        assert "RSA" in output

    def test_empty(self) -> None:
        vm = _make_vm([])
        output = _render_to_string(priority_actions_panel(vm))
        assert "priority" in output.lower()


# ---------------------------------------------------------------------------
# recommendations_table
# ---------------------------------------------------------------------------


class TestRecommendationsTable:
    def test_with_recommendations(self) -> None:
        vm = _make_vm([_make_finding(recommended="ML-KEM-768")])
        output = _render_to_string(recommendations_table(vm))
        assert "ML-KEM-768" in output

    def test_no_recommendations(self) -> None:
        vm = _make_vm([])
        output = _render_to_string(recommendations_table(vm))
        assert "quantum-safe" in output.lower() or "ML-" in output or "safe" in output.lower()


# ---------------------------------------------------------------------------
# legend
# ---------------------------------------------------------------------------


class TestLegend:
    def test_legend_content(self) -> None:
        output = _render_to_string(legend())
        assert "Q" in output
        assert "classically" in output.lower() or "broken" in output.lower()
        assert "CRITICAL" in output


# ---------------------------------------------------------------------------
# _ellipsis_path
# ---------------------------------------------------------------------------


class TestEllipsisPath:
    def test_short_path(self) -> None:
        result = _ellipsis_path("src/main.py", 42, width=100)
        assert result == "src/main.py:42"

    def test_long_path_ellipsised(self) -> None:
        long_path = "very/deeply/nested/project/module/submodule/file.py"
        result = _ellipsis_path(long_path, 123, width=30)
        assert "\u2026" in result
        assert "file.py:123" in result

    def test_no_line(self) -> None:
        result = _ellipsis_path("a/b/c.py", None, width=100)
        assert result == "a/b/c.py"


# ---------------------------------------------------------------------------
# scan_report — empty scan
# ---------------------------------------------------------------------------


class TestScanReportEmpty:
    def test_empty_scan(self) -> None:
        vm = _make_vm([], files_scanned=42)
        output = _render_to_string(scan_report(vm))
        assert "42" in output
        assert "cryptographic" in output.lower()

    def test_empty_scan_is_friendly(self) -> None:
        """Empty scan should be a simple friendly panel, not the full layout."""
        vm = _make_vm([], files_scanned=10)
        output = _render_to_string(scan_report(vm))
        # Should NOT have priority actions, findings table, etc.
        assert "Priority Actions" not in output
        assert "Findings" not in output


# ---------------------------------------------------------------------------
# scan_report — full scan
# ---------------------------------------------------------------------------


class TestScanReportFull:
    def test_full_scan(self) -> None:
        vm = _make_vm([
            _make_finding(),
            _make_finding(id="det-2", risk_level="high", family="ECC"),
            _make_finding(
                id="det-3",
                risk_level="quantum-safe",
                quantum_vulnerable=False,
                urgency_ratio=0.0,
                family="ML-KEM",
                algorithm="ML-KEM-768",
                recommended="ML-KEM-768",
            ),
        ])
        output = _render_to_string(scan_report(vm))
        assert "Summary" in output or "Scan" in output
        assert "Findings" in output
        assert "RSA" in output
        assert "ML-KEM" in output


# ---------------------------------------------------------------------------
# HOSTILE CONTENT — escape safety (CRITICAL)
# ---------------------------------------------------------------------------


class TestHostileContent:
    """File paths, snippets, and algorithm names from scanned repos are
    attacker-controlled.  Renderers must NEVER interpolate them into Rich
    markup strings — they go through ``rich.text.Text`` which treats content
    as plain text, not markup."""

    HOSTILE_PATH = "[bold red]pwn[/].py"
    HOSTILE_ALGORITHM = "[link=https://evil.example]RSA[/link]"
    HOSTILE_RATIONALE = "\x1b[31mred\x1b[0m rationale"
    HOSTILE_SNIPPET = "import [bold red]malware[/bold red]"

    def _hostile_vm(self) -> ScanVM:
        return _make_vm([
            _make_finding(
                file_path=self.HOSTILE_PATH,
                algorithm=self.HOSTILE_ALGORITHM,
                rationale=self.HOSTILE_RATIONALE,
                snippet=self.HOSTILE_SNIPPET,
            ),
        ])

    def test_literal_bracket_text_present(self) -> None:
        """The literal '[bold red]' text must appear in output — NOT be parsed."""
        vm = self._hostile_vm()
        output = _render_to_string(scan_report(vm))
        assert "[bold red]pwn[/].py" in output

    def test_no_escape_sequences(self) -> None:
        """No raw ANSI escape sequences in output."""
        vm = self._hostile_vm()
        output = _render_to_string(scan_report(vm))
        assert "\x1b[" not in output, "Raw ANSI escape found in output"

    def test_no_encoded_escape(self) -> None:
        """No \\x1b literal in output."""
        vm = self._hostile_vm()
        output = _render_to_string(scan_report(vm))
        assert r"\x1b" not in output

    def test_algorithm_text_present(self) -> None:
        """Algorithm name with link markup appears as literal text."""
        vm = self._hostile_vm()
        output = _render_to_string(scan_report(vm))
        assert "RSA" in output


class TestSafeHelper:
    def test_safe_wraps_as_plain_text(self) -> None:
        t = _safe("[bold red]test[/bold red]")
        assert t.plain == "[bold red]test[/bold red]"
        # No spans should be created from markup parsing.
        assert t.style is not None  # has a Style object, even if empty

    def test_safe_strips_escape_bytes(self) -> None:
        """``_safe`` neutralises raw ESC / BEL before Text() is built."""
        t = _safe("\x1b[31mred\x1b[0m")
        assert "\x1b" not in t.plain
        assert t.plain == "[31mred[0m"

    def test_safe_preserves_printable_unicode(self) -> None:
        value = "caf\u00e9 \U0001f600 \u2502 \u2588"
        assert _safe(value).plain == value


class TestStripControlChars:
    """Unit tests for the untrusted-content boundary sanitizer."""

    def test_removes_esc_and_bell(self) -> None:
        assert strip_control_chars("a\x1b[31mb\x07c") == "a[31mbc"

    def test_removes_c1_controls(self) -> None:
        assert strip_control_chars("a\x9b31m\x85b") == "a31mb"

    def test_drops_carriage_return(self) -> None:
        assert strip_control_chars("a\rb") == "ab"

    def test_keeps_tab_and_newline(self) -> None:
        assert strip_control_chars("a\tb\nc") == "a\tb\nc"

    def test_keeps_printable_unicode(self) -> None:
        value = "caf\u00e9 \U0001f600 \u2502 \u2588 \u2714"
        assert strip_control_chars(value) == value

    def test_empty_string(self) -> None:
        assert strip_control_chars("") == ""

    def test_removes_every_c0_except_tab_newline(self) -> None:
        raw = "".join(chr(c) for c in range(0x20))
        assert strip_control_chars(raw) == "\t\n"

    def test_removes_every_c1(self) -> None:
        raw = "".join(chr(c) for c in range(0x80, 0xA0))
        assert strip_control_chars(raw) == ""


class TestReportControlByteSafety:
    """The full pretty report must carry zero raw control bytes."""

    HOSTILE_OSC8 = "\x1b]8;;https://evil.example\x07click\x1b]8;;\x07"
    HOSTILE_OSC2 = "\x1b]2;owned title\x07"
    HOSTILE_BELL = "ding\x07dong"
    HOSTILE_C1 = "c1:\x9b31m\x85x"

    def _vm_with(self, value: str) -> ScanVM:
        return _make_vm([
            _make_finding(
                file_path=f"src/{value}.py",
                algorithm=value,
                family=value,
                rationale=value,
                recommended=value,
                snippet=value,
            ),
        ], target=value)

    def _render(self, vm: ScanVM) -> str:
        return _render_to_string(scan_report(vm, limit=50))

    @pytest.mark.parametrize(
        "payload",
        [HOSTILE_OSC8, HOSTILE_OSC2, HOSTILE_BELL, HOSTILE_C1],
        ids=["osc8", "osc2", "bell", "c1"],
    )
    def test_no_raw_control_bytes(self, payload: str) -> None:
        output = self._render(self._vm_with(payload))
        assert "\x1b" not in output
        assert "\x07" not in output
        bad = [c for c in output if ord(c) < 0x20 and c not in "\t\n"]
        assert not bad, f"control bytes {[hex(ord(c)) for c in bad]} leaked"
        c1 = [c for c in output if 0x80 <= ord(c) <= 0x9F]
        assert not c1

    def test_unicode_survives_report(self) -> None:
        value = "caf\u00e9 \U0001f600 \u2502 \u2588"
        output = self._render(self._vm_with(value))
        assert value in output


class TestExportControlByteSafety:
    """Markdown and HTML exports must carry zero raw control bytes."""

    HOSTILE = "\x1b]8;;https://evil.example\x07click\x1b]8;;\x07\x1b[31m\x9b"

    def _result(self) -> "ScanResult":
        from ecdat_core.models import Detection, Recommendation, RiskAssessment, ScanResult

        detection = Detection(
            id="d1",
            file_path=f"src/{self.HOSTILE}.py",
            line_number=5,
            matched_text=self.HOSTILE,
            asset_type="algorithm",
            algorithm_family=self.HOSTILE,
            key_size_bits=2048,
            quantum_vulnerable=True,
            classically_broken=False,
            confidence=0.9,
            language="python",
            detection_method="regex",
        )
        return ScanResult(
            scan_id=self.HOSTILE,
            target=self.HOSTILE,
            detections=[detection],
            risk_assessments=[
                RiskAssessment(
                    detection_id="d1",
                    migration_time_years=3.0,
                    shelf_life_years=5.0,
                    threat_horizon_years=5.0,
                    urgency_ratio=1.5,
                    risk_level="critical",
                    mosca_violation=True,
                )
            ],
            recommendations=[
                Recommendation(
                    detection_id="d1",
                    recommended_algorithm=self.HOSTILE,
                    fips_reference=self.HOSTILE,
                    rationale=self.HOSTILE,
                    latency_note="",
                    migration_note="",
                )
            ],
            scanned_at="2026-09-22T12:00:00+00:00",
            files_scanned=1,
        )

    @pytest.mark.parametrize("fmt", ["markdown", "html"])
    def test_no_raw_control_bytes(self, fmt: str) -> None:
        from ecdat.services.exporters import export_html, export_markdown

        doc = export_markdown(self._result()) if fmt == "markdown" else export_html(self._result())
        assert "\x1b" not in doc
        assert "\x07" not in doc
        c1 = [c for c in doc if 0x80 <= ord(c) <= 0x9F]
        assert not c1

    @pytest.mark.parametrize("fmt", ["markdown", "html"])
    def test_unicode_survives_export(self, fmt: str) -> None:
        from ecdat.services.exporters import export_html, export_markdown

        value = "caf\u00e9 \U0001f600 \u2502 \u2588"
        result = self._result()
        result.target = value
        result.detections[0].file_path = f"{value}.py"
        result.detections[0].algorithm_family = value
        doc = export_markdown(result) if fmt == "markdown" else export_html(result)
        assert value in doc