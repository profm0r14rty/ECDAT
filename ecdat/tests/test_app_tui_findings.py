"""Pilot tests for the Findings tab (Phase 85).

Animations are disabled by the repo's autouse fixture, so every render happens
at its final value immediately.  The showcase fixture is the reference scan:
70 findings, 16 critical, 8 medium, 8 low, 38 quantum-safe.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from rich.text import Text
from textual.widgets import DataTable, Input, Static, TabbedContent

from ecdat.services.scanner import ScanOutcome, classify_target, perform_scan
from ecdat.services.viewmodel import build_scan_vm
from ecdat.tui.app import EcdatApp
from ecdat.tui.screens.results import ResultsScreen
from ecdat.tui.widgets.finding_detail import FindingDetail
from ecdat.tui.widgets.findings_table import FindingsPane
from ecdat.tui.widgets.mosca_timeline import MoscaTimeline
from ecdat_core.models import Detection, Recommendation, RiskAssessment, ScanResult

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tui_helpers import wait_until  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SHOWCASE_REPO = REPO_ROOT / "ecdat_core" / "tests" / "fixtures" / "showcase_repo"

HOSTILE = "[bold red]evil\x1b[31m[/]"


def _outcome() -> ScanOutcome:
    return perform_scan(classify_target(str(SHOWCASE_REPO)), label="showcase")


def _plain(widget) -> str:
    rendered = widget.render()
    return getattr(rendered, "plain", str(rendered))


def _hostile_outcome() -> ScanOutcome:
    """A one-finding scan whose algorithm/file carry rich-markup-shaped text."""
    detection = Detection(
        id="hostile-1",
        file_path=f"{HOSTILE}/weird.py",
        line_number=7,
        matched_text="crypto",
        asset_type="algorithm",
        algorithm_family=HOSTILE,
        key_size_bits=None,
        quantum_vulnerable=True,
        classically_broken=False,
        confidence=0.5,
        language="python",
        detection_method="regex",
    )
    result = ScanResult(
        scan_id="hostile",
        target="hostile",
        detections=[detection],
        risk_assessments=[
            RiskAssessment(
                detection_id="hostile-1",
                migration_time_years=1.0,
                shelf_life_years=2.0,
                threat_horizon_years=5.0,
                urgency_ratio=0.6,
                risk_level="medium",
                mosca_violation=False,
            )
        ],
        recommendations=[
            Recommendation(
                detection_id="hostile-1",
                recommended_algorithm=HOSTILE,
                fips_reference=HOSTILE,
                rationale=HOSTILE,
                latency_note="",
                migration_note="",
            )
        ],
        scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        files_scanned=1,
    )
    return ScanOutcome(
        result=result, vm=build_scan_vm(result, target="hostile"), duration_s=0.1
    )


async def _open_findings(pilot, app) -> FindingsPane:
    """Focus the Findings tab and return its pane."""
    tabs = app.screen.query_one("#results-tabs", TabbedContent)
    await pilot.press("2")
    await wait_until(pilot, lambda: tabs.active == "tab-findings", timeout=10.0)
    await pilot.pause()
    return app.screen.query_one("#findings-pane", FindingsPane)


# ---------------------------------------------------------------------------
# Structure and initial population
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_findings_tab_exists_with_table_and_detail() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        pane = await _open_findings(pilot, app)
        assert pane.query_one("#findings", DataTable) is not None
        assert pane.query_one("#finding-detail", FindingDetail) is not None
        assert pane.query_one("#detail-mosca", MoscaTimeline) is not None


@pytest.mark.asyncio
async def test_initial_rows_equal_total() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        pane = await _open_findings(pilot, app)
        table = pane.query_one("#findings", DataTable)
        assert table.row_count == outcome.vm.total
        assert pane.visible_findings() == outcome.vm.findings


@pytest.mark.asyncio
async def test_showing_label_counts() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        pane = await _open_findings(pilot, app)
        label = _plain(pane.query_one("#findings-showing", Static))
        assert f"Showing {outcome.vm.total} of {outcome.vm.total}" in label


# ---------------------------------------------------------------------------
# Severity keys
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_c_filters_to_critical_only() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        pane = await _open_findings(pilot, app)
        table = pane.query_one("#findings", DataTable)

        await pilot.press("c")
        await pilot.pause()
        assert table.row_count == outcome.vm.counts["critical"]
        assert {f.risk_level for f in pane.visible_findings()} == {"critical"}
        assert pane.active_levels() == ["critical"]

        await pilot.press("c")
        await pilot.pause()
        assert table.row_count == outcome.vm.total


@pytest.mark.asyncio
async def test_each_severity_key_solos_its_level() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        pane = await _open_findings(pilot, app)

        for key, level in (("h", "high"), ("m", "medium"), ("l", "low"), ("s", "quantum-safe")):
            await pilot.press(key)
            await pilot.pause()
            assert pane.active_levels() == [level]
            assert {f.risk_level for f in pane.visible_findings()} <= {level}
            await pilot.press(key)  # restore all
            await pilot.pause()
            assert len(pane.active_levels()) == 5


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slash_focuses_search_and_typing_narrows() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        pane = await _open_findings(pilot, app)
        table = pane.query_one("#findings", DataTable)

        await pilot.press("slash")
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "findings-search"

        search = pane.query_one("#findings-search", Input)
        search.value = "md5"
        await pilot.pause()

        expected = sum(1 for f in outcome.vm.findings if "md5" in f.algorithm.lower())
        assert table.row_count == expected
        assert all("md5" in f.algorithm.lower() for f in pane.visible_findings())
        label = _plain(pane.query_one("#findings-showing", Static))
        assert f"of {outcome.vm.total}" in label
        assert f"Showing {expected}" in label


@pytest.mark.asyncio
async def test_escape_clears_search_and_refocuses_table() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        pane = await _open_findings(pilot, app)
        table = pane.query_one("#findings", DataTable)

        await pilot.press("slash")
        await pilot.pause()
        await pilot.press("m", "d", "5")
        await pilot.pause()
        assert pane.query_one("#findings-search", Input).value == "md5"

        await pilot.press("escape")
        await pilot.pause()
        assert pane.query_one("#findings-search", Input).value == ""
        assert table.row_count == outcome.vm.total
        assert app.focused is not None and app.focused.id == "findings"


# ---------------------------------------------------------------------------
# Detail pane
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_highlighting_a_row_updates_the_detail() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        pane = await _open_findings(pilot, app)
        table = pane.query_one("#findings", DataTable)
        detail = pane.query_one("#finding-detail", FindingDetail)

        target = next(f for f in pane.visible_findings() if f.family == "RSA")
        index = pane.visible_findings().index(target)
        table.move_cursor(row=index)
        await pilot.pause()

        assert target.algorithm in detail.plain_text()
        assert detail.location_text() == f"{target.file_path}:{target.line}"


@pytest.mark.asyncio
async def test_rsa_finding_shows_exposed_mosca_window() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        pane = await _open_findings(pilot, app)
        table = pane.query_one("#findings", DataTable)
        mosca = pane.query_one("#detail-mosca", MoscaTimeline)

        rsa = next(f for f in pane.visible_findings() if f.family == "RSA")
        assert rsa.mosca_violation is True
        table.move_cursor(row=pane.visible_findings().index(rsa))
        await pilot.pause()

        assert mosca.has_values()
        assert mosca.has_exposed_window()
        tokens = {token for row in mosca.segment_rows() for _text, token in row}
        assert "gap" in tokens


@pytest.mark.asyncio
async def test_classically_broken_md5_shows_gap_too() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        pane = await _open_findings(pilot, app)
        table = pane.query_one("#findings", DataTable)
        mosca = pane.query_one("#detail-mosca", MoscaTimeline)

        md5 = next(f for f in pane.visible_findings() if f.family == "MD5")
        table.move_cursor(row=pane.visible_findings().index(md5))
        await pilot.pause()
        assert mosca.has_exposed_window()


@pytest.mark.asyncio
async def test_quantum_safe_finding_has_no_gap() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        pane = await _open_findings(pilot, app)
        table = pane.query_one("#findings", DataTable)
        mosca = pane.query_one("#detail-mosca", MoscaTimeline)

        safe = next(f for f in pane.visible_findings() if f.risk_level == "quantum-safe")
        table.move_cursor(row=pane.visible_findings().index(safe))
        await pilot.pause()
        assert not mosca.has_exposed_window()


# ---------------------------------------------------------------------------
# Sort
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_o_cycles_sort_modes() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        pane = await _open_findings(pilot, app)

        assert pane.sort_mode == "urgency"
        seen = [pane.sort_mode]
        for _ in range(4):
            await pilot.press("o")
            await pilot.pause()
            seen.append(pane.sort_mode)
        assert seen == ["urgency", "file", "algorithm", "risk", "urgency"]


@pytest.mark.asyncio
async def test_file_sort_orders_rows() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        pane = await _open_findings(pilot, app)

        await pilot.press("o")  # urgency -> file
        await pilot.pause()
        assert pane.sort_mode == "file"
        keys = [(f.file_path, f.line) for f in pane.visible_findings()]
        assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# Filter survival and jump-to-findings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filter_change_keeps_cursor_when_row_survives() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        pane = await _open_findings(pilot, app)
        table = pane.query_one("#findings", DataTable)

        # Focus a critical row, then keep critical active — it must survive.
        first = pane.visible_findings()[0]
        assert first.risk_level == "critical"
        table.move_cursor(row=0)
        await pilot.pause()
        await pilot.press("c")  # solo to critical; row 0 is still there
        await pilot.pause()
        assert pane.selected_finding() is not None
        assert pane.selected_finding().risk_level == "critical"


@pytest.mark.asyncio
async def test_jump_to_findings_from_priority_list_filters_by_file() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        screen = ResultsScreen(outcome)
        app.push_screen(screen)
        await pilot.pause()

        action = outcome.vm.priority_actions[0]
        screen.jump_to_findings(action.family, action.file_path)
        await pilot.pause()

        tabs = screen.query_one("#results-tabs", TabbedContent)
        assert tabs.active == "tab-findings"
        pane = screen.query_one("#findings-pane", FindingsPane)
        visible = pane.visible_findings()
        assert visible
        assert all(f.file_path == action.file_path for f in visible)
        assert all(f.family == action.family for f in visible)


@pytest.mark.asyncio
async def test_apply_filter_clear_restores_everything() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        pane = await _open_findings(pilot, app)

        pane.apply_filter(file=outcome.vm.priority_actions[0].file_path)
        await pilot.pause()
        assert len(pane.visible_findings()) < outcome.vm.total

        pane.apply_filter()
        await pilot.pause()
        assert len(pane.visible_findings()) == outcome.vm.total


# ---------------------------------------------------------------------------
# Responsive layout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_narrow_terminal_applies_narrow_class() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        pane = await _open_findings(pilot, app)
        split = pane.query_one("#findings-split")
        assert not split.has_class("-narrow")

        await pilot.resize_terminal(90, 40)
        await pilot.pause()
        assert split.has_class("-narrow")

        await pilot.resize_terminal(140, 44)
        await pilot.pause()
        assert not split.has_class("-narrow")


# ---------------------------------------------------------------------------
# Hostile content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hostile_finding_renders_literally() -> None:
    outcome = _hostile_outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        pane = await _open_findings(pilot, app)

        table = pane.query_one("#findings", DataTable)
        assert table.row_count == 1
        # The raw markup text reaches the cells unparsed.
        cells = table.get_row_at(0)
        joined = "".join(getattr(c, "plain", str(c)) for c in cells)
        assert HOSTILE in joined

        detail = pane.query_one("#finding-detail", FindingDetail)
        detail.show_finding(pane.visible_findings()[0])
        await pilot.pause()
        assert HOSTILE in detail.plain_text()


@pytest.mark.asyncio
async def test_hostile_finding_does_not_crash_render() -> None:
    outcome = _hostile_outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        pane = await _open_findings(pilot, app)
        # Force a full re-render of both halves.
        await pilot.press("o")
        await pilot.pause()
        await pilot.resize_terminal(95, 38)
        await pilot.pause()
        assert app.is_running is True


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_y_copies_location(monkeypatch) -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    copied: list[str] = []
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        pane = await _open_findings(pilot, app)
        monkeypatch.setattr(app, "copy_to_clipboard", lambda text: copied.append(text))

        finding = pane.selected_finding()
        assert finding is not None
        await pilot.press("y")
        await pilot.pause()
        assert copied == [f"{finding.file_path}:{finding.line}"]
