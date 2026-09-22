"""Regression tests for the splash screen's dismissal paths (Task C6).

The decrypt-reveal splash can be dismissed two ways: the auto-dismiss timer
fires, or the user presses a key / clicks.  When both happen for the same
screen, the second ``dismiss()`` used to re-resolve an already-settled result
future — raising ``asyncio.InvalidStateError`` — or pop an unrelated screen.
These tests pin the idempotent single-dismiss behaviour and the timer
disarm on a manual dismiss.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pytest
from textual.app import ComposeResult
from textual.screen import Screen

import ecdat.tui.screens.splash as splash_mod
from ecdat.tui.app import EcdatApp
from ecdat.tui.screens.home import HomeScreen
from ecdat.tui.screens.splash import SplashScreen

_SPLASH = "SplashScreen"
_HOME = "HomeScreen"
_SIZE = (120, 40)


class _KeyEvent:
    """A minimal stand-in for a Textual key event (``on_key`` needs ``stop``)."""

    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class _Overlay(Screen[None]):
    """A screen pushed on top of the splash to model the demo's ScanScreen."""

    def compose(self) -> ComposeResult:
        yield from ()


@pytest.fixture
def anim_on():
    """Force animations on for the duration of a test, then restore."""
    previous: Optional[str] = os.environ.get("ECDAT_ANIM")
    os.environ["ECDAT_ANIM"] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("ECDAT_ANIM", None)
        else:
            os.environ["ECDAT_ANIM"] = previous


def _stack(app: EcdatApp) -> list[str]:
    return [type(screen).__name__ for screen in app.screen_stack]


@pytest.mark.asyncio
async def test_double_dismiss_is_idempotent(anim_on) -> None:
    """Timer fire then keypress must not raise and must not double-pop Home."""
    app = EcdatApp(show_splash=True)
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.pause()
        splash = app.screen
        assert isinstance(splash, SplashScreen)

        splash._auto_dismiss()
        key = _KeyEvent()
        splash.on_key(key)
        await pilot.pause()

        assert key.stopped is True
        assert isinstance(app.screen, HomeScreen)
        assert _stack(app) == ["Screen", _HOME]


@pytest.mark.asyncio
async def test_keypress_then_timer_is_idempotent(anim_on) -> None:
    """The reverse order must behave the same and leave Home exactly once."""
    app = EcdatApp(show_splash=True)
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.pause()
        splash = app.screen
        assert isinstance(splash, SplashScreen)

        splash.on_key(_KeyEvent())
        splash._auto_dismiss()
        await pilot.pause()

        assert isinstance(app.screen, HomeScreen)
        assert _stack(app) == ["Screen", _HOME]


@pytest.mark.asyncio
async def test_dismiss_while_not_top_does_not_raise(anim_on) -> None:
    """A second dismiss on a screen that outlived its own pop must not crash.

    When the splash sits under another screen (as ``ecdat demo --tui`` pushes
    ``ScanScreen`` on top of it), the timer's ``dismiss()`` resolves the
    splash's result future but pops the *overlay*, leaving the splash alive
    with a settled callback.  A later keypress would then re-resolve that
    future — the original ``InvalidStateError``.
    """
    app = EcdatApp(show_splash=True)
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.pause()
        splash = app.screen
        assert isinstance(splash, SplashScreen)

        app.push_screen(_Overlay())
        await pilot.pause()
        assert _stack(app)[-1] == "_Overlay"

        splash._auto_dismiss()
        assert splash in app.screen_stack

        splash.on_key(_KeyEvent())
        await pilot.pause()

        assert _stack(app) == ["Screen", _HOME, _SPLASH]
        assert splash._dismissed is True


@pytest.mark.asyncio
async def test_auto_dismiss_fires_within_the_window(anim_on, monkeypatch) -> None:
    """The auto-dismiss timer still fires on its own when nothing is pressed."""
    monkeypatch.setattr(splash_mod, "_AUTO_DISMISS_SECONDS", 0.2)
    app = EcdatApp(show_splash=True)
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.pause(0.05)
        splash = app.screen
        assert isinstance(splash, SplashScreen)

        await pilot.pause(0.6)

        assert splash._dismissed is True
        assert isinstance(app.screen, HomeScreen)
        assert _stack(app) == ["Screen", _HOME]


@pytest.mark.asyncio
async def test_manual_dismiss_disarms_auto_timer(anim_on, monkeypatch) -> None:
    """A manual keypress stops the pending timer so it can never fire."""
    monkeypatch.setattr(splash_mod, "_AUTO_DISMISS_SECONDS", 0.2)
    app = EcdatApp(show_splash=True)
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.pause(0.05)
        splash = app.screen
        assert isinstance(splash, SplashScreen)
        assert splash._auto_timer is not None

        await pilot.press("x")
        await pilot.pause(0.6)

        assert splash._auto_timer is None
        assert _stack(app) == ["Screen", _HOME]
