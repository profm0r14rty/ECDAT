"""RiskChart widget: animated risk-distribution rows and a quantum-readiness gauge.

All motion is gated by :mod:`ecdat.ui.motion`.  Colours come from
:mod:`ecdat.ui.theme`.  Dynamic values are rendered as
:class:`rich.text.Text` — never interpolated into Rich markup strings.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import List

from rich.style import Style
from rich.text import Text
from textual.widgets import Static

from ecdat.services.settings import load_settings
from ecdat.ui import motion
from ecdat.ui.render import risk_chip, smooth_bar
from ecdat.ui.theme import PALETTE, RISK_ORDER, lerp_hex

_TOTAL_SECONDS = 0.6
_TICK_SECONDS = 1.0 / 30.0
_DEFAULT_WIDTH = 40
_MIN_WIDTH = 10

# Unicode eighth-block characters for manual bar building.
_UNICODE_EIGHTHS = "\u258f\u258e\u258d\u258c\u258b\u258a\u2589\u2588"  # ▏▎▍▌▋▊▉█


class RiskChart(Static):
    """Five risk rows plus a quantum-readiness gauge, animated from zero.

    Each risk row (critical, high, medium, low, quantum-safe) shows a
    coloured chip, a horizontal bar proportional to its count fraction, and
    a ``count (pct%)`` label.  Below the rows a quantum-readiness gauge
    renders a bar whose colour interpolates from critical (0%) through
    medium (50%) to safe (100%).

    Args:
        counts: Mapping of risk level to artefact count.
        total: Total number of artefacts (may be 0).
        readiness: Quantum-readiness fraction in ``[0, 1]``.
        id: DOM id.
        classes: Additional CSS classes.
    """

    def __init__(
        self,
        counts: Mapping[str, int],
        total: int,
        *,
        readiness: float = 0.0,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        cls = f"{classes} risk-chart" if classes else "risk-chart"
        super().__init__(id=id, classes=cls)
        self._counts = dict(counts)
        self._total = int(total)
        self._readiness = float(readiness)
        self._anim_progress = 0.0
        self._anim_timer = None

    def row_levels(self) -> List[str]:
        """Return the five risk levels in canonical display order.

        Returns:
            ``["critical", "high", "medium", "low", "quantum-safe"]``.
        """
        return list(RISK_ORDER)

    def final_fractions(self) -> List[float]:
        """Return the final per-row fraction (count / total) for each risk level.

        When *total* is 0 every fraction is 0.0.
        """
        if self._total == 0:
            return [0.0] * len(RISK_ORDER)
        return [self._counts.get(level, 0) / self._total for level in RISK_ORDER]

    def gauge_label(self) -> str:
        """Build the quantum-readiness label text."""
        clamped = motion.clamp01(self._readiness)
        return f"Quantum readiness {round(clamped * 100)}%"

    def on_mount(self) -> None:
        """Render the initial frame and start the animation timer."""
        self._render_chart()
        if motion.animations_enabled(load_settings().reduce_motion):
            self._anim_timer = self.set_interval(_TICK_SECONDS, self._tick)

    def _tick(self) -> None:
        """Advance one animation frame."""
        self._anim_progress += _TICK_SECONDS / _TOTAL_SECONDS
        self._render_chart()
        if self._anim_progress >= 1.0:
            if self._anim_timer is not None:
                self._anim_timer.stop()
                self._anim_timer = None

    def _bar_width(self) -> int:
        """Derive the bar width from the widget content size.

        Returns at least ``_MIN_WIDTH`` and falls back to ``_DEFAULT_WIDTH``
        when the content size is unknown.
        """
        content_w = self.content_size.width
        if content_w and content_w > 0:
            w = int(content_w)
        else:
            w = _DEFAULT_WIDTH
        # Allocate ~60% of width to the bar itself (rest is chip + label).
        bar_w = max(_MIN_WIDTH, w - 28)
        return bar_w

    def _current_fractions(self) -> List[float]:
        """Return the eased fractions for the current animation frame."""
        if not motion.animations_enabled(load_settings().reduce_motion):
            return self.final_fractions()
        eased = motion.ease_out_cubic(min(1.0, self._anim_progress))
        return [f * eased for f in self.final_fractions()]

    def _render_chart(self) -> None:
        """Render the full chart as one :class:`~rich.text.Text`."""
        bar_w = self._bar_width()
        fractions = self._current_fractions()
        final = self.final_fractions()
        levels = self.row_levels()

        rows: list[Text] = []
        for i, level in enumerate(levels):
            count = self._counts.get(level, 0)
            row = Text()
            # risk chip
            row.append(risk_chip(level))
            row.append(" ")
            # animated smooth bar
            row.append(smooth_bar(fractions[i], bar_w))
            # count and percentage (use final percentages, not animated)
            pct = round(final[i] * 100)
            row.append(Text(f"  {count}  {pct}%"))
            rows.append(row)

        # Readiness gauge row.
        clamped = motion.clamp01(self._readiness)
        rows.append(Text())  # blank separator line
        label = self.gauge_label()
        rows.append(Text(label, style=Style(color=PALETTE.muted)))
        rows.append(self._build_gauge_bar(clamped, bar_w))

        result = Text()
        for i, row in enumerate(rows):
            if i > 0:
                result.append("\n")
            result.append(row)
        self.update(result)

    @staticmethod
    def _build_gauge_bar(readiness: float, width: int) -> Text:
        """Build a horizontal gauge bar colour-interpolated by *readiness*.

        Colour is ``PALETTE.critical → PALETTE.medium`` for ``readiness`` in
        ``[0, 0.5)``, and ``PALETTE.medium → PALETTE.safe`` for ``[0.5, 1]``.
        """
        if readiness < 0.5:
            t = motion.clamp01(readiness / 0.5)
            gauge_color = lerp_hex(PALETTE.critical, PALETTE.medium, t)
        else:
            t = motion.clamp01((readiness - 0.5) / 0.5)
            gauge_color = lerp_hex(PALETTE.medium, PALETTE.safe, t)

        fraction = max(0.0, min(1.0, readiness))
        filled = fraction * width
        full_cells = int(filled)
        frac_part = filled - full_cells

        bar = Text()
        fill_style = Style(color=gauge_color)
        empty_style = Style(color=PALETTE.muted)

        for i in range(width):
            if i < full_cells:
                bar.append("\u2588", style=fill_style)
            elif i == full_cells and frac_part > 0:
                eig_idx = min(7, int(frac_part * 8))
                if eig_idx > 0:
                    bar.append(_UNICODE_EIGHTHS[eig_idx - 1], style=fill_style)
                else:
                    bar.append(" ", style=empty_style)
            else:
                bar.append(" ", style=empty_style)

        return bar


__all__ = ["RiskChart"]