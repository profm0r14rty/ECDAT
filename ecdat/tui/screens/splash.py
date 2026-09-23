"""The decrypt-reveal splash screen.

The banner scrambles through hex glyphs and resolves left-to-right over
``~1.2 s``; any key or click dismisses immediately, and it auto-dismisses after
``~1.8 s``.  With animations disabled it dismisses on mount without drawing.
"""

from __future__ import annotations

import time
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Static

from ecdat.services.settings import load_settings
from ecdat.ui import motion
from ecdat.ui.banner import BANNER_ASCII_LINES, BANNER_LINES, SUBLINE, TAGLINE

_REVEAL_SECONDS = 1.2
_AUTO_DISMISS_SECONDS = 1.8
_TICK_SECONDS = 1.0 / 30.0

_SCRAMBLE_ALPHABET = "0123456789ABCDEF#$%&@"


class SplashScreen(Screen[None]):
    """A short decrypt-reveal intro that auto-dismisses."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Both the auto-dismiss timer and a manual key/click can ask to leave;
        # whichever runs first wins, and every later path becomes a no-op.
        self._dismissed = False
        self._auto_timer: Optional[Timer] = None

    def compose(self) -> ComposeResult:
        with Vertical(id="splash-column"):
            yield Static("", id="splash-art")
            yield Static("", id="splash-tagline")

    def on_mount(self) -> None:
        if not motion.animations_enabled(load_settings().reduce_motion):
            self._dismiss()
            return
        self._started = time.monotonic()
        self._frame = 0
        self.set_interval(_TICK_SECONDS, self._tick)
        self._auto_timer = self.set_timer(_AUTO_DISMISS_SECONDS, self._auto_dismiss)

    def _lines(self) -> tuple[str, ...]:
        encoding = getattr(self.app.console, "encoding", None) or ""
        return BANNER_LINES if encoding.lower().startswith("utf") else BANNER_ASCII_LINES

    def _tick(self) -> None:
        elapsed = time.monotonic() - self._started
        progress = motion.ease_out_cubic(elapsed / _REVEAL_SECONDS)
        self._frame += 1

        lines = self._lines()
        rendered = "\n".join(
            motion.scramble(line, progress, self._frame, alphabet=_SCRAMBLE_ALPHABET)
            for line in lines
        )
        self.query_one("#splash-art", Static).update(rendered)

        tagline = self.query_one("#splash-tagline", Static)
        if progress >= 1.0:
            tagline.update(f"{TAGLINE}\n{SUBLINE}")

    def _stop_auto_timer(self) -> None:
        """Cancel the pending auto-dismiss timer, if one is armed."""
        timer = self._auto_timer
        if timer is not None:
            timer.stop()
            self._auto_timer = None

    def _dismiss(self) -> None:
        """Leave the splash exactly once, and only while it owns the screen.

        The timer and a manual key/click can both request dismissal for the
        same screen; the first one to run wins and every later call returns
        immediately.  The actual pop is deferred one refresh so the decision is
        made against the screen stack *after* everything already queued for
        this tick has been pushed: if something was placed on top of the
        splash (the demo/auto-start launch), ``self.app.screen`` is no longer
        this screen and we must not call ``dismiss()`` — that would resolve an
        already-settled future (``InvalidStateError``) or pop the wrong screen.
        """
        if self._dismissed:
            return
        self._dismissed = True
        self._stop_auto_timer()
        self.call_after_refresh(self._dismiss_if_top)

    def _dismiss_if_top(self) -> None:
        """Pop the splash, but only when it is still the top screen."""
        if self.app.screen is self:
            self.dismiss(None)

    def _auto_dismiss(self) -> None:
        if self.is_current:
            self._dismiss()

    def on_key(self, event) -> None:
        event.stop()
        self._dismiss()

    def on_click(self) -> None:
        self._dismiss()


__all__ = ["SplashScreen"]
