"""MoscaTimeline widget: the per-finding Mosca-inequality bar chart.

Thin Textual wrapper around the **pure** cell generator
:func:`ecdat.ui.render.mosca_timeline_segments`.  The split matters: the cell
maths lives in the engine-adjacent render module (unit-tested there and reused
by the CLI's ``ecdat mosca`` command), while this widget owns only the
token → theme-colour mapping and the resize/re-render lifecycle.

When the selected finding is a classically-broken artefact the exposed window
(the ``gap`` row, drawn from Z out to X + Y) is rendered in the critical colour
— that red band is the whole point of the visual: it is the period during which
data is already exposed.
"""

from __future__ import annotations

from typing import List, Optional

from rich.style import Style
from rich.text import Text
from textual.widgets import Static

from ecdat.ui.render import Row, mosca_timeline_segments
from ecdat.ui.theme import PALETTE

# Fallback width when the widget has not been laid out yet.
_DEFAULT_WIDTH = 64
# Below this the bars degenerate into noise; clamp rather than emit garbage.
_MIN_WIDTH = 16

# The "not enough data" message.
_NO_DATA = "Not enough data to plot Mosca's inequality."


class MoscaTimeline(Static):
    """Horizontal X / Y / Z timeline for one finding's Mosca's inequality.

    Rows produced (see :func:`~ecdat.ui.render.mosca_timeline_segments`):

    - ``NOW ├`` + the X bar (accent) and Y bar (medium) — the time we must
      stay safe.
    - ``NOW ├`` + the Z bar (critical) — the quantum-arrival horizon.
    - when ``X + Y > Z``, a red ``▒`` band from Z to ``X + Y``: the exposed
      window.  This row is absent when the inequality holds.
    - a legend line naming X, Y and Z.

    Args:
        x: Data-lifetime / migration-time component in years, or ``None``.
        y: Shelf-life component in years, or ``None``.
        z: Quantum threat horizon in years, or ``None``.
        id: DOM id.
        classes: Additional CSS classes.
    """

    def __init__(
        self,
        x: Optional[float] = None,
        y: Optional[float] = None,
        z: Optional[float] = None,
        *,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        cls = f"{classes} mosca-timeline" if classes else "mosca-timeline"
        # Seed with an empty Text: a Textual Static with no renderable cannot
        # measure its content height until something is set, which crashes the
        # layout pass before on_mount runs.
        super().__init__(Text(""), id=id, classes=cls)
        self._x = x
        self._y = y
        self._z = z

    # -- public API ---------------------------------------------------------

    def set_values(
        self,
        x: Optional[float],
        y: Optional[float],
        z: Optional[float],
    ) -> None:
        """Replace the plotted values and re-render.

        Any ``None`` switches the widget to its "not enough data" placeholder.
        """
        self._x = x
        self._y = y
        self._z = z
        self._rebuild()

    def has_values(self) -> bool:
        """Return whether all three components are present."""
        return self._x is not None and self._y is not None and self._z is not None

    def has_exposed_window(self) -> bool:
        """Return whether the current plot includes the red exposed-window row.

        True exactly when ``X + Y > Z`` (a Mosca violation) and all values are
        present.
        """
        if not self.has_values():
            return False
        return any(token == "gap" for row in self.segment_rows() for _text, token in row)

    def segment_rows(self) -> List[Row]:
        """Return the raw ``(text, style_token)`` rows for the current width.

        Returns an empty list when there is not enough data to plot.
        """
        if not self.has_values():
            return []
        return mosca_timeline_segments(self._x, self._y, self._z, self._plot_width())

    # -- lifecycle ----------------------------------------------------------

    def on_mount(self) -> None:
        """Render once after the first layout pass gives us a real width."""
        self.call_after_refresh(self._rebuild)

    def on_resize(self, event) -> None:  # noqa: ANN001 - Textual event
        """Re-render at the new width (the bars are width-proportional)."""
        self._rebuild()

    # -- rendering ----------------------------------------------------------

    def _plot_width(self) -> int:
        """Resolve the row width from the current content box."""
        width = self.content_size.width or self.size.width or _DEFAULT_WIDTH
        return max(_MIN_WIDTH, int(width))

    def _token_style(self, token: str) -> Style:
        """Map a timeline token to its theme colour."""
        if token == "x":
            return Style(color=PALETTE.accent)
        if token == "y":
            return Style(color=PALETTE.medium)
        if token == "z":
            return Style(color=PALETTE.critical)
        if token == "gap":
            # The exposed window — the loudest thing on the screen.
            return Style(color=PALETTE.critical, bold=True)
        if token == "label":
            return Style(color=PALETTE.muted)
        return Style()

    def _rebuild(self) -> None:
        """Rebuild the widget content from the current values and width."""
        if not self.has_values():
            self.update(Text(_NO_DATA, style=Style(color=PALETTE.muted, italic=True)))
            return

        lines: List[Text] = []
        for row in self.segment_rows():
            line = Text()
            for text, token in row:
                line.append(text, style=self._token_style(token))
            lines.append(line)

        summary = Text()
        summary.append("X+Y ", style=Style(color=PALETTE.muted))
        summary.append(self._fmt((self._x or 0.0) + (self._y or 0.0)), style="bold")
        summary.append("  \u00b7  Z ", style=Style(color=PALETTE.muted))
        summary.append(self._fmt(self._z or 0.0), style=Style(color=PALETTE.critical, bold=True))
        if self.has_exposed_window():
            summary.append("  \u00b7  exposed window ", style=Style(color=PALETTE.muted))
            summary.append(
                self._fmt((self._x or 0.0) + (self._y or 0.0) - (self._z or 0.0)),
                style=Style(color=PALETTE.critical, bold=True),
            )
            summary.append(" yr", style=Style(color=PALETTE.muted))

        content = Text()
        for i, line in enumerate(lines):
            if i > 0:
                content.append("\n")
            content.append(line)
        content.append("\n")
        content.append(summary)
        self.update(content)

    @staticmethod
    def _fmt(value: float) -> str:
        """Format a year count without a trailing ``.0``."""
        return str(int(value)) if float(value).is_integer() else f"{value:.1f}"


__all__ = ["MoscaTimeline"]
