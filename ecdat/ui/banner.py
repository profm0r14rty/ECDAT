r"""Gradient ASCII banner with optional shimmer highlight.

The banner uses big Unicode box-drawing characters for modern terminals and
falls back to pure ASCII for legacy environments.  Each column is coloured
with a :data:`~ecdat.ui.theme.MINT_GRADIENT` gradient.
"""

from __future__ import annotations

from typing import Optional

from rich.console import Group, RenderableType
from rich.style import Style
from rich.text import Text

from ecdat.ui.theme import MINT_GRADIENT, PALETTE

# ---------------------------------------------------------------------------
# Banner ASCII art — raw strings for backslash safety
# ---------------------------------------------------------------------------

BANNER_LINES = (
    r"███████╗ ██████╗██████╗  █████╗ ████████╗",
    r"██╔════╝██╔════╝██╔══██╗██╔══██╗╚══██╔══╝",
    r"█████╗  ██║     ██║  ██║███████║   ██║   ",
    r"██╔══╝  ██║     ██║  ██║██╔══██║   ██║   ",
    r"███████╗╚██████╗██████╔╝██║  ██║   ██║   ",
    r"╚══════╝ ╚═════╝╚═════╝ ╚═╝  ╚═╝   ╚═╝   ",
)

BANNER_ASCII_LINES = (
    r" _____   ____  ____      _     _____ ",
    r"| ____| / ___||  _ \    / \   |_   _|",
    r"|  _|  | |    | | | |  / _ \    | |  ",
    r"| |___ | |___ | |_| | / ___ \   | |  ",
    r"|_____| \____||____/ /_/   \_\  |_|  ",
)

TAGLINE = "Enterprise Cryptographic Discovery & Analysis Tool"
SUBLINE = "post-quantum readiness \xb7 CBOM \xb7 Mosca"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def banner_text(
    *,
    unicode: bool = True,
    shimmer: Optional[float] = None,
) -> Text:
    """Return the ECDAT banner as a gradient-coloured :class:`~rich.text.Text`.

    Each column is coloured from :data:`~ecdat.ui.theme.MINT_GRADIENT`, cycling
    left-to-right across the full width of the banner text.

    When *shimmer* is a float in ``[0, 1]``, the gradient is locally brightened
    in a window of ±3 columns around ``shimmer * width`` — this produces a
    "scanning highlight" effect when animated across frames.

    Args:
        unicode: Use the full box-drawing banner (``True``) or pure ASCII
                 fallback (``False``).
        shimmer: Optional highlight position ``0..1``; ``None`` disables.

    Returns:
        A single :class:`~rich.text.Text` with styled characters.
    """
    lines = BANNER_LINES if unicode else BANNER_ASCII_LINES
    gradient = MINT_GRADIENT
    n_colors = len(gradient)

    # Determine max width for per-column gradient mapping.
    max_width = max(len(line) for line in lines) if lines else 0

    shimmer_col = -1
    if shimmer is not None:
        shimmer_col = int(round(max(0.0, min(1.0, shimmer)) * (max_width - 1)))
        # Clamp shimmer window to valid column range.
        shimmer_col = max(0, min(max_width - 1, shimmer_col))

    text = Text()
    for li, line in enumerate(lines):
        if li > 0:
            text.append("\n")
        for ci, ch in enumerate(line):
            # Base gradient index from column position.
            if max_width > 1:
                base_idx = ci * (n_colors - 1) // (max_width - 1)
            else:
                base_idx = 0

            # Shimmer brightens ±3 columns around shimmer_col.
            idx = base_idx
            if shimmer is not None and abs(ci - shimmer_col) <= 3:
                boost = max(0, 3 - abs(ci - shimmer_col))
                idx = min(n_colors - 1, base_idx + boost)

            color = gradient[idx]
            text.append(ch, style=Style(color=color, bold=False))

    return text


def render_banner(
    version: Optional[str] = None,
    *,
    unicode: bool = True,
) -> Group:
    """Return the full banner as a :class:`~rich.console.Group`.

    Layout (centred)::

        [gradient banner art]
        TAGLINE
        SUBLINE
        version (e.g. "v0.2.0")

    Args:
        version: Optional version string to display below the subline.
        unicode: Use box-drawing banner (``True``) or ASCII (``False``).

    Returns:
        A :class:`~rich.console.Group` ready for ``console.print()``.
    """
    elements: list[RenderableType] = []

    # Banner art.
    elements.append(banner_text(unicode=unicode))

    # TAGLINE — centred, accent colour.
    tagline = Text(TAGLINE, style=Style(color=PALETTE.accent, bold=True))
    tagline.justify = "center"
    elements.append(tagline)

    # SUBLINE — centred, muted.
    subline = Text(SUBLINE, style=Style(color=PALETTE.muted))
    subline.justify = "center"
    elements.append(subline)

    # Version — centred, dimmed.
    if version:
        ver = Text(f"v{version}", style=Style(color=PALETTE.muted, dim=True))
        ver.justify = "center"
        elements.append(ver)

    return Group(*elements)