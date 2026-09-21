"""StatCard widget: big count-up number with caption and risk-coloured border.

All motion is gated by :mod:`ecdat.ui.motion`.  Colours come from
:mod:`ecdat.ui.theme`.  Dynamic values are rendered as
:class:`rich.text.Text` — never interpolated into Rich markup strings.
"""

from __future__ import annotations

from textual.containers import Vertical
from textual.widgets import Digits, Static

from ecdat.services.settings import load_settings
from ecdat.ui import motion
from ecdat.ui.theme import PALETTE, RISK_COLORS

_TOTAL_SECONDS = 0.7
_TICK_SECONDS = 1.0 / 30.0


class StatCard(Vertical):
    """A large count-up number with a caption and a level-coloured border.

    Composes a :class:`~textual.widgets.Digits` (count-up target) and a
    :class:`~textual.widgets.Static` caption.  When motion is enabled the
    number animates from zero to *value* over ~0.7 s.

    Args:
        label: Caption text displayed below the number.
        value: Target integer value for the count-up.
        level: Risk level key determining the border colour
            (``"critical"``, ``"high"``, …).  Also accepts ``"files"`` and
            ``"artefacts"`` which use ``PALETTE.accent``.
        id: DOM id for the card.
        classes: Additional CSS classes.
    """

    def __init__(
        self,
        label: str,
        value: int,
        *,
        level: str = "",
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        cls = f"{classes} stat-card" if classes else "stat-card"
        super().__init__(id=id, classes=cls)
        self._card_label = label
        self._card_value = int(value)
        self._card_level = level
        self._elapsed = 0.0
        self._anim_timer = None

    def compose(self) -> None:
        """Compose the :class:`Digits` and caption :class:`Static`."""
        digits_id: str | None = None
        if self.id:
            digits_id = f"{self.id}-value"
        yield Digits("0", id=digits_id)
        yield Static(self._card_label, classes="stat-label")

    def on_mount(self) -> None:
        """Set the level-coloured border and start the count-up animation."""
        level = self._card_level
        if level in ("files", "artefacts"):
            color = PALETTE.accent
        else:
            color = RISK_COLORS.get(level, PALETTE.border)
        self.styles.border = ("round", color)

        if motion.animations_enabled(load_settings().reduce_motion) and self._card_value > 0:
            self._anim_timer = self.set_interval(_TICK_SECONDS, self._tick)
        else:
            self._set_value(self._card_value)

    def _tick(self) -> None:
        """Advance one animation frame for the count-up."""
        self._elapsed += _TICK_SECONDS
        progress = min(1.0, self._elapsed / _TOTAL_SECONDS)
        current = motion.count_up_value(self._card_value, progress)
        self._set_value(current)
        if progress >= 1.0:
            if self._anim_timer is not None:
                self._anim_timer.stop()
                self._anim_timer = None

    def _set_value(self, value: int) -> None:
        """Set the :class:`Digits` value."""
        self.query_one(Digits).update(str(value))

    @property
    def display_value(self) -> int:
        """The displayed integer (0 when the Digits value is non-numeric or absent)."""
        try:
            return int(self.query_one(Digits).value)
        except (ValueError, TypeError):
            return 0


__all__ = ["StatCard"]