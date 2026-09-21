"""``ecdat about`` — credits, project links, and the animated globe.

The globe is decorative, so it is strictly opt-in: it only animates when the
output is an interactive terminal, motion is enabled
(:func:`ecdat.ui.motion.animations_enabled`), ``--no-anim`` is absent, and
``--spin`` is positive.  When any of those is false, exactly one static frame
is printed — no cursor movement, no escape codes.
"""

from __future__ import annotations

import argparse
import time

NAME = "about"

_DESCRIPTION = (
    "ECDAT discovers cryptographic artefacts in source code and dependency "
    "manifests, scores their post-quantum risk with Mosca's inequality, and "
    "exports a CycloneDX 1.6 Cryptography Bill of Materials."
)
_LICENSE_LINE = "MIT \u00b7 https://github.com/profm0r14rty/ecdat"
_BUILT_WITH = "Built with Rich"

_FPS = 14.0
_GLOBE_MAX_WIDTH = 56
_GLOBE_MAX_HEIGHT = 22


def register(subparsers: "argparse._SubParsersAction") -> None:
    """Attach the ``about`` subcommand to *subparsers*."""
    parser = subparsers.add_parser(
        "about",
        help="About ECDAT \u2014 credits and a spinning globe",
        description=(
            "Show the ECDAT banner, a short description, and (on an "
            "interactive terminal) an animated 3D globe."
        ),
    )
    parser.add_argument(
        "--spin",
        type=float,
        default=3.0,
        metavar="SECONDS",
        help="Seconds to animate the globe (default: 3; 0 disables)",
    )
    parser.add_argument(
        "--no-anim",
        action="store_true",
        help="Never animate; print a single static frame",
    )


def run(args) -> int:
    """Print credits and optionally animate the globe; return 0."""
    from rich.style import Style
    from rich.text import Text

    from ecdat import __version__
    from ecdat.ui.banner import render_banner
    from ecdat.ui.console import make_console
    from ecdat.ui.motion import animations_enabled
    from ecdat.ui.theme import PALETTE

    no_color = True if getattr(args, "no_color", False) else None
    console = make_console(no_color=no_color)

    console.print(render_banner(version=__version__))
    console.print(Text(_DESCRIPTION))
    console.print(Text(_LICENSE_LINE, style=Style(color=PALETTE.muted)))
    console.print(Text(_BUILT_WITH, style=Style(color=PALETTE.muted)))
    console.print(Text())

    width, height = _globe_size(console)
    spin = max(0.0, float(getattr(args, "spin", 0.0)))
    animate = (
        not getattr(args, "no_anim", False)
        and spin > 0.0
        and console.is_terminal
        and animations_enabled()
    )

    if animate:
        _animate(console, width, height, spin)
    else:
        console.print(_frame_text(0.0, width, height))
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _globe_size(console) -> tuple[int, int]:
    """Return the globe frame size: terminal size capped at 56x22."""
    size = console.size
    return (
        max(1, min(size.width, _GLOBE_MAX_WIDTH)),
        max(1, min(size.height, _GLOBE_MAX_HEIGHT)),
    )


def _frame_text(elapsed: float, width: int, height: int):
    """Render one globe frame as gradient-coloured Rich Text."""
    from ecdat.ui.art3d import render_globe
    from ecdat.ui.art_text import frame_to_text

    return frame_to_text(render_globe(elapsed, width, height))


def _animate(console, width: int, height: int, seconds: float) -> None:
    """Animate the globe for *seconds* using real elapsed wall-clock time.

    Uses :class:`rich.live.Live` with ``transient=False`` so the final frame
    stays on screen.  ``Ctrl-C`` propagates out (the Live context restores the
    terminal, and the CLI maps it to exit code 130).
    """
    from rich.live import Live

    interval = 1.0 / _FPS
    start = time.monotonic()

    with Live(console=console, refresh_per_second=int(_FPS), transient=False) as live:
        elapsed = 0.0
        while elapsed < seconds:
            elapsed = time.monotonic() - start
            live.update(_frame_text(elapsed, width, height))
            time.sleep(min(interval, max(0.0, seconds - elapsed)))
        live.update(_frame_text(seconds, width, height))
