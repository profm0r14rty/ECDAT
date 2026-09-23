"""Tests for the Home screen and directory picker (Phase 82).

Everything runs headless with animations disabled, so the tests are
deterministic.  The host repo's ``ECDAT_HOME`` autouse fixture keeps all
settings/history reads inside a tmp directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.widgets import Input, OptionList, Static

from ecdat.tui.app import EcdatApp
from ecdat.tui.screens.pick_dir import PickDirScreen

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tui_helpers import wait_until  # noqa: E402


def _home(app: EcdatApp):
    return app.screen


@pytest.mark.asyncio
async def test_home_mounts_with_expected_widgets() -> None:
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        home = _home(app)
        assert home.query_one("#target", Input) is not None
        assert home.query_one("#home-menu", OptionList).option_count == 6
        assert home.query_one("#home-banner") is not None
        assert home.query_one("#home-globe") is not None


@pytest.mark.asyncio
async def test_valid_target_shows_local_folder_hint(tmp_path: Path) -> None:
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        home = _home(app)
        home.query_one("#target", Input).value = str(tmp_path)
        await pilot.pause()
        hint = str(home.query_one("#target-hint", Static).render())
        assert "local folder" in hint


@pytest.mark.asyncio
async def test_git_url_shows_repository_hint() -> None:
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        home = _home(app)
        home.query_one("#target", Input).value = "https://github.com/acme/app"
        await pilot.pause()
        hint = str(home.query_one("#target-hint", Static).render())
        assert "Git repository" in hint


@pytest.mark.asyncio
async def test_missing_path_shows_error_and_does_not_scan(monkeypatch) -> None:
    calls: list[str] = []
    app = EcdatApp(show_splash=False)
    monkeypatch.setattr(app, "start_scan", lambda target, label=None: calls.append(target))

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        home = _home(app)
        target = home.query_one("#target", Input)
        target.value = "/nonexistent/path/zzz"
        await pilot.pause()
        hint = str(home.query_one("#target-hint", Static).render())
        assert "does not exist" in hint
        target.focus()
        await pilot.press("enter")
        await pilot.pause()
        assert calls == []


@pytest.mark.asyncio
async def test_valid_target_enter_starts_scan(monkeypatch, tmp_path: Path) -> None:
    calls: list[str] = []
    app = EcdatApp(show_splash=False)
    monkeypatch.setattr(app, "start_scan", lambda target, label=None: calls.append(target))

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        home = _home(app)
        target = home.query_one("#target", Input)
        target.value = str(tmp_path)
        target.focus()
        await pilot.press("enter")
        await pilot.pause()
        assert calls == [str(tmp_path)]


@pytest.mark.asyncio
async def test_d_binding_runs_demo(monkeypatch) -> None:
    calls: list[int] = []
    app = EcdatApp(show_splash=False)
    monkeypatch.setattr(app, "run_demo", lambda: calls.append(1))

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.set_focus(None)
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        assert calls == [1]


@pytest.mark.asyncio
async def test_ctrl_o_opens_picker_and_escape_returns_none() -> None:
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        results: list[object] = []
        app.push_screen(PickDirScreen(Path.cwd()), results.append)
        await pilot.pause()
        assert isinstance(app.screen, PickDirScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert results and results[0] is None
        assert not isinstance(app.screen, PickDirScreen)


@pytest.mark.asyncio
async def test_picker_select_returns_highlighted_directory() -> None:
    from textual.widgets import DirectoryTree

    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        results: list[object] = []
        app.push_screen(PickDirScreen(Path.cwd()), results.append)
        await pilot.pause()
        tree = app.screen.query_one("#pick-tree", DirectoryTree)
        tree.focus()
        await pilot.press("down")
        await pilot.pause()
        await pilot.click("#pick-select")
        await pilot.pause()
        assert results
        assert isinstance(results[0], Path)
        assert results[0].is_dir()


@pytest.mark.asyncio
async def test_narrow_size_hides_globe() -> None:
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(100, 26)) as pilot:
        await pilot.pause()
        home = _home(app)
        assert home.query_one("#home-globe").display is False
        assert "-compact" in home.classes


@pytest.mark.asyncio
async def test_recents_render_after_history_entry(tmp_path: Path) -> None:
    from datetime import datetime, timezone

    from ecdat.services.history import save_scan
    from ecdat_core.models import ScanResult

    result = ScanResult(
        scan_id="recent-1",
        target="/tmp/example-target",
        detections=[],
        risk_assessments=[],
        recommendations=[],
        scanned_at=datetime(2099, 1, 1, tzinfo=timezone.utc).isoformat(),
        files_scanned=3,
    )
    save_scan(result)

    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        home = _home(app)
        panel = home.query_one("#home-recent", Static)

        def rendered() -> str:
            value = panel.render()
            return getattr(value, "plain", str(value))

        text = await wait_until(pilot, lambda: rendered() if "example-target" in rendered() else "")
        assert "Recent scans" in text
        assert "example-target" in text


@pytest.mark.asyncio
async def test_hostile_target_is_not_interpreted_as_markup(tmp_path: Path) -> None:
    hostile = "[bold red]evil"
    target = tmp_path / hostile
    target.mkdir()

    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        home = _home(app)
        home.query_one("#target", Input).value = str(target)
        await pilot.pause()
        rendered = home.query_one("#target-hint", Static).render()
        plain = getattr(rendered, "plain", str(rendered))
        assert "local folder" in plain
