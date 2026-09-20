"""Convert 3D frame data into gradient-coloured Rich Text.

Consumes :class:`Frame` from :mod:`ecdat.ui.art3d` and produces
:class:`~rich.text.Text` objects suitable for rendering.
"""

from __future__ import annotations

from typing import Sequence

from rich.style import Style
from rich.text import Text

from ecdat.ui.theme import MINT_GRADIENT

Frame = Sequence[Sequence[tuple[str, int]]]


def frame_to_text(
    frame: Frame,
    gradient: list[str] | None = None,
) -> Text:
    """Convert a :class:`Frame` into gradient-coloured :class:`~rich.text.Text`.

    Level 0 cells map to a space with no style.  Level *n* (≥ 1) maps to
    ``gradient[min(n, len(gradient)) - 1]``.  Consecutive cells at the same
    level are merged into a single :class:`~rich.text.Text` run to keep the
    output compact.

    Args:
        frame: A sequence of rows, each a sequence of ``(char, level)`` tuples.
        gradient: Colour gradient (12 hex colours by default);
                  defaults to :data:`~ecdat.ui.theme.MINT_GRADIENT`.

    Returns:
        A :class:`~rich.text.Text` ready for ``console.print()``.
    """
    if gradient is None:
        gradient = MINT_GRADIENT
    n_colors = len(gradient)

    text = Text()
    for ri, row in enumerate(frame):
        if ri > 0:
            text.append("\n")
        if not row:
            continue

        # Run-length encode consecutive same-level cells.
        prev_level = -1  # sentinel
        run_chars: list[str] = []
        for ch, level in row:
            if level == prev_level:
                run_chars.append(ch)
                continue
            # Flush previous run.
            _flush_run(text, run_chars, prev_level, gradient, n_colors)
            run_chars = [ch]
            prev_level = level
        _flush_run(text, run_chars, prev_level, gradient, n_colors)

    return text


def _flush_run(
    text: Text,
    chars: list[str],
    level: int,
    gradient: list[str],
    n_colors: int,
) -> None:
    """Append a run of same-level characters to *text*."""
    if not chars:
        return
    run_str = "".join(chars)
    chars.clear()
    if level <= 0:
        text.append(run_str)  # blank — no style
        return
    color_idx = min(level, n_colors) - 1
    text.append(run_str, style=Style(color=gradient[color_idx]))