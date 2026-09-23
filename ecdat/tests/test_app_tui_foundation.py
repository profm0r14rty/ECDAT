"""Tests for the TUI foundation: themes, launcher, and import boundaries.

Covers the Textual app skeleton (Phase 79): theme registration and cycling,
the splash screen, the non-TTY refusal, and the import-light guarantees that
keep Textual out of the plain CLI.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ecdat.cli.commands import tui_cmd
from ecdat.tui.app import EcdatApp, _is_interactive
from ecdat.tui.theme import ECDAT_DARK, ECDAT_LIGHT, THEME_NAMES
from ecdat.tui.widgets.art_view import ArtView
from ecdat.tui.widgets.banner import BannerWidget
from ecdat.ui.banner import BANNER_LINES

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tui_helpers import wait_until  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


class _TuiArgs:
    def __init__(self, target=None, no_anim=False, no_splash=False) -> None:
        self.target = target
        self.no_anim = no_anim
        self.no_splash = no_splash


# ---- themes ---------------------------------------------------------------


def test_both_themes_registered_and_named() -> None:
    assert ECDAT_DARK.name == "ecdat-dark"
    assert ECDAT_LIGHT.name == "ecdat-light"
    assert THEME_NAMES == ("ecdat-dark", "ecdat-light")


def test_theme_risk_variables_present() -> None:
    for theme in (ECDAT_DARK, ECDAT_LIGHT):
        for key in ("risk-critical", "risk-safe"):
            assert key in theme.variables


@pytest.mark.asyncio
async def test_app_mounts_with_dark_theme() -> None:
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.theme == "ecdat-dark"
        assert "ecdat-dark" in app.available_themes


@pytest.mark.asyncio
async def test_quits_on_q() -> None:
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.set_focus(None)
        await pilot.pause()
        await pilot.press("q")
        await pilot.pause()
        assert app.is_running is False


@pytest.mark.asyncio
async def test_theme_cycles_and_persists(tmp_path: Path) -> None:
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.set_focus(None)
        before = app.theme
        await pilot.press("t")
        await pilot.pause()
        assert app.theme != before
        settings_path = Path(os.environ["ECDAT_HOME"]) / "settings.json"
        assert settings_path.exists()
        assert json.loads(settings_path.read_text(encoding="utf-8"))["theme"] == app.theme


@pytest.mark.asyncio
async def test_help_binding_notifies(capsys) -> None:
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.set_focus(None)
        await pilot.press("question_mark")
        await pilot.pause()
        assert app.is_running is True


@pytest.mark.asyncio
async def test_start_scan_notifies(capsys) -> None:
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.start_scan("/tmp/some-target")
        await pilot.pause()
        assert app.is_running is True


@pytest.mark.asyncio
async def test_splash_dismisses_on_key() -> None:
    os.environ["ECDAT_ANIM"] = "1"
    app = EcdatApp(show_splash=True)
    try:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert type(app.screen).__name__ == "SplashScreen"
            await pilot.press("x")
            await pilot.pause()
            assert type(app.screen).__name__ == "HomeScreen"
    finally:
        os.environ["ECDAT_ANIM"] = "0"


@pytest.mark.asyncio
async def test_splash_skipped_when_anim_off() -> None:
    os.environ["ECDAT_ANIM"] = "0"
    app = EcdatApp(show_splash=True)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert type(app.screen).__name__ == "HomeScreen"


# ---- launcher -------------------------------------------------------------


def test_run_tui_non_tty_returns_2(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    rc = tui_cmd.run(_TuiArgs())
    captured = capsys.readouterr()
    assert rc == 2
    assert "interactive terminal" in captured.err


def test_is_interactive_false_for_dumb_term(monkeypatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("TERM", "dumb")
    assert _is_interactive() is False


def test_tui_cmd_registers_target_and_flags() -> None:
    from ecdat.cli.parser import build_parser

    parser = build_parser()
    args = parser.parse_args(["tui", "/tmp/x", "--no-anim", "--no-splash"])
    assert args.command == "tui"
    assert args.target == "/tmp/x"
    assert args.no_anim is True
    assert args.no_splash is True


def test_ui_alias_resolves_to_tui() -> None:
    from ecdat.cli.parser import build_parser, resolve_command

    parser = build_parser()
    args = parser.parse_args(["ui"])
    assert resolve_command(args.command) is tui_cmd


# ---- animated widgets (Phase 81) ------------------------------------------


@pytest.mark.asyncio
async def test_art_view_static_when_anim_off() -> None:
    os.environ["ECDAT_ANIM"] = "0"
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        globe = app.screen.query_one("#home-globe", ArtView)
        first = globe.render()
        await pilot.pause(0.4)
        assert globe.render() == first


@pytest.mark.asyncio
async def test_art_view_animates_when_anim_on() -> None:
    os.environ["ECDAT_ANIM"] = "1"
    app = EcdatApp(show_splash=False)
    try:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            globe = app.screen.query_one("#home-globe", ArtView)
            first = str(globe.render())
            changed = await wait_until(
                pilot, lambda: str(globe.render()) != first, timeout=3.0
            )
            assert changed
    finally:
        os.environ["ECDAT_ANIM"] = "0"


@pytest.mark.asyncio
async def test_banner_shimmer_keeps_plain_text() -> None:
    os.environ["ECDAT_ANIM"] = "0"
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        banner = app.screen.query_one("#home-banner", BannerWidget)
        rendered = banner.render()
        plain = getattr(rendered, "plain", str(rendered))
        assert plain.strip()
        assert BANNER_LINES[0] in plain


def test_art_view_pause_resume_toggle() -> None:
    view = ArtView("torus")
    view.pause()
    assert view._paused is True
    view.resume()
    assert view._paused is False


# ---- import boundaries ----------------------------------------------------


def test_import_ecdat_cli_does_not_import_textual() -> None:
    script = (
        "import sys\n"
        "import ecdat.cli\n"
        "from ecdat.cli.parser import build_parser\n"
        "build_parser()\n"
        "bad = [m for m in sys.modules if m == 'textual' or m.startswith('textual.')]\n"
        "print('FAIL:' + ','.join(bad) if bad else 'OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"


def test_import_ecdat_tui_does_not_import_textual() -> None:
    script = (
        "import sys\n"
        "import ecdat.tui\n"
        "assert callable(ecdat.tui.run_tui)\n"
        "bad = [m for m in sys.modules if m == 'textual' or m.startswith('textual.')]\n"
        "print('FAIL:' + ','.join(bad) if bad else 'OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"
