"""``ecdat tui`` — launch the animated full-screen terminal UI.

This module must not import :mod:`textual` at import time: the app is loaded
lazily inside :func:`run` (via :func:`ecdat.tui.run_tui`), so the plain CLI
stays framework-free.
"""

from __future__ import annotations

import argparse

NAME = "tui"

# Extra invocations that map onto this command (argparse reports the alias as
# ``args.command``, so the dispatcher normalises them through ALIASES).
ALIASES = ("ui",)


def register(subparsers: "argparse._SubParsersAction") -> None:
    """Attach the ``tui`` subcommand (alias ``ui``) to *subparsers*."""
    parser = subparsers.add_parser(
        "tui",
        aliases=["ui"],
        help="Launch the animated full-screen terminal UI",
        description=(
            "Open ECDAT's animated terminal UI. With TARGET, the scan starts "
            "as soon as the app is ready."
        ),
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Optional folder path or https:// Git URL to scan immediately",
    )
    parser.add_argument(
        "--no-anim",
        action="store_true",
        help="Disable animations for this session",
    )
    parser.add_argument(
        "--no-splash",
        action="store_true",
        help="Skip the decrypt-reveal splash screen",
    )


def run(args) -> int:
    """Launch the TUI; return its exit code."""
    from ecdat.tui import run_tui

    target = getattr(args, "target", None)
    return run_tui(
        target,
        auto_start=target is not None,
        no_anim=bool(getattr(args, "no_anim", False)),
        no_splash=bool(getattr(args, "no_splash", False)),
    )


__all__ = ["NAME", "register", "run"]
