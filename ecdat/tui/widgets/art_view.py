"""Animated ``Static`` widgets that render the pure 3D ASCII art.

The maths lives in :mod:`ecdat.ui.art3d` (pure, deterministic); this widget is
only the timer/quality wrapper around it.  All motion is gated by
:mod:`ecdat.ui.motion`, so with animations disabled the widget draws exactly
one static frame and never schedules a timer.
"""

from __future__ import annotations

import time
from typing import Literal

from textual.widgets import Static

from ecdat.services.settings import load_settings
from ecdat.ui import art3d, motion
from ecdat.ui.art_text import frame_to_text
from ecdat.ui.motion import FrameBudget
from ecdat.ui.theme import MINT_GRADIENT

Kind = Literal["globe", "torus"]

# Angle t used for the single static globe frame.
_STATIC_GLOBE_T = 0.6
# Torus rotation angles for the single static frame.
_STATIC_TORUS_A = 0.9
_STATIC_TORUS_B = 0.5

# Minimum content size worth rendering — below this the art is unreadable.
_MIN_WIDTH = 16
_MIN_HEIGHT = 8


class ArtView(Static):
    """A self-animating view of the hex-globe or the torus.

    Args:
        kind: Which renderer to drive — ``"globe"`` or ``"torus"``.
        fps: Target frame rate while animating.
        **kw: Passed through to :class:`~textual.widgets.Static`.
    """

    def __init__(self, kind: Kind = "globe", *, fps: int = 14, **kw) -> None:
        super().__init__(**kw)
        self.kind: Kind = kind
        self.fps = max(1, int(fps))
        self._t = 0.0
        self._a = _STATIC_TORUS_A
        self._b = _STATIC_TORUS_B
        self._last_tick: float | None = None
        self._budget = FrameBudget()
        self._paused = False
        self._frozen = False
        self._timer = None
        self._static = False

    def on_mount(self) -> None:
        if not motion.animations_enabled(load_settings().reduce_motion):
            # ``on_mount`` runs before Textual has laid the widget out, so
            # ``content_size`` is still ``0x0`` here and drawing now would
            # paint a blank frame.  Defer to after the first refresh, when
            # the widget actually has a size.
            self._static = True
            self.call_after_refresh(self._render_static)
            return
        self._timer = self.set_interval(1.0 / self.fps, self._tick)

    def on_resize(self, event) -> None:  # noqa: ANN001 - Textual event
        """Redraw the static frame when motion is off.

        A resize may land before the deferred first draw (or change the size
        afterwards); re-rendering keeps the widget from being stuck blank.
        When animations are enabled the timer owns every redraw, so this is a
        deliberate no-op and existing behaviour is unchanged.
        """
        if self._static:
            self.call_after_refresh(self._render_static)

    def _render_static(self) -> None:
        """Draw the single deterministic frame used when motion is off."""
        if self.kind == "globe":
            frame = art3d.render_globe(_STATIC_GLOBE_T, self._width(), self._height())
        else:
            frame = art3d.render_torus(
                _STATIC_TORUS_A, _STATIC_TORUS_B, self._width(), self._height()
            )
        self.update(frame_to_text(frame, MINT_GRADIENT))

    def _width(self) -> int:
        return max(0, int(self.content_size.width))

    def _height(self) -> int:
        return max(0, int(self.content_size.height))

    def _tick(self) -> None:
        """Advance one animation frame (frame-rate independent)."""
        if self._paused or self._frozen:
            return
        if self.screen is not self.app.screen:
            return

        width, height = self._width(), self._height()
        if width < _MIN_WIDTH or height < _MIN_HEIGHT:
            return

        now = time.monotonic()
        dt = 0.0 if self._last_tick is None else max(0.0, now - self._last_tick)
        self._last_tick = now

        started = time.monotonic()
        if self.kind == "globe":
            self._t += dt * 0.9
            frame = art3d.render_globe(self._t, width, height)
        else:
            self._a += dt * 1.2
            self._b += dt * 0.7
            scale = self._budget.scale
            frame = art3d.render_torus(
                self._a,
                self._b,
                width,
                height,
                step_theta=0.07 * scale,
                step_phi=0.04 * scale,
            )
        self.update(frame_to_text(frame, MINT_GRADIENT))

        self._budget.record(time.monotonic() - started)
        if self._budget.disabled:
            self._freeze()

    def _freeze(self) -> None:
        """Stop animating and keep the last frame on screen."""
        self._frozen = True
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def pause(self) -> None:
        """Pause animation without discarding the current frame."""
        self._paused = True

    def resume(self) -> None:
        """Resume animation after :meth:`pause`."""
        self._paused = False
        self._last_tick = None


__all__ = ["ArtView"]
