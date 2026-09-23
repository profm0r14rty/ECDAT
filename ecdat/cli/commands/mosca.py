"""``ecdat mosca`` — Mosca's-inequality calculator with a visual timeline.

Given X (data lifetime), Y (migration time) and Z (quantum arrival horizon),
this computes the urgency ratio ``(X + Y) / Z``, classifies it with the engine's
own :func:`ecdat_core.risk_engine.classify_urgency` (the exact thresholds the
scanner uses — no duplicated constants), and draws the timeline from
:func:`ecdat.ui.render.mosca_timeline`.

Variable naming follows the Phase 77 spec: ``-x``/``--shelf-life`` is the data
lifetime, ``-y``/``--migration`` is the migration time, ``-z``/``--threat`` is
the quantum arrival horizon.

Exit codes:
    - 0 — computed successfully.
    - 2 — usage/validation error (missing/invalid arguments).
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from ecdat.ui.render import mosca_timeline
from ecdat.ui.theme import PALETTE, RISK_COLORS, RISK_LABELS, make_console
from ecdat_core.risk_engine import classify_urgency

NAME = "mosca"


def register(subparsers: "argparse._SubParsersAction") -> None:
    """Attach the ``mosca`` subcommand to *subparsers*."""
    parser = subparsers.add_parser(
        "mosca",
        help="Mosca's-inequality calculator with a visual timeline",
        description=(
            "Compute the Mosca urgency ratio (X + Y) / Z from a data "
            "lifetime (X), migration time (Y) and quantum horizon (Z) and "
            "draw the exposure timeline."
        ),
    )
    parser.add_argument(
        "-x",
        "--shelf-life",
        type=float,
        default=None,
        dest="x",
        help="X — data lifetime in years (data must stay secret)",
    )
    parser.add_argument(
        "-y",
        "--migration",
        type=float,
        default=None,
        dest="y",
        help="Y — migration time in years",
    )
    parser.add_argument(
        "-z",
        "--threat",
        type=float,
        default=None,
        dest="z",
        help="Z — quantum threat horizon in years",
    )


def _is_interactive() -> bool:
    """Return whether we may prompt the user for missing values.

    Interactive means both stdin and stdout are TTYs — prompting into a pipe or
    a redirected stream would either hang or corrupt the payload.
    """
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except (AttributeError, ValueError):
        return False


def _fmt(value: float) -> str:
    """Format a year value without a trailing ``.0`` for whole numbers."""
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _risk_chip(level: str) -> Text:
    """Return a coloured uppercase risk chip for *level*."""
    color = RISK_COLORS.get(level, PALETTE.text)
    label = RISK_LABELS.get(level, level.upper())
    return Text(label, style=f"bold {color}")


def _resolve(
    raw: Optional[float],
    *,
    label: str,
    flag: str,
    out,
) -> Optional[float]:
    """Resolve a possibly-missing value, prompting only when interactive.

    Args:
        raw: The parsed value, or ``None`` when the flag was omitted.
        label: Human-readable name used in the prompt ("data lifetime").
        flag: The CLI flag spelling used in the prompt (``-x/--shelf-life``).
        out: The console used for the interactive prompt.

    Returns:
        The resolved float value, or ``None`` when a value is required but the
        session is non-interactive (the caller then returns a usage error).
    """
    if raw is not None:
        return raw
    if not _is_interactive():
        return None
    entered = Prompt.ask(
        Text(f"{label} ({flag})", style=PALETTE.accent),
        console=out,
    )
    try:
        return float(entered)
    except (TypeError, ValueError):
        return None


def run(args: object) -> int:
    """Execute the ``mosca`` subcommand.

    Args:
        args: Parsed arguments with attributes ``x`` (data lifetime),
            ``y`` (migration time) and ``z`` (threat horizon), any of which may
            be ``None``.

    Returns:
        Exit code (0 on success, 2 on usage/validation error).
    """
    out = make_console()

    raw_x: Optional[float] = getattr(args, "x", None)
    raw_y: Optional[float] = getattr(args, "y", None)
    raw_z: Optional[float] = getattr(args, "z", None)

    x = _resolve(raw_x, label="Data lifetime", flag="-x/--shelf-life", out=out)
    if x is None:
        print(
            "Error: data lifetime (-x/--shelf-life) is required and must be a "
            "number.",
            file=sys.stderr,
        )
        return 2

    y = _resolve(raw_y, label="Migration time", flag="-y/--migration", out=out)
    if y is None:
        print(
            "Error: migration time (-y/--migration) is required and must be a "
            "number.",
            file=sys.stderr,
        )
        return 2

    z = _resolve(raw_z, label="Quantum arrival", flag="-z/--threat", out=out)
    if z is None:
        print(
            "Error: quantum arrival (-z/--threat) is required and must be a "
            "number.",
            file=sys.stderr,
        )
        return 2

    if x < 0 or y < 0:
        print(
            "Error: data lifetime (X) and migration time (Y) must be >= 0.",
            file=sys.stderr,
        )
        return 2
    if z <= 0:
        print("Error: quantum arrival (Z) must be > 0.", file=sys.stderr)
        return 2

    total = x + y
    urgency = total / z
    level = classify_urgency(urgency)
    violation = total > z

    # --- headline numbers + risk chip -------------------------------------
    line = Text()
    line.append(f"X + Y = {_fmt(total)} vs Z = {_fmt(z)}")
    line.append("    urgency ratio ")
    line.append(_fmt(round(urgency, 2)))
    line.append("    ")
    line.append(_risk_chip(level))

    # --- plain-English verdict -------------------------------------------
    if violation:
        verdict = Text(
            f"You would be exposed for {_fmt(total - z)} years.",
            style=f"bold {PALETTE.critical}",
        )
    else:
        verdict = Text(
            f"You have a {_fmt(z - total)}-year safety margin.",
            style=PALETTE.safe,
        )

    out.print(
        Panel(
            Text.assemble(
                line,
                "\n\n",
                verdict,
            ),
            title="ecdat mosca",
            title_align="left",
            border_style=PALETTE.border,
            padding=(1, 2),
        )
    )
    out.print(mosca_timeline(x, y, z))
    return 0
