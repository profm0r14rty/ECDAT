"""Motion / animation policy and pure animation helpers.

Every animation in the app goes through this module so motion can be switched
off in one place (CI, ``TERM=dumb``, ``--no-anim``, ``ECDAT_ANIM=0``,
reduce-motion) and so the visual helpers stay deterministic and unit-testable.

Public API:
    - :func:`animations_enabled` — the motion policy switch.
    - :func:`clamp01`, :func:`ease_out_cubic`, :func:`count_up_value` — scalar
      easing helpers.
    - :func:`scramble` — the deterministic decrypt-reveal text effect.
    - :class:`FrameBudget` — adaptive-quality controller for render loops.
"""

from __future__ import annotations

import os
from collections import deque
from typing import Mapping, Optional

DEFAULT_SCRAMBLE_ALPHABET = "0123456789ABCDEF#$%&@"


def animations_enabled(
    reduce_motion: bool = False,
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """Return ``True`` when animations should play.

    Resolution order (first match wins):

    1. ``ECDAT_ANIM`` env var — ``"0"``/``"off"``/``"false"``/``"no"`` →
       ``False``; ``"1"``/``"on"``/``"true"``/``"yes"`` → ``True``.
    2. If *reduce_motion* is ``True`` → ``False``.
    3. If running under CI (``CI`` env var set to anything truthy) → ``False``.
    4. If running under pytest (``PYTEST_CURRENT_TEST`` set) → ``False``.
    5. If ``TERM`` is ``"dumb"`` → ``False``.
    6. Otherwise → ``True`` (default: animations on).

    Args:
        reduce_motion: Caller-level reduced-motion flag (e.g. from
                       ``prefers-reduced-motion``).
        env: Environment mapping; defaults to :data:`os.environ`.

    Returns:
        ``True`` if animations should play.
    """
    if env is None:
        env = os.environ

    anim = env.get("ECDAT_ANIM", "").strip().lower()
    if anim:
        if anim in ("0", "off", "false", "no"):
            return False
        if anim in ("1", "on", "true", "yes"):
            return True

    if reduce_motion:
        return False

    if env.get("CI", "").strip():
        return False

    if env.get("PYTEST_CURRENT_TEST", "").strip():
        return False

    if env.get("TERM", "").strip().lower() == "dumb":
        return False

    return True


def clamp01(value: float) -> float:
    """Clamp *value* to the closed interval ``[0.0, 1.0]``."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def ease_out_cubic(progress: float) -> float:
    """Ease *progress* (clamped to ``[0, 1]``) with a cubic ease-out curve."""
    p = clamp01(progress)
    return 1.0 - (1.0 - p) ** 3


def count_up_value(target: int, progress: float) -> int:
    """Return the eased running value for a count-up animation.

    Args:
        target: The final integer value.
        progress: Animation progress; ``>= 1`` returns *target* exactly.

    Returns:
        ``0`` at or below progress ``0``, *target* at or above ``1``, and an
        eased intermediate integer in between.
    """
    if progress >= 1.0:
        return target
    if progress <= 0.0:
        return 0
    return int(round(target * ease_out_cubic(progress)))


def scramble(
    final: str,
    progress: float,
    frame: int,
    *,
    alphabet: str = DEFAULT_SCRAMBLE_ALPHABET,
) -> str:
    """Return *final* progressively revealed by a deterministic scramble.

    Characters whose index is below ``int(progress * len(final))`` are shown
    as-is; every other character is replaced by a glyph from *alphabet* chosen
    deterministically from its index and *frame*.  Spaces always stay spaces,
    so the text's shape never jumps.  ``progress >= 1`` returns *final*.

    Args:
        final: The fully revealed string.
        progress: Reveal progress (``0`` → fully scrambled, ``1`` → final).
        frame: Animation frame counter (changes the scrambled glyphs).
        alphabet: Replacement glyph set; must be non-empty.

    Returns:
        A string the same length as *final*.
    """
    if progress >= 1.0 or not final:
        return final
    if not alphabet:
        return final

    keep = int(progress * len(final))
    n_alphabet = len(alphabet)
    out: list[str] = []
    for index, char in enumerate(final):
        if char == " " or index < keep:
            out.append(char)
        else:
            out.append(alphabet[(index * 31 + frame * 17) % n_alphabet])
    return "".join(out)


class FrameBudget:
    """Adaptive-quality controller for an animation render loop.

    The loop records each frame's render cost; :attr:`scale` reports how much
    to coarsen the next render (``1.0`` = full quality).  Tier changes use
    hysteresis so the quality does not flap between frames, and :attr:`disabled`
    latches once rendering is clearly too slow, so the caller can freeze.
    """

    def __init__(self, target_ms: float = 45.0, window: int = 12) -> None:
        self.target_ms = float(target_ms)
        self.window = max(1, int(window))
        self._samples: deque[float] = deque(maxlen=self.window)
        self._tier = 0
        self._disabled = False

    def record(self, cost_s: float) -> None:
        """Record one frame's render cost in seconds."""
        self._samples.append(float(cost_s) * 1000.0)
        self._update_tier()

    @property
    def average_ms(self) -> float:
        """Mean render cost over the current window (0.0 when empty)."""
        if not self._samples:
            return 0.0
        return sum(self._samples) / len(self._samples)

    def _update_tier(self) -> None:
        if self._disabled:
            return
        average = self.average_ms
        slow = self.target_ms
        slower = 2.0 * self.target_ms
        release = 0.85  # hysteresis: drop a tier only below 85% of the threshold

        if self._tier == 0:
            if average > slow:
                self._tier = 1
        elif self._tier == 1:
            if average > slower:
                self._tier = 2
            elif average < slow * release:
                self._tier = 0
        else:
            if average < slower * release:
                self._tier = 1 if average >= slow else 0

        if len(self._samples) >= self.window and all(
            sample > 4.0 * self.target_ms for sample in self._samples
        ):
            self._disabled = True

    @property
    def scale(self) -> float:
        """Quality factor: ``1.0`` normal, ``1.6`` slow, ``2.4`` very slow."""
        return (1.0, 1.6, 2.4)[self._tier]

    @property
    def disabled(self) -> bool:
        """``True`` once the rolling average stayed above 4x target."""
        return self._disabled

    def reset(self) -> None:
        """Clear all samples and restore full quality."""
        self._samples.clear()
        self._tier = 0
        self._disabled = False


__all__ = [
    "DEFAULT_SCRAMBLE_ALPHABET",
    "FrameBudget",
    "animations_enabled",
    "clamp01",
    "count_up_value",
    "ease_out_cubic",
    "scramble",
]
