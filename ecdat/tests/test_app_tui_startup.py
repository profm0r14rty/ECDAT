"""Startup regression tests for the TUI (Task C13).

The real, unmodified ``EcdatApp`` must mount through ``run_test()`` — and
keep working while the user cycles themes with ``t`` — no matter which theme
is saved/active.  Previously a saved Textual built-in theme (``textual-dark``
/ ``textual-light``) crashed the app at startup with
``UnresolvedVariableError`` because the built-ins define no ``$risk-*``
variables and ``get_css_variables`` merges theme variables over an empty
default set.  These tests pin the ``get_theme_variable_defaults`` override
that makes the five ``$risk-*`` variables resolve under every theme.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ecdat.services.settings import load_settings, save_settings
from ecdat.tui.app import EcdatApp
from ecdat.tui.theme import risk_variable_defaults

# The five $risk-* variables referenced by ecdat.tcss.
RISK_VARIABLES = (
    "risk-critical",
    "risk-high",
    "risk-medium",
    "risk-low",
    "risk-safe",
)


def _mount(app: EcdatApp):
    """Mount *app* under run_test and fail on any raised/unhandled exception."""
    return app.run_test(size=(120, 40))


# ---- unit: the defaults mapping --------------------------------------------


def test_risk_variable_defaults_cover_all_five():
    """The defaults helper must provide every variable ecdat.tcss references."""
    for name in RISK_VARIABLES:
        assert name in risk_variable_defaults()
    assert len(risk_variable_defaults()) == len(RISK_VARIABLES)


def test_app_theme_defaults_merge_super():
    """EcdatApp supplies the risk variables on top of Textual's own defaults."""
    app = EcdatApp(show_splash=False)
    defaults = app.get_theme_variable_defaults()
    # Textual's base defaults exist too (empty today, but don't assume).
    assert isinstance(defaults, dict)
    for name in RISK_VARIABLES:
        assert name in defaults


# ---- plain App smoke tests (real EcdatApp, real ecdat.tcss) ----------------


@pytest.mark.asyncio
async def test_plain_ecdat_app_mounts_ok():
    """The real, unmodified EcdatApp mounts without a stylesheet error."""
    app = EcdatApp(show_splash=False)
    async with _mount(app) as pilot:
        await pilot.pause()
        assert app._exception is None
        assert app.screen is not None


@pytest.mark.asyncio
async def test_all_risk_variables_resolve_in_stylesheet_variables():
    """After mounting, every $risk-* name actually resolves in the stylesheet."""
    app = EcdatApp(show_splash=False)
    async with _mount(app) as pilot:
        await pilot.pause()
        css_variables = app.get_css_variables()
        for name in RISK_VARIABLES:
            assert name in css_variables, f"{name} missing from css variables"


# ---- saved built-in theme (the original crash) -----------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("saved_theme", ["textual-dark", "textual-light"])
async def test_saved_builtin_theme_mounts(saved_theme):
    """A saved Textual built-in theme must not break startup.

    The original bug: when settings saved a built-in theme, the reactive
    ``self.theme`` set in __init__ was a no-op (the App default is already
    ``textual-dark``), so ``_watch_theme`` never fired and the stylesheet
    kept its initial variable set — which lacks ``$risk-*`` — while
    ``textual-light`` re-parsed with no risk variables either.  Both must
    mount cleanly now.
    """
    settings = load_settings()
    settings.theme = saved_theme
    save_settings(settings)

    app = EcdatApp(show_splash=False)
    async with _mount(app) as pilot:
        await pilot.pause()
        assert app._exception is None
        assert app.theme == saved_theme
        css_variables = app.get_css_variables()
        for name in RISK_VARIABLES:
            assert name in css_variables, f"{name} unresolved under {saved_theme}"


# ---- theme cycling through every theme -------------------------------------


@pytest.mark.asyncio
async def test_cycle_all_themes_never_raises_stylesheet_error():
    """Pressing ``t`` through every registered theme stays error-free."""
    app = EcdatApp(show_splash=False)
    # Every theme registered on the app: Textual's built-ins plus the ECDAT
    # pair.  The built-ins define no $risk-* variables, which is the whole
    # point of this test.
    all_themes = list(app.available_themes)
    assert all_themes, "expected at least the built-in themes"
    async with _mount(app) as pilot:
        await pilot.pause()
        app.set_focus(None)
        seen: list[str] = []
        for _ in all_themes:
            await pilot.press("t")
            await pilot.pause()
            assert app._exception is None, f"error after cycling to {app.theme}"
            css_variables = app.get_css_variables()
            for name in RISK_VARIABLES:
                assert name in css_variables, (
                    f"{name} unresolved under {app.theme}"
                )
            seen.append(app.theme)
        # Every registered theme was visited (cycling wraps around).
        assert set(seen) == set(all_themes)


# ---- stylesheet references stay covered ------------------------------------


def test_tcss_risk_references_match_defaults():
    """Every $risk-* reference in ecdat.tcss is covered by the defaults."""
    tcss_path = Path(__file__).resolve().parents[1] / "tui" / "ecdat.tcss"
    tcss = tcss_path.read_text(encoding="utf-8")
    referenced = sorted(re.findall(r"\$risk-[A-Za-z0-9_-]+", tcss))
    assert referenced, "expected $risk-* references in ecdat.tcss"
    # Every referenced variable name (without the leading $) has a default.
    for name in referenced:
        assert name[1:] in risk_variable_defaults(), f"{name} has no default"