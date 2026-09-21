"""ECDAT Textual TUI package.

This package must stay **import-light**: importing it (or :mod:`ecdat.cli`)
must never import Textual.  The real app is imported lazily inside
:func:`run_tui`, so ``ecdat about`` and the plain CLI stay framework-free.
"""

from __future__ import annotations

from typing import Optional

__all__ = ["run_tui"]


def run_tui(
    target: Optional[str] = None,
    *,
    auto_start: bool = False,
    no_anim: bool = False,
    no_splash: bool = False,
) -> int:
    """Launch the animated ECDAT TUI.

    Textual is imported here (not at module import time) so the rest of the
    CLI never pulls it in.

    Args:
        target: Optional scan target; when given with *auto_start* the scan
            begins as soon as Home mounts.
        auto_start: Start scanning *target* immediately on mount.
        no_anim: Disable all animation for this run.
        no_splash: Skip the splash screen for this run.

    Returns:
        A process exit code (``0`` on a normal exit, ``2`` when the terminal
        cannot host the TUI).
    """
    from ecdat.tui.app import run_tui as _run_tui

    return _run_tui(
        target,
        auto_start=auto_start,
        no_anim=no_anim,
        no_splash=no_splash,
    )
