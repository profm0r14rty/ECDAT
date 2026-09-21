"""The decrypt-reveal splash screen.

The banner scrambles through hex glyphs and resolves left-to-right over
``~1.2 s``; any key or click dismisses immediately, and it auto-dismisses after
``~1.8 s``.  With animations disabled it dismisses on mount without drawing.
"""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
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

    def compose(self) -> ComposeResult:
        with Vertical(id="splash-column"):
            yield Static("", id="splash-art")
            yield Static("", id="splash-tagline")

    def on_mount(self) -> None:
        if not motion.animations_enabled(load_settings().reduce_motion):
            self.dismiss(None)
            return
        self._started = time.monotonic()
        self._frame = 0
        self.set_interval(_TICK_SECONDS, self._tick)
        self.set_timer(_AUTO_DISMISS_SECONDS, self._auto_dismiss)

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

    def _auto_dismiss(self) -> None:
        if self.is_current:
            self.dismiss(None)

    def on_key(self, event) -> None:
        event.stop()
        self.dismiss(None)

    def on_click(self) -> None:
        self.dismiss(None)


__all__ = ["SplashScreen"]
