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
import sys
from pathlib import Path
from typing import Optional

import pytest
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Static

import ecdat.tui.screens.splash as splash_mod
from ecdat.tui.app import EcdatApp
from ecdat.tui.screens.home import HomeScreen
from ecdat.tui.screens.results import ResultsScreen
from ecdat.tui.screens.splash import SplashScreen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tui_helpers import wait_until  # noqa: E402

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


class _HeaderOverlay(Screen[None]):
    """An overlay that mounts a ``Header`` — the widget whose ``HeaderTitle``
    lookup blew up (``NoMatches``) when the C9b race detached it mid-mount."""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("x")


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
    """A dismiss on a screen that no longer owns the stack must not crash.

    When the splash sits under another screen, ``_dismiss`` stops the timer and
    sets the dismissed flag but deliberately does NOT call ``dismiss()`` — it
    refuses to pop a screen it does not own.  The overlay therefore legitimately
    remains, and a second dismiss (keypress) is a harmless no-op.

    NOTE (Task C9b): the final stack assertion changed from ``[Screen, Home,
    Splash]`` to include the surviving ``_Overlay``.  The old expectation
    encoded the very wrong-screen pop this task removes: the buried splash's
    ``dismiss()`` used to pop the overlay on top of it.  Keeping the splash from
    popping a screen it does not own and asserting the overlay was popped are
    mutually exclusive, so the assertion was corrected rather than the fix.
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

        assert _stack(app) == ["Screen", _HOME, _SPLASH, "_Overlay"]
        assert splash._dismissed is True


@pytest.mark.asyncio
async def test_dismiss_while_buried_does_not_pop_wrong_screen(anim_on) -> None:
    """The C9b regression: a buried splash must not tear down the screen above it.

    ``ecdat demo --tui`` pushes ``ScanScreen`` on top of the splash in the same
    ``on_mount`` tick, so the splash's auto-dismiss timer fires while it is
    buried.  The old code called ``dismiss()`` unconditionally, which popped the
    *overlay* — detaching a screen mid-mount and surfacing as an intermittent
    ``NoMatches: No nodes match 'HeaderTitle' on Header()``.  The overlay here
    mounts a ``Header`` so the same failure mode is exercised; the block simply
    exiting without Textual re-raising any exception is the assertion.
    """
    app = EcdatApp(show_splash=True)
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.pause()
        splash = app.screen
        assert isinstance(splash, SplashScreen)

        app.push_screen(_HeaderOverlay())
        await pilot.pause()
        assert _stack(app)[-1] == "_HeaderOverlay"

        splash._auto_dismiss()
        await pilot.pause()

        assert splash._dismissed is True
        assert "_HeaderOverlay" in _stack(app)


@pytest.mark.asyncio
async def test_demo_launch_never_pushes_splash(anim_on) -> None:
    """A demo launch pushes a second screen immediately, so no splash is pushed.

    Pushing the splash only to bury it under ``ScanScreen`` is exactly the C9b
    race; the fix skips it at the source, so the splash class must never appear
    in the stack.
    """
    app = EcdatApp(demo=True, show_splash=True)
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.pause()
        assert all(
            not isinstance(screen, SplashScreen) for screen in app.screen_stack
        )
        await wait_until(
            pilot, lambda: isinstance(app.screen, ResultsScreen), timeout=30.0
        )
        # Let the freshly-pushed Results screen finish mounting before exit.
        await pilot.pause(0.3)
        assert all(
            not isinstance(screen, SplashScreen) for screen in app.screen_stack
        )


@pytest.mark.asyncio
async def test_auto_dismiss_fires_within_the_window(anim_on, monkeypatch) -> None:
    """The auto-dismiss timer still fires on its own when nothing is pressed."""
    monkeypatch.setattr(splash_mod, "_AUTO_DISMISS_SECONDS", 0.2)
    app = EcdatApp(show_splash=True)
    async with app.run_test(size=_SIZE) as pilot:
        # The timer may already have fired by the time the test body runs (slow
        # CI runners spend longer than the window starting the app).  Poll for
        # the observable end state rather than racing a fixed sleep.
        await wait_until(
            pilot, lambda: isinstance(app.screen, HomeScreen), timeout=3.0
        )
        assert isinstance(app.screen, HomeScreen)
        assert all(not isinstance(s, SplashScreen) for s in app.screen_stack)
        assert _stack(app) == ["Screen", _HOME]


@pytest.mark.asyncio
async def test_manual_dismiss_disarms_auto_timer(anim_on, monkeypatch) -> None:
    """A manual keypress stops the pending timer so it can never fire."""
    # A window far longer than the test itself keeps the timer from firing
    # during setup, so the manual press is provably what dismisses the splash.
    monkeypatch.setattr(splash_mod, "_AUTO_DISMISS_SECONDS", 30.0)
    app = EcdatApp(show_splash=True)
    async with app.run_test(size=_SIZE) as pilot:
        await wait_until(
            pilot, lambda: isinstance(app.screen, SplashScreen), timeout=3.0
        )
        splash = app.screen
        assert splash._auto_timer is not None

        await pilot.press("x")
        await wait_until(
            pilot, lambda: isinstance(app.screen, HomeScreen), timeout=3.0
        )

        assert splash._auto_timer is None
        assert _stack(app) == ["Screen", _HOME]
