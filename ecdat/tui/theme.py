"""Textual themes for the ECDAT TUI.

Two themes are registered from the shared :data:`ecdat.ui.theme.PALETTE` so
the TUI, the Rich renderers and the web dashboard all draw from one palette.

Public API:
    - :data:`ECDAT_DARK` / :data:`ECDAT_LIGHT` — the theme objects.
    - :data:`THEME_NAMES` — their names, in cycle order.
    - :func:`register_themes` — register both on an app.
"""

from __future__ import annotations

from textual.theme import Theme

from ecdat.ui.theme import PALETTE

# Risk colours exposed to TCSS as $risk-critical, $risk-high, …
_RISK_VARIABLES = {
    "risk-critical": PALETTE.critical,
    "risk-high": PALETTE.high,
    "risk-medium": PALETTE.medium,
    "risk-low": PALETTE.low,
    "risk-safe": PALETTE.safe,
}

ECDAT_DARK = Theme(
    name="ecdat-dark",
    primary=PALETTE.accent,
    secondary=PALETTE.low,
    accent=PALETTE.accent,
    foreground=PALETTE.text,
    background=PALETTE.bg,
    surface=PALETTE.surface,
    panel=PALETTE.panel,
    success=PALETTE.safe,
    warning=PALETTE.medium,
    error=PALETTE.critical,
    dark=True,
    variables=dict(_RISK_VARIABLES),
)

ECDAT_LIGHT = Theme(
    name="ecdat-light",
    primary="#1f9d6b",
    secondary=PALETTE.low,
    accent="#1f9d6b",
    foreground="#10201a",
    background="#f4faf7",
    surface="#ffffff",
    panel="#e8f3ee",
    success="#178a4c",
    warning="#a86a00",
    error="#b3261e",
    dark=False,
    variables={
        "risk-critical": "#b3261e",
        "risk-high": "#a85a00",
        "risk-medium": "#8a6a00",
        "risk-low": "#0b63a8",
        "risk-safe": "#178a4c",
    },
)

THEME_NAMES = (ECDAT_DARK.name, ECDAT_LIGHT.name)


def register_themes(app) -> None:
    """Register both ECDAT themes on *app*."""
    app.register_theme(ECDAT_DARK)
    app.register_theme(ECDAT_LIGHT)


__all__ = [
    "ECDAT_DARK",
    "ECDAT_LIGHT",
    "THEME_NAMES",
    "register_themes",
]
