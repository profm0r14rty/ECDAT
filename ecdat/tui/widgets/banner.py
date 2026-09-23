"""The shimmering ECDAT banner widget.

Renders :func:`ecdat.ui.banner.banner_text`; when motion is enabled a shimmer
highlight sweeps across it every few seconds.  The plain text never changes —
only the styling does — so the banner is safe to snapshot.
"""

from __future__ import annotations

from typing import Optional

from textual.widgets import Static

from ecdat.services.settings import load_settings
from ecdat.ui import motion
from ecdat.ui.banner import banner_text

# Shimmer sweep timing.
_SWEEP_SECONDS = 2.2
_SWEEP_INTERVAL = 6.0
_TICK_SECONDS = 1.0 / 20.0


class BannerWidget(Static):
    """A gradient banner that optionally shimmers.

    Args:
        **kw: Passed through to :class:`~textual.widgets.Static`.
    """

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self._shimmer: Optional[float] = None
        self._elapsed = 0.0

    def on_mount(self) -> None:
        self._redraw()
        if motion.animations_enabled(load_settings().reduce_motion):
            self.set_interval(_TICK_SECONDS, self._tick)

    def _unicode_ok(self) -> bool:
        encoding = getattr(self.app.console, "encoding", None) or ""
        return encoding.lower().startswith("utf")

    def _redraw(self) -> None:
        self.update(banner_text(unicode=self._unicode_ok(), shimmer=self._shimmer))

    def _tick(self) -> None:
        self._elapsed += _TICK_SECONDS
        cycle = self._elapsed % _SWEEP_INTERVAL
        if cycle < _SWEEP_SECONDS:
            self._shimmer = motion.clamp01(cycle / _SWEEP_SECONDS)
        else:
            self._shimmer = None
        self._redraw()


__all__ = ["BannerWidget"]
