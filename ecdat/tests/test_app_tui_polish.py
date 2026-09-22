"""Pilot tests for the TUI polish pass (Task B7 / Phase 88).

Covers the help overlay, the command palette, theme/animations persistence,
the terminal-too-small guard, and the crash-safe launcher.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from textual.widgets import Static

from ecdat.services.scanner import classify_target, perform_scan
from ecdat.tui import app as app_module
from ecdat.tui.app import EcdatApp, TooSmallScreen, run_tui
from ecdat.tui.screens.help import HelpScreen
from ecdat.tui.screens.home import HomeScreen
from ecdat.tui.screens.results import ResultsScreen
from ecdat.tui.theme import THEME_NAMES

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tui_helpers import wait_until  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_REPO = REPO_ROOT / "ecdat_core" / "tests" / "fixtures" / "demo_repo"


def _settings() -> dict:
    path = Path(os.environ["ECDAT_HOME"]) / "settings.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _outcome():
    return perform_scan(classify_target(str(DEMO_REPO)), label="demo", save_history=False)


# ---------------------------------------------------------------------------
# Help overlay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_question_mark_opens_and_closes_help() -> None:
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, HomeScreen)
        app.set_focus(None)
        await pilot.pause()

        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)

        await pilot.press("question_mark")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)


@pytest.mark.asyncio
async def test_help_closes_on_escape_and_q() -> None:
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.set_focus(None)
        await pilot.pause()

        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)

        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("q")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)


@pytest.mark.asyncio
async def test_help_lists_screens_and_version() -> None:
    from ecdat import __version__

    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.set_focus(None)
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()

        content = app.screen.query_one("#help-content", Static)
        rendered = content.render()
        plain = getattr(rendered, "plain", str(rendered))

        for heading in ("Global", "Home", "Scan", "Results", "Findings"):
            assert heading in plain
        assert __version__ in plain
        assert "ECDAT_ANIM" in plain


# ---------------------------------------------------------------------------
# Command palette
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_palette_includes_ecdats_commands() -> None:
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        titles = [cmd.title for cmd in app.get_system_commands(app.screen)]
        for expected in (
            "Run demo",
            "Toggle animations",
            "New scan",
            "Recent scans",
            "Cycle theme",
            "Show keyboard help",
        ):
            assert expected in titles, f"{expected!r} missing from {titles}"


@pytest.mark.asyncio
async def test_palette_keeps_textual_builtins() -> None:
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        titles = [cmd.title for cmd in app.get_system_commands(app.screen)]
        # Textual's own system commands are still present.
        assert any("Quit" in t or "Theme" in t for t in titles)
        assert len(titles) > 6


@pytest.mark.asyncio
async def test_export_command_only_on_results() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        home_titles = [c.title for c in app.get_system_commands(app.screen)]
        assert "Export results" not in home_titles

        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        result_titles = [c.title for c in app.get_system_commands(app.screen)]
        assert "Export results" in result_titles


@pytest.mark.asyncio
async def test_toggle_animations_persists_reduce_motion() -> None:
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert _settings().get("reduce_motion", False) is False

        app.action_toggle_animations()
        await pilot.pause()
        assert _settings()["reduce_motion"] is True

        app.action_toggle_animations()
        await pilot.pause()
        assert _settings()["reduce_motion"] is False


def test_shortcut_opens_command_palette() -> None:
    """ctrl+p is Textual's default palette binding and stays enabled."""
    assert EcdatApp.ENABLE_COMMAND_PALETTE is True


# ---------------------------------------------------------------------------
# Theme cycling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_saved_theme_falls_back_to_dark() -> None:
    path = Path(os.environ["ECDAT_HOME"]) / "settings.json"
    path.write_text(json.dumps({"theme": "no-such-theme"}), encoding="utf-8")

    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.theme == THEME_NAMES[0] == "ecdat-dark"


@pytest.mark.asyncio
async def test_theme_cycle_persists_chosen_theme() -> None:
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.set_focus(None)
        await pilot.pause()
        before = app.theme
        await pilot.press("t")
        await pilot.pause()
        assert app.theme != before
        assert _settings()["theme"] == app.theme


# ---------------------------------------------------------------------------
# Terminal-too-small guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_too_small_overlay_appears_and_clears_on_resize() -> None:
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(60, 20)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, TooSmallScreen)
        message = app.screen.query_one("#too-small-message", Static)
        rendered = message.render()
        plain = getattr(rendered, "plain", str(rendered))
        assert "80" in plain and "24" in plain

        await pilot.resize_terminal(100, 30)
        await pilot.pause()
        await pilot.pause()
        assert not isinstance(app.screen, TooSmallScreen)
        assert isinstance(app.screen, HomeScreen)


@pytest.mark.asyncio
async def test_adequate_size_has_no_overlay() -> None:
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert not isinstance(app.screen, TooSmallScreen)


# ---------------------------------------------------------------------------
# Crash-safe launcher
# ---------------------------------------------------------------------------


def test_run_tui_crash_returns_3_and_writes_crash_log(
    monkeypatch, capsys
) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.delenv("TERM", raising=False)

    def _boom(self) -> None:
        raise RuntimeError("synthetic TUI crash")

    monkeypatch.setattr(EcdatApp, "run", _boom)

    rc = run_tui()
    captured = capsys.readouterr()
    assert rc == 3
    assert "unexpected error" in captured.err.lower()

    logs = sorted((Path(os.environ["ECDAT_HOME"]) / "logs").glob("crash-*.log"))
    assert logs, "expected a crash log to be written"
    assert "synthetic TUI crash" in logs[-1].read_text(encoding="utf-8")


def test_run_tui_keyboard_interrupt_returns_130(monkeypatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.delenv("TERM", raising=False)

    def _interrupt(self) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(EcdatApp, "run", _interrupt)
    assert run_tui() == 130


def test_run_tui_non_tty_still_returns_2(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    rc = run_tui()
    captured = capsys.readouterr()
    assert rc == 2
    assert "interactive terminal" in captured.err


def test_run_tui_accepts_demo_parameter() -> None:
    import inspect

    signature = inspect.signature(app_module.run_tui)
    assert "demo" in signature.parameters
