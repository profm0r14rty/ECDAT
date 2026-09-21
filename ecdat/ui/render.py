"""Rich renderers for the ECDAT app layer.

This module holds presentation logic that is independent of the scan
view-model, so it can be reused by the CLI, the TUI, and tests alike.

The Mosca timeline is deliberately split into two layers:

- :func:`mosca_timeline_segments` — a **pure** function returning plain
  ``(text, style_token)`` cells.  No Rich objects, no console, no colour
  lookup: it is trivially unit-testable and reusable by a Textual widget.
- :func:`mosca_timeline` — a thin Rich wrapper that maps style tokens to the
  :mod:`ecdat.ui.theme` palette and returns a printable
  :class:`rich.console.Group`.

All dynamic values here are numeric (never attacker-controlled text), so there
is no markup-escaping concern in this module.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from rich.console import Group
from rich.style import Style
from rich.text import Text

from ecdat.ui.theme import PALETTE

# A timeline row is a list of ``(text, style_token)`` segments.
Segment = Tuple[str, str]
Row = List[Segment]

# Prefix rendered on the first two rows, before the bars.  ``"NOW ├"`` is
# exactly 5 cells wide (``├`` is a single box-drawing cell).
_NOW_PREFIX = "NOW \u251c"
_PREFIX_WIDTH = len(_NOW_PREFIX)

# Row 4 label — the legend spelling out what each bar means.  Per the
# Phase 77 spec, X is data lifetime (shelf life) and Y is migration time.
_LABEL = "X data lifetime \u00b7 Y migration \u00b7 Z quantum arrival"

# Exposed-window fill character (medium shade), tokenised as "gap".
_GAP_CHAR = "\u2592"


def _cells(value: float, scale: float) -> int:
    """Return the number of cells for *value* at *scale*.

    Every non-zero value gets at least one cell (an invisible bar is worse than
    an approximate one); zero maps to zero.  A non-positive *scale* (only
    possible for degenerate widths) still yields one cell for a non-zero value.
    """
    if value <= 0:
        return 0
    if scale <= 0:
        return 1
    return max(1, int(round(value * scale)))


def _fit(segments: Row, width: int) -> Row:
    """Pad or truncate *segments* so the row is exactly *width* cells wide.

    Padding is emitted as a single ``("plain")`` segment.  If the content
    already exceeds *width*, later segments are truncated (dropping any
    remainder) so the exact-width invariant always holds.
    """
    budget = width
    out: Row = []
    for text, token in segments:
        if not text:
            continue
        if budget <= 0:
            break
        if len(text) <= budget:
            out.append((text, token))
            budget -= len(text)
        else:
            out.append((text[:budget], token))
            budget = 0
            break
    if budget > 0:
        out.append((" " * budget, "plain"))
    return out


def mosca_timeline_segments(x: float, y: float, z: float, width: int) -> List[Row]:
    """Build the raw cell rows for a Mosca-inequality timeline.

    The timeline visualises ``X + Y`` (the time we must stay safe) against
    ``Z`` (the quantum arrival horizon):

    - **row 1** — ``"NOW ├"`` followed by the X bar (token ``"x"``) and the Y
      bar (token ``"y"``), i.e. ``X + Y`` laid out on the same axis as Z.
    - **row 2** — ``"NOW ├"`` followed by the Z bar (token ``"z"``).
    - **row 3** — present **only** when ``X + Y > Z`` (a Mosca violation):
      spaces up to Z, then ``"▒"`` (token ``"gap"``) marking the exposed
      window from Z to ``X + Y``.
    - **row 4** — the legend label (token ``"label"``).

    Scaling uses ``scale = (width - 6) / (max(X + Y, Z) * 1.05)``, leaving a
    small headroom so the longest bar never touches the right edge.  Every row
    is returned with **exactly** *width* cells (padded with a ``"plain"``
    segment when short).

    Args:
        x: Data-lifetime component (years), the "X" bar.
        y: Migration-time component (years), the "Y" bar.
        z: Quantum threat horizon (years), the "Z" bar.
        width: Total number of terminal cells per row.

    Returns:
        A list of rows, each a list of ``(text, style_token)`` segments whose
        combined text length equals *width*.  Tokens used: ``x``, ``y``, ``z``,
        ``gap``, ``label``, ``plain``.
    """
    width = max(0, int(width))
    total = x + y
    max_value = max(total, z)

    # Scale in cells-per-year.  Guard against a zero/negative denominator.
    scale = ((width - 6) / (max_value * 1.05)) if max_value > 0 else 0.0

    x_cells = _cells(x, scale)
    y_cells = _cells(y, scale)
    z_cells = _cells(z, scale)
    sum_cells = x_cells + y_cells

    rows: List[Row] = []

    # Row 1 — X + Y against the same axis.
    rows.append(
        _fit(
            [
                (_NOW_PREFIX, "label"),
                ("#" * x_cells, "x"),
                ("#" * y_cells, "y"),
            ],
            width,
        )
    )

    # Row 2 — Z.
    rows.append(
        _fit(
            [
                (_NOW_PREFIX, "label"),
                ("#" * z_cells, "z"),
            ],
            width,
        )
    )

    # Row 3 — the exposed window, only when X + Y > Z.
    if total > z:
        gap_cells = sum_cells - z_cells
        if gap_cells < 1:
            # Rounding could collapse a genuine (but tiny) violation to zero
            # cells; keep the violation visible with a single-cell marker.
            gap_cells = 1
        rows.append(
            _fit(
                [
                    (" " * _PREFIX_WIDTH, "plain"),
                    (" " * z_cells, "plain"),
                    (_GAP_CHAR * gap_cells, "gap"),
                ],
                width,
            )
        )

    # Row 4 — legend.
    rows.append(_fit([(_LABEL, "label")], width))

    return rows


# ---------------------------------------------------------------------------
# Token → theme colour mapping
# ---------------------------------------------------------------------------

_TOKEN_STYLES: dict[str, Optional[Style]] = {
    "x": Style(color=PALETTE.accent),
    "y": Style(color=PALETTE.medium),
    "z": Style(color=PALETTE.critical),
    "gap": Style(color=PALETTE.critical, bold=True),
    "label": Style(color=PALETTE.muted),
    "plain": Style(),
}


def mosca_timeline(
    x: float,
    y: float,
    z: float,
    width: Optional[int] = None,
) -> Group:
    """Render the Mosca timeline as a printable Rich :class:`~rich.console.Group`.

    Thin wrapper over :func:`mosca_timeline_segments`: each style token is
    mapped to a :mod:`ecdat.ui.theme` colour (``x`` → accent, ``y`` → medium,
    ``z`` → critical, ``gap`` → critical) and every row becomes a
    :class:`rich.text.Text`.

    Args:
        x: Data-lifetime component (years).
        y: Migration-time component (years).
        z: Quantum threat horizon (years).
        width: Row width in cells; defaults to 64 when ``None``.

    Returns:
        A :class:`~rich.console.Group` of timeline rows, ready for
        ``console.print()``.
    """
    resolved_width = 64 if width is None else width
    rows = mosca_timeline_segments(x, y, z, resolved_width)

    lines: List[Text] = []
    for row in rows:
        line = Text()
        for text, token in row:
            line.append(text, style=_TOKEN_STYLES.get(token, Style()))
        lines.append(line)

    return Group(*lines)


__all__ = ["mosca_timeline", "mosca_timeline_segments"]
