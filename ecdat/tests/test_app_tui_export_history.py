"""Pilot tests for the export modal and the history screen (Task B7 / Phase 87).

Animations are off via the repo's autouse fixture, so every assertion is
deterministic.  All history reads/writes land in the ``ECDAT_HOME`` tmp
directory created by ``ecdat/tests/conftest.py``.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from textual.widgets import DataTable, SelectionList, Static

from ecdat.services.scanner import ScanOutcome, classify_target, perform_scan
from ecdat.services.viewmodel import build_scan_vm
from ecdat.tui.app import EcdatApp
from ecdat.tui.screens.export import ExportScreen, default_export_dir
from ecdat.tui.screens.history import HistoryScreen, _ConfirmDeleteScreen
from ecdat.tui.screens.results import ResultsScreen
from ecdat_core.models import ScanResult

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tui_helpers import wait_until  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_REPO = REPO_ROOT / "ecdat_core" / "tests" / "fixtures" / "demo_repo"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _outcome(path: Path = DEMO_REPO) -> ScanOutcome:
    """Scan *path* and return its outcome (never saves history)."""
    return perform_scan(classify_target(str(path)), label=str(path), save_history=False)


def _empty_outcome() -> ScanOutcome:
    result = ScanResult(
        scan_id="empty-1",
        target="/tmp/empty",
        detections=[],
        risk_assessments=[],
        recommendations=[],
        scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        files_scanned=0,
    )
    return ScanOutcome(
        result=result, vm=build_scan_vm(result, target="/tmp/empty"), duration_s=0.0
    )


def _seed_history(count: int = 1) -> list[ScanResult]:
    """Persist *count* demo scans to history and return the saved records."""
    from ecdat.services.history import list_scans

    for _ in range(count):
        perform_scan(classify_target(str(DEMO_REPO)), label="demo")  # saves history
    return list_scans()


# ---------------------------------------------------------------------------
# default_export_dir
# ---------------------------------------------------------------------------


def test_default_dir_uses_record_id(tmp_path: Path) -> None:
    outcome = _outcome()
    outcome = ScanOutcome(
        result=outcome.result,
        vm=outcome.vm,
        duration_s=outcome.duration_s,
        record_id="abc123",
    )
    assert default_export_dir(outcome, tmp_path) == tmp_path / "ecdat-report-abc123"


def test_default_dir_falls_back_to_timestamp(tmp_path: Path) -> None:
    outcome = _outcome()
    name = default_export_dir(outcome, tmp_path).name
    assert name.startswith("ecdat-report-")
    assert len(name) > len("ecdat-report-")


# ---------------------------------------------------------------------------
# ExportScreen
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_writes_all_four_files_and_dismisses(tmp_path: Path) -> None:
    outcome = _outcome()
    out_dir = tmp_path / "bundle"
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        results: list = []
        app.push_screen(ExportScreen(outcome, base_dir=tmp_path), results.append)
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, ExportScreen)
        # All four built-in formats are preselected.
        assert set(screen.selected_formats()) == {
            "cbom",
            "summary",
            "markdown",
            "html",
        }

        screen.query_one("#export-dir").value = str(out_dir)
        await pilot.click("#export-go")

        await wait_until(
            pilot,
            lambda: bool(results),
            timeout=20.0,
        )

        assert len(results[0]) == 4
        names = sorted(p.name for p in out_dir.glob("*"))
        assert names == ["cbom.json", "report.html", "report.md", "summary.json"]
        # Payload formats are real, parseable documents.
        assert json.loads((out_dir / "cbom.json").read_text(encoding="utf-8"))[
            "bomFormat"
        ] == "CycloneDX"
        assert "ECDAT Scan Report" in (out_dir / "report.md").read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in (out_dir / "report.html").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_export_creates_missing_output_dir(tmp_path: Path) -> None:
    outcome = _outcome()
    out_dir = tmp_path / "deep" / "nested" / "bundle"
    assert not out_dir.exists()

    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(ExportScreen(outcome, base_dir=tmp_path))
        await pilot.pause()
        app.screen.query_one("#export-dir").value = str(out_dir)
        await pilot.click("#export-go")
        await wait_until(pilot, lambda: (out_dir / "cbom.json").exists(), timeout=20.0)
    assert (out_dir / "report.md").is_file()


@pytest.mark.asyncio
async def test_export_unwritable_folder_shows_error_without_crash(
    tmp_path: Path,
) -> None:
    """A path whose parent is a *file* can never be created as a directory."""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    bad_dir = blocker / "sub"

    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        results: list = []
        app.push_screen(ExportScreen(outcome, base_dir=tmp_path), results.append)
        await pilot.pause()
        screen = app.screen
        screen.query_one("#export-dir").value = str(bad_dir)
        await pilot.click("#export-go")

        error = await wait_until(
            pilot,
            lambda: screen.query_one("#export-error", Static).display
            and "Export failed" in _plain(screen.query_one("#export-error", Static)),
            timeout=20.0,
        )
        assert error
        # The dialog stays open and the app is still alive.
        assert isinstance(app.screen, ExportScreen)
        assert app.is_running
        assert results == []


@pytest.mark.asyncio
async def test_export_cancel_dismisses_with_none(tmp_path: Path) -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        results: list = []
        app.push_screen(ExportScreen(outcome, base_dir=tmp_path), results.append)
        await pilot.pause()
        await pilot.click("#export-cancel")
        await pilot.pause()
        assert results == [None]


@pytest.mark.asyncio
async def test_export_no_formats_selected_shows_error(tmp_path: Path) -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(ExportScreen(outcome, base_dir=tmp_path))
        await pilot.pause()
        screen = app.screen
        screen.query_one(f"#export-formats", SelectionList).deselect_all()
        await pilot.click("#export-go")
        await pilot.pause()
        assert screen.query_one("#export-error", Static).display is True
        assert isinstance(app.screen, ExportScreen)


@pytest.mark.asyncio
async def test_e_on_results_opens_export_and_toasts(tmp_path: Path) -> None:
    outcome = _outcome()
    out_dir = tmp_path / "from-e"
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        app.set_focus(None)
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, ExportScreen)

        app.screen.query_one("#export-dir").value = str(out_dir)
        await pilot.click("#export-go")
        await wait_until(
            pilot,
            lambda: isinstance(app.screen, ResultsScreen)
            and (out_dir / "cbom.json").exists(),
            timeout=20.0,
        )


def _plain(widget) -> str:
    rendered = widget.render()
    return getattr(rendered, "plain", str(rendered))


# ---------------------------------------------------------------------------
# HistoryScreen
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_lists_saved_scans_newest_first() -> None:
    records = _seed_history(2)
    assert len(records) == 2

    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_history_entry("latest")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, HistoryScreen)
        table = screen.query_one("#history-table", DataTable)
        assert table.row_count == 2
        assert screen.record_count() == 2
        # Newest first — matches the service ordering.
        assert screen.selected_record().scan_id == records[0].scan_id


@pytest.mark.asyncio
async def test_history_empty_state() -> None:
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_history_entry("latest")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, HistoryScreen)
        assert screen.record_count() == 0
        empty = screen.query_one("#history-empty", Static)
        assert empty.display is True
        assert "No saved scans" in _plain(empty)


@pytest.mark.asyncio
async def test_history_enter_opens_results_with_same_totals() -> None:
    records = _seed_history(1)
    expected = len(records[0].detections)

    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_history_entry("latest")
        await pilot.pause()
        screen = app.screen
        table = screen.query_one("#history-table", DataTable)
        table.focus()
        await pilot.press("enter")
        await wait_until(
            pilot, lambda: isinstance(app.screen, ResultsScreen), timeout=10.0
        )
        assert app.screen.vm.total == expected
        assert app.screen.vm.total > 0


@pytest.mark.asyncio
async def test_history_delete_confirm_removes_entry() -> None:
    _seed_history(2)

    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_history_entry("latest")
        await pilot.pause()
        screen = app.screen
        assert screen.record_count() == 2

        screen.query_one("#history-table", DataTable).focus()
        await pilot.press("d")
        await pilot.pause()
        assert isinstance(app.screen, _ConfirmDeleteScreen)

        await pilot.click("#history-confirm-yes")
        await pilot.pause()
        assert isinstance(app.screen, HistoryScreen)
        assert screen.record_count() == 1


@pytest.mark.asyncio
async def test_history_delete_cancel_keeps_entry() -> None:
    _seed_history(1)

    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_history_entry("latest")
        await pilot.pause()
        screen = app.screen
        screen.query_one("#history-table", DataTable).focus()
        await pilot.press("d")
        await pilot.pause()
        await pilot.click("#history-confirm-no")
        await pilot.pause()
        assert isinstance(app.screen, HistoryScreen)
        assert screen.record_count() == 1


@pytest.mark.asyncio
async def test_history_escape_returns_home() -> None:
    from ecdat.tui.screens.home import HomeScreen

    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_history_entry("latest")
        await pilot.pause()
        assert isinstance(app.screen, HistoryScreen)
        await pilot.press("escape")
        await wait_until(pilot, lambda: isinstance(app.screen, HomeScreen), timeout=10.0)


@pytest.mark.asyncio
async def test_open_history_entry_by_exact_id() -> None:
    records = _seed_history(1)
    scan_id = records[0].scan_id

    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_history_entry(scan_id)
        await wait_until(
            pilot, lambda: isinstance(app.screen, ResultsScreen), timeout=10.0
        )
        assert app.screen.vm.total == len(records[0].detections)
        # Let the freshly-pushed screen's mount callbacks drain before teardown.
        await pilot.pause(0.3)


@pytest.mark.asyncio
async def test_open_history_entry_unknown_id_shows_empty_history() -> None:
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_history_entry("does-not-exist")
        await pilot.pause()
        assert isinstance(app.screen, HistoryScreen)
        await pilot.pause(0.3)


# ---------------------------------------------------------------------------
# Recents strip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recents_strip_click_opens_scan() -> None:
    records = _seed_history(1)

    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        home = app.screen
        panel = home.query_one("#home-recent", Static)

        def recorded() -> bool:
            return bool(getattr(home, "_recents", None))

        await wait_until(pilot, recorded, timeout=10.0)
        # The recents list holds the real record.
        assert home._recents[0].scan_id == records[0].scan_id
        # Clicking the first record line (offset 1) opens that scan.
        await pilot.click(panel, offset=(2, 1))
        await wait_until(
            pilot,
            lambda: isinstance(app.screen, ResultsScreen)
            or isinstance(app.screen, HistoryScreen),
            timeout=10.0,
        )
