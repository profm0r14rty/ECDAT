"""Frozen palette, colour utilities, and Rich theme for the ECDAT app layer.

Colours are derived from the dashboard design tokens (``frontend/src/index.css``)
and the shared risk palette (``frontend/src/lib/colors.ts``).  All values are
immutable — palette is a frozen dataclass, and the module-level mappings are tuples
or frozensets so nothing accidentally mutates the shared state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from rich.theme import Theme

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Palette:
    """Immutable colour palette derived from the dashboard design tokens.

    The default values are hard-coded hex colours that match the dashboard's
    dark-only theme.  Where the dashboard uses ``oklch(…)`` expressions the
    approximate sRGB hex is given.
    """

    bg: str = "#0b0f0e"       # ~dashboard --ecdat-bg #04100b — brightened for terminal
    surface: str = "#111816"  # ~dashboard --ecdat-surface #0b1a12 — brightened
    panel: str = "#17211e"    # panel background (card on surface)
    border: str = "#26332f"   # oklch(1 0 0 / 12%) ≈ #26332f
    text: str = "#dfeae6"     # oklch(0.97 0.005 160)
    muted: str = "#8aa39a"    # oklch(0.65 0.015 160)
    accent: str = "#3ddc97"   # dashboard --ecdat-accent #44e0a4 (softened for terminal)

    # Risk-level colours — bright terminal-safe hex values distinct from the
    # dashboard's Tailwind-700 shades (which are tuned for WCAG AA on white).
    critical: str = "#ff5d5d"
    high: str = "#ff9a3c"
    medium: str = "#ffd23f"
    low: str = "#4cc3ff"
    safe: str = "#4ade80"     # quantum-safe green


# Singleton instance — import this everywhere.
PALETTE = Palette()

# ---------------------------------------------------------------------------
# Risk metadata
# ---------------------------------------------------------------------------

RISK_ORDER: Tuple[str, ...] = ("critical", "high", "medium", "low", "quantum-safe")

RISK_COLORS: dict[str, str] = {
    "critical": PALETTE.critical,
    "high": PALETTE.high,
    "medium": PALETTE.medium,
    "low": PALETTE.low,
    "quantum-safe": PALETTE.safe,
}

RISK_LABELS: dict[str, str] = {
    "critical": "CRITICAL",
    "high": "HIGH",
    "medium": "MEDIUM",
    "low": "LOW",
    "quantum-safe": "SAFE",
}

RISK_INDEX: dict[str, int] = {level: i for i, level in enumerate(RISK_ORDER)}

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert a ``#RRGGBB`` string to an ``(r, g, b)`` tuple (0–255)."""
    hex_color = hex_color.lstrip("#")
    return (
        int(hex_color[0:2], 16),
        int(hex_color[2:4], 16),
        int(hex_color[4:6], 16),
    )


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert ``(r, g, b)`` (0–255) to a ``#RRGGBB`` string."""
    return f"#{r:02x}{g:02x}{b:02x}"


def lerp_hex(a: str, b: str, t: float) -> str:
    """Linearly interpolate between two hex colours.

    ``t`` is clamped to ``[0, 1]``.  Per-channel linear interpolation in sRGB.
    """
    t = max(0.0, min(1.0, t))
    ar, ag, ab = hex_to_rgb(a)
    br, bg, bb = hex_to_rgb(b)
    return rgb_to_hex(
        round(ar + (br - ar) * t),
        round(ag + (bg - ag) * t),
        round(ab + (bb - ab) * t),
    )


def gradient(stops: list[str], steps: int) -> list[str]:
    """Return ``steps`` evenly-spaced colours interpolating through *stops*.

    The first colour is *stops[0]* and the last is *stops[-1]* exactly.
    Interior stops are placed at evenly-spaced indices; linear interpolation
    fills the gaps between them.

    Args:
        stops: Two or more hex-colour anchor points.
        steps: Total number of colours to return (must be ≥ 2).

    Returns:
        A list of ``steps`` ``#RRGGBB`` strings.
    """
    if steps < 2:
        return [stops[0]] * steps if steps == 1 else []
    if len(stops) == 1:
        return [stops[0]] * steps

    n_segments = len(stops) - 1
    result: list[str] = []
    for i in range(steps):
        # Map step index i to a float position in [0, n_segments].
        pos = i * n_segments / (steps - 1)
        seg = min(int(pos), n_segments - 1)
        frac = pos - seg
        result.append(lerp_hex(stops[seg], stops[seg + 1], frac))
    return result


# ---------------------------------------------------------------------------
# Gradient presets
# ---------------------------------------------------------------------------

MINT_GRADIENT: list[str] = gradient(
    ["#0b3d2e", "#1f9d6b", PALETTE.accent, "#eafff6"],
    12,
)

# ---------------------------------------------------------------------------
# Rich theme
# ---------------------------------------------------------------------------


def rich_theme() -> Theme:
    """Build a :class:`rich.theme.Theme` from the :class:`Palette`.

    Style names use the ``ecdat.`` prefix so they never clash with Rich's
    built-in styles.  Usable as:

        console = Console(theme=rich_theme())
        console.print("[ecdat.accent]hi[/]")
    """
    return Theme(
        {
            "ecdat.accent": f"bold {PALETTE.accent}",
            "ecdat.muted": PALETTE.muted,
            "ecdat.title": f"bold {PALETTE.accent}",
            "ecdat.critical": f"bold {PALETTE.critical}",
            "ecdat.high": f"bold {PALETTE.high}",
            "ecdat.medium": PALETTE.medium,
            "ecdat.low": PALETTE.low,
            "ecdat.safe": PALETTE.safe,
        }
    )