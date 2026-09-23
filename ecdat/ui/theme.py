"""Frozen palette, risk metadata, colour utilities, and the Rich theme.

Colours are derived from the dashboard design tokens
(``frontend/src/index.css``) and the shared risk palette
(``frontend/src/lib/colors.ts``).  All values are immutable — the palette is a
frozen dataclass and the module-level mappings are tuples/dicts that nothing
mutates.

This module is the single source of colour truth for the app layer: renderers
map their style tokens to these colours and never hardcode hex values.

Public API:
    - :data:`PALETTE` / :class:`Palette` — the frozen colour palette.
    - :data:`RISK_ORDER`, :data:`RISK_COLORS`, :data:`RISK_LABELS` — risk
      level metadata.
    - :func:`strip_control_chars` — neutralise terminal control/escape bytes in
      attacker-controlled strings (the untrusted-content boundary).
    - :func:`hex_to_rgb`, :func:`rgb_to_hex`, :func:`lerp_hex`,
      :func:`gradient` — colour maths.
    - :func:`rich_theme` — build the Rich :class:`~rich.theme.Theme`.
    - :func:`make_console` / :func:`_ensure_utf8_streams` — thin re-exports of
      the canonical console factory in :mod:`ecdat.ui.console` (kept here for
      the commands that historically imported them from this module).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from rich.console import Console
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
# Untrusted-content sanitisation
# ---------------------------------------------------------------------------

# Control characters to drop: every C0 code point (0x00–0x1F) and every C1
# code point (0x80–0x9F), except TAB (0x09) and LINE FEED (0x0A) which are
# legitimate whitespace.  Carriage return (0x0D) is a C0 control and is
# therefore dropped.  Removing ESC (0x1B) neutralises the entire ANSI/CSI/OSC/
# DCS escape family in one go — every escape sequence starts with ESC, so no
# regex matching on sequence shapes is required.
_CONTROL_CHARS = frozenset(
    chr(cp)
    for cp in list(range(0x00, 0x20)) + list(range(0x80, 0xA0))
    if cp not in (0x09, 0x0A)
)


def strip_control_chars(s: str) -> str:
    """Remove terminal control characters from an attacker-controlled string.

    This is the **untrusted-content boundary** for the presentation layer:
    file paths, matched snippets, algorithm/library names, repo names and URLs
    from scanned repositories are attacker-controlled and must never carry raw
    control bytes into a terminal, an HTML document, or a Markdown file.

    Removed: every C0 control character (``0x00``–``0x1F``) and every C1
    control character (``0x80``–``0x9F``), except TAB (``\\t``) and LINE FEED
    (``\\n``), which are legitimate whitespace.  Carriage return (``\\r``) is a
    C0 control and is dropped entirely.

    Because ESC (``0x1B``) is removed, the whole ANSI escape family — CSI
    (``ESC [``), OSC (``ESC ]``, DCS (``ESC P``) — and the bare BEL (``0x07``)
    used by OSC-8 hyperlinks are all neutralised; no regex matching on escape
    sequences is needed.

    Printable Unicode (accented letters, box-drawing characters, emoji, etc.)
    is left untouched.

    Args:
        s: The string to sanitise.

    Returns:
        The sanitised string.  Returns the input unchanged when it contains no
        control characters.
    """
    if not s or not any(ch in _CONTROL_CHARS for ch in s):
        return s
    return "".join(ch for ch in s if ch not in _CONTROL_CHARS)


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
    built-in styles.  Usable as::

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


# ---------------------------------------------------------------------------
# Console factory re-exports
#
# The canonical implementation lives in :mod:`ecdat.ui.console` (it resolves
# NO_COLOR / FORCE_COLOR and the colour system).  These wrappers keep the
# historical ``ecdat.ui.theme.make_console`` import path working without
# duplicating the logic; the import is deferred so theme.py stays importable
# on its own (console.py imports :func:`rich_theme` from here).
# ---------------------------------------------------------------------------


def _ensure_utf8_streams() -> None:
    """Reconfigure stdout/stderr to UTF-8 when possible (best-effort)."""
    from ecdat.ui.console import _ensure_utf8_streams as _impl

    _impl()


def make_console(
    *,
    stderr: bool = False,
    no_color: Optional[bool] = None,
    width: Optional[int] = None,
) -> Console:
    """Create a themed Rich :class:`~rich.console.Console`.

    Thin re-export of :func:`ecdat.ui.console.make_console`.
    """
    from ecdat.ui.console import make_console as _impl

    return _impl(stderr=stderr, no_color=no_color, width=width)


__all__ = [
    "PALETTE",
    "Palette",
    "RISK_ORDER",
    "RISK_COLORS",
    "RISK_LABELS",
    "RISK_INDEX",
    "MINT_GRADIENT",
    "strip_control_chars",
    "hex_to_rgb",
    "rgb_to_hex",
    "lerp_hex",
    "gradient",
    "rich_theme",
    "make_console",
]
