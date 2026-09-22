"""Golden-path end-to-end tests through the real TUI (Task B7 / Phase 91).

These drive :class:`~ecdat.tui.app.EcdatApp` headlessly with the Textual pilot
and touch only public surfaces: the Home input, the documented key bindings,
the export dialog, and the History screen.  Animations are off via the repo's
autouse fixture (``ECDAT_ANIM=0``), so every wait is deterministic.

The scan target is the bundled ``demo_repo`` fixture and the scans persist to
the ``ECDAT_HOME`` tmp directory from ``ecdat/tests/conftest.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from textual.widgets import DataTable, Input

from ecdat.tui.app import EcdatApp
from ecdat.tui.screens.export import ExportScreen
from ecdat.tui.screens.history import HistoryScreen
from ecdat.tui.screens.home import HomeScreen
from ecdat.tui.screens.results import ResultsScreen
from ecdat.tui.widgets.findings_table import FindingsPane

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tui_helpers import wait_until  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_REPO = REPO_ROOT / "ecdat_core" / "tests" / "fixtures" / "demo_repo"

_SIZE = (120, 40)


async def _wait_for_results(pilot, timeout: float = 60.0) -> ResultsScreen:
    """Wait until a ResultsScreen is active and return it."""
    await wait_until(
        pilot, lambda: isinstance(pilot.app.screen, ResultsScreen), timeout=timeout
    )
    # Let the freshly-pushed screen's mount callbacks settle.
    await pilot.pause(0.3)
    return pilot.app.screen


# ---------------------------------------------------------------------------
# 1. The full golden path, driven entirely by keys and the input box
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_golden_path_scan_filter_export_history(tmp_path: Path) -> None:
    export_dir = tmp_path / "e2e-bundle"

    app = EcdatApp(show_splash=False)
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, HomeScreen)

        # 1. Type the demo repo into the Home input and press Enter.
        target = app.screen.query_one("#target", Input)
        target.value = str(DEMO_REPO)
        target.focus()
        await pilot.press("enter")
        screen = await _wait_for_results(pilot)
        assert screen.vm.total > 0

        # 2. Open the Findings tab.
        await pilot.press("2")
        await pilot.pause(0.3)
        pane = screen.query_one("#findings-pane", FindingsPane)
        total_rows = screen.query_one("#findings", DataTable).row_count
        assert total_rows == screen.vm.total

        # 3. Filter to critical only.
        await pilot.press("c")
        await pilot.pause(0.3)
        critical_rows = screen.query_one("#findings", DataTable).row_count
        assert critical_rows == screen.vm.counts["critical"]
        assert pane.active_levels() == ["critical"]

        # 4. Export the bundle.
        app.set_focus(None)
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, ExportScreen)
        app.screen.query_one("#export-dir").value = str(export_dir)
        await pilot.click("#export-go")

        await wait_until(
            pilot,
            lambda: isinstance(app.screen, ResultsScreen)
            and (export_dir / "cbom.json").exists()
            and (export_dir / "report.html").exists(),
            timeout=60.0,
        )

        # 5. Back to Home, then into History.
        await pilot.press("n")
        await wait_until(pilot, lambda: isinstance(app.screen, HomeScreen), timeout=10.0)

        app.set_focus(None)
        await pilot.pause()
        await pilot.press("h")
        await wait_until(
            pilot, lambda: isinstance(app.screen, HistoryScreen), timeout=10.0
        )
        history = app.screen
        assert history.record_count() == 1

        # 6. Escape back out.
        await pilot.press("escape")
        await wait_until(pilot, lambda: isinstance(app.screen, HomeScreen), timeout=10.0)
        await pilot.pause(0.3)


# ---------------------------------------------------------------------------
# 2. auto_start reaches Results with no key presses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_start_reaches_results_without_keys() -> None:
    app = EcdatApp(
        initial_target=str(DEMO_REPO),
        auto_start=True,
        show_splash=False,
    )
    async with app.run_test(size=_SIZE) as pilot:
        screen = await _wait_for_results(pilot)
        assert screen.vm.total > 0


# ---------------------------------------------------------------------------
# 3. run_demo reaches Results with findings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_demo_reaches_results_with_findings() -> None:
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.pause()
        app.run_demo()
        screen = await _wait_for_results(pilot)
        assert screen.vm.total > 0


# ---------------------------------------------------------------------------
# 4. demo=True starts the demo scan straight from mount
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_demo_flag_starts_demo_on_mount() -> None:
    app = EcdatApp(show_splash=False, demo=True)
    async with app.run_test(size=_SIZE) as pilot:
        screen = await _wait_for_results(pilot)
        assert screen.vm.total > 0
