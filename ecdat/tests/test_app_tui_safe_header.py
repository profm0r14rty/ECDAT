"""Regression tests for the Header/HeaderTitle teardown race (Task C11).

Textual's ``Header._on_mount`` delays its title update: every watched
title/subtitle change — including the four fired at mount — queues an async
``set_title`` coroutine on the *header's own* message pump (``call_next``).
Its ``except NoScreen`` guard only covers the header's *screen* going away.
If the header widget itself is detached while that coroutine is still queued,
``query_one(HeaderTitle)`` instead raises
``NoMatches: No nodes match 'HeaderTitle' on Header()``, which escapes
``App.run_test()`` — the intermittent CI failure in
``test_recents_strip_click_opens_scan`` (a recents click does a ``switch_screen``
a moment after the Home header has queued title work).

These tests pin both halves of the claim against the deterministic harness
below:

* the exact sequence makes plain ``Header`` raise ``NoMatches`` — proving the
  harness reproduces the CI failure mode; and
* the same sequence with :class:`ecdat.tui.widgets.header.SafeHeader` lets
  ``run_test``'s ``async with`` exit cleanly.

The harness mirrors the CI timing without a race: set a title (queues
``set_title``), ``push_screen`` a fresh screen (its header mounts and queues
more), and ``switch_screen`` in the same tick — which pops the pushed screen
while its header's coroutines are still pending.  The block exiting with no
exception *is* the assertion for the fixed widget.
"""

from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console
from textual.app import App, ComposeResult
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Header, Static
from textual.widgets._header import HeaderTitle

from ecdat.tui.widgets.header import SafeHeader

_SIZE = (120, 40)


class _PlainHeaderScreen(Screen[None]):
    """A minimal screen composing Textual's stock ``Header``."""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("x")


class _SafeHeaderScreen(Screen[None]):
    """The same screen composing ``SafeHeader``."""

    def compose(self) -> ComposeResult:
        yield SafeHeader()
        yield Static("x")


class _ReproApp(App[None]):
    """App that mounts the first screen of the push/switch sequence on start."""

    def __init__(self, screen_cls) -> None:
        super().__init__()
        self._screen_cls = screen_cls

    def on_mount(self) -> None:
        self.push_screen(self._screen_cls())


def _queue_title_update_and_torn_down(app: _ReproApp, pilot) -> None:
    """Reproduce the CI race: tear a header down with title work still queued.

    ``app.title = ...`` fires every ``set_title`` watcher registered on the
    mounted header.  ``push_screen`` mounts a second screen+header in the same
    tick (its mount-time watchers queue immediately), and ``switch_screen``
    pops it again before those pending coroutines have flushed — so they run
    on a header whose ``HeaderTitle`` child is already gone.
    """
    app.title = "pending title change"
    app.push_screen(type(app.screen)())
    app.switch_screen(type(app.screen)())


@pytest.mark.asyncio
async def test_plain_header_raises_no_matches_on_teardown_race() -> None:
    """Stock Header throws — documents the bug the harness reproduces."""
    app = _ReproApp(_PlainHeaderScreen)
    with pytest.raises(NoMatches):
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.pause()
            _queue_title_update_and_torn_down(app, pilot)
            await pilot.pause(0.3)
            assert app.is_running


@pytest.mark.asyncio
async def test_safe_header_survives_teardown_race() -> None:
    """The fix: the same sequence must never escape ``run_test``'s block."""
    app = _ReproApp(_SafeHeaderScreen)
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.pause()
        _queue_title_update_and_torn_down(app, pilot)
        await pilot.pause(0.3)
        # The switch took effect and the app is still alive.
        assert type(app.screen) is _SafeHeaderScreen
        assert app.is_running
    # Exiting the ``async with`` without an exception IS the regression guard.


@pytest.mark.asyncio
async def test_safe_header_still_updates_title_when_mounted() -> None:
    """The faithful-copy behaviour is intact: a live header tracks the title."""
    app = _ReproApp(_SafeHeaderScreen)
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.pause()
        header = app.screen.query_one(SafeHeader)
        app.title = "ECDAT-C11-TITLE"
        await pilot.pause()
        buffer = StringIO()
        console = Console(file=buffer, width=120, no_color=True)
        console.print(header.query_one(HeaderTitle).render())
        assert "ECDAT-C11-TITLE" in buffer.getvalue()
        assert app.is_running