"""Tests for the Results screen and its widgets (Phase 84).

Animations are disabled by the repo's autouse fixture, so every count-up and bar
renders at its final value immediately and the assertions are deterministic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from textual.widgets import Digits, Static, TabbedContent

from ecdat.services.scanner import ScanOutcome, classify_target, perform_scan
from ecdat.tui.app import EcdatApp
from ecdat.tui.screens.home import HomeScreen
from ecdat.tui.screens.results import JumpToFindings, ResultsScreen
from ecdat.tui.widgets.priority_list import PriorityList
from ecdat.tui.widgets.risk_chart import RiskChart
from ecdat.tui.widgets.stat_card import StatCard
from ecdat.ui.art_static import CRIT_LOCK, SAFE_LOCK, WARN_LOCK, emblem_for, headline_for, verdict
from ecdat.ui.theme import RISK_ORDER, strip_control_chars

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tui_helpers import wait_until  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SHOWCASE_REPO = REPO_ROOT / "ecdat_core" / "tests" / "fixtures" / "showcase_repo"
DEMO_REPO = REPO_ROOT / "ecdat_core" / "tests" / "fixtures" / "demo_repo"


def _outcome(path: Path) -> ScanOutcome:
    return perform_scan(classify_target(str(path)), label=str(path))


def _empty_outcome() -> ScanOutcome:
    from datetime import datetime, timezone

    from ecdat_core.models import ScanResult
    from ecdat.services.viewmodel import build_scan_vm

    result = ScanResult(
        scan_id="empty-1",
        target="/tmp/empty",
        detections=[],
        risk_assessments=[],
        recommendations=[],
        scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        files_scanned=7,
    )
    return ScanOutcome(result=result, vm=build_scan_vm(result, target="/tmp/empty"), duration_s=0.1)


def _plain(widget) -> str:
    rendered = widget.render()
    return getattr(rendered, "plain", str(rendered))


# ---------------------------------------------------------------------------
# art_static contract (reused by the screen)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("emblem", [SAFE_LOCK, WARN_LOCK, CRIT_LOCK])
def test_every_emblem_is_9x19(emblem) -> None:
    assert len(emblem) == 9
    assert all(len(row) == 19 for row in emblem)


def test_verdict_and_emblem_mapping() -> None:
    assert verdict({"critical": 1}) == "crit"
    assert emblem_for("crit") == CRIT_LOCK
    assert verdict({"high": 1}) == "warn"
    assert emblem_for("warn") == WARN_LOCK
    assert verdict({"quantum-safe": 3}) == "safe"
    assert emblem_for("safe") == SAFE_LOCK
    assert verdict({}) == "empty"
    assert emblem_for("empty") == SAFE_LOCK


def test_headline_mentions_critical() -> None:
    text = headline_for({"critical": 2, "high": 1}, files=4)
    assert "CRITICAL" in text and "HIGH" in text


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_showcase_overview_shows_exact_counts() -> None:
    outcome = _outcome(SHOWCASE_REPO)
    vm = outcome.vm
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        screen = ResultsScreen(outcome)
        app.push_screen(screen)
        await pilot.pause()

        assert screen.query_one("#result-emblem", Static) is not None
        assert screen.query_one("#stats-grid") is not None
        assert screen.query_one("#risk-chart", RiskChart) is not None
        assert screen.query_one("#priority-list", PriorityList) is not None
        assert screen.query_one("#results-tabs", TabbedContent).active == "tab-overview"

        expected = {
            "stat-files": vm.files_scanned,
            "stat-artefacts": vm.total,
            "stat-critical": vm.counts["critical"],
            "stat-high": vm.counts["high"],
            "stat-medium": vm.counts["medium"],
            "stat-low": vm.counts["low"],
            "stat-safe": vm.counts["quantum-safe"],
        }
        for stat_id, value in expected.items():
            card = screen.query_one(f"#{stat_id}", StatCard)
            assert card.display_value == value
            assert card.query_one(Digits).value == str(value)

        headline = _plain(screen.query_one("#result-headline", Static))
        assert "CRITICAL" in headline


@pytest.mark.asyncio
async def test_risk_chart_rows_match_risk_order() -> None:
    outcome = _outcome(SHOWCASE_REPO)
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        chart = RiskChart(outcome.vm.counts, outcome.vm.total, readiness=outcome.vm.safe_ratio)
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        assert chart.row_levels() == list(RISK_ORDER)

        fractions = chart.final_fractions()
        assert len(fractions) == 5
        assert fractions[0] == pytest.approx(
            outcome.vm.counts["critical"] / outcome.vm.total
        )
        assert "%" in chart.gauge_label()


@pytest.mark.asyncio
async def test_empty_scan_shows_friendly_state() -> None:
    outcome = _empty_outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = ResultsScreen(outcome)
        app.push_screen(screen)
        await pilot.pause()
        empty = screen.query_one("#results-empty", Static)
        assert empty.display is True
        assert "7" in _plain(empty)


# ---------------------------------------------------------------------------
# Priority list -> JumpToFindings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_priority_list_enter_posts_jump_message() -> None:
    outcome = _outcome(SHOWCASE_REPO)
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        screen = ResultsScreen(outcome)
        app.push_screen(screen)
        await pilot.pause()

        plist = screen.query_one("#priority-list", PriorityList)
        assert plist.action_rows()
        assert plist.option_count == len(plist.action_rows())

        seen: list[tuple[str, str]] = []
        screen.jump_to_findings = lambda family, path: seen.append((family, path))  # type: ignore[assignment]
        plist.highlighted = 0
        plist.focus()
        await pilot.press("enter")
        await pilot.pause()
        assert seen
        assert seen[0] == (plist.action_rows()[0][0], plist.action_rows()[0][1])


def test_jump_to_findings_message_carries_payload() -> None:
    message = JumpToFindings("RSA", "auth/login.py")
    assert message.family == "RSA"
    assert message.file_path == "auth/login.py"


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_n_returns_home() -> None:
    outcome = _outcome(DEMO_REPO)
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        assert isinstance(app.screen, ResultsScreen)
        await pilot.press("n")
        await wait_until(pilot, lambda: isinstance(app.screen, HomeScreen), timeout=10.0)


@pytest.mark.asyncio
async def test_digit_key_switches_to_existing_tab_only() -> None:
    outcome = _outcome(DEMO_REPO)
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        tabs = app.screen.query_one("#results-tabs", TabbedContent)
        await pilot.press("1")
        await pilot.pause()
        assert tabs.active == "tab-overview"
        # Phase 85 added the Findings tab — pressing 2 now switches to it.
        await pilot.press("2")
        await pilot.pause()
        assert tabs.active == "tab-findings"
        # An out-of-range key is silently ignored, leaving the active tab alone.
        await pilot.press("9")
        await pilot.pause()
        assert tabs.active == "tab-findings"


# ---------------------------------------------------------------------------
# Hostile content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hostile_target_is_not_markup() -> None:
    from datetime import datetime, timezone

    from ecdat_core.models import ScanResult
    from ecdat.services.viewmodel import build_scan_vm

    hostile = "[bold red]evil\x1b[31m"
    result = ScanResult(
        scan_id="hostile-1",
        target=hostile,
        detections=[],
        risk_assessments=[],
        recommendations=[],
        scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        files_scanned=1,
    )
    outcome = ScanOutcome(
        result=result, vm=build_scan_vm(result, target=hostile), duration_s=0.1
    )

    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        meta = _plain(app.screen.query_one("#result-meta", Static))
        # The markup-shaped text appears literally; the raw ESC byte is stripped
        # at the untrusted-content boundary so no ANSI escape can reach the TUI.
        assert strip_control_chars(hostile) in meta
        assert "\x1b" not in meta
