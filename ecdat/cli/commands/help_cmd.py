"""``ecdat help`` — a friendly overview of every command.

The command table is built by introspecting the argument parser, so a newly
registered subcommand shows up here automatically.  ``ecdat help <command>``
renders that subcommand's own ``argparse`` help inside a panel (as plain
:class:`rich.text.Text`, never markup).
"""

from __future__ import annotations

import argparse

NAME = "help"

_QUICK_START = (
    "ecdat demo",
    "ecdat scan . --fail-on high",
    "ecdat scan https://github.com/acme/app --git-url",
    "ecdat help scan",
)

# Optional per-command examples; unknown/new commands fall back to "ecdat <name>".
_EXAMPLES: dict[str, str] = {
    "scan": "ecdat scan . --fail-on high",
    "demo": "ecdat demo",
    "help": "ecdat help scan",
    "doctor": "ecdat doctor",
    "about": "ecdat about",
    "version": "ecdat version",
}

_EXIT_CODES = (
    ("0", "success"),
    ("1", "findings at or above --fail-on"),
    ("2", "usage or validation error"),
    ("3", "scan, runtime, or unexpected error"),
    ("130", "interrupted (Ctrl-C)"),
)


def register(subparsers: "argparse._SubParsersAction") -> None:
    """Attach the ``help`` subcommand to *subparsers*."""
    parser = subparsers.add_parser(
        "help",
        help="List all commands, or show detailed help for one",
        description=(
            "List every ECDAT command with an example, or show the full "
            "argparse help for a single command: ecdat help <command>."
        ),
    )
    parser.add_argument(
        "topic",
        nargs="?",
        default=None,
        metavar="COMMAND",
        help="Command to show detailed help for",
    )


def run(args) -> int:
    """Print the command overview or one command's help; return the exit code."""
    from rich.panel import Panel
    from rich.style import Style
    from rich.text import Text

    from ecdat import __version__
    from ecdat.cli.parser import build_parser
    from ecdat.ui.banner import render_banner
    from ecdat.ui.console import make_console
    from ecdat.ui.theme import PALETTE

    no_color = True if getattr(args, "no_color", False) else None
    out_console = make_console(no_color=no_color)
    err_console = make_console(stderr=True, no_color=no_color)

    parser = build_parser()
    commands, choices = _registry(parser)
    topic = getattr(args, "topic", None)

    if topic is None:
        out_console.print(render_banner(version=__version__))
        out_console.print(Text())
        out_console.print(_commands_table(commands))
        out_console.print(Text())
        out_console.print(
            Text("Quick start", style=Style(color=PALETTE.accent, bold=True))
        )
        for line in _QUICK_START:
            out_console.print(Text(f"  {line}"))
        out_console.print(Text())
        out_console.print(_exit_codes_table())
        return 0

    if topic not in choices:
        valid = ", ".join(name for name, _ in commands)
        err_console.print(
            Text(
                f"Error: unknown command {topic!r}. Valid commands: {valid}",
                style=Style(color=PALETTE.critical, bold=True),
            )
        )
        return 2

    out_console.print(
        Panel(
            Text(choices[topic].format_help()),
            title=f"ecdat {topic}",
            title_align="left",
            border_style=PALETTE.border,
            padding=(1, 2),
        )
    )
    return 0


# ---------------------------------------------------------------------------
# Parser introspection
# ---------------------------------------------------------------------------


def _registry(
    parser: argparse.ArgumentParser,
) -> tuple[list[tuple[str, str]], dict[str, argparse.ArgumentParser]]:
    """Return ``[(name, summary), ...]`` and ``name -> subparser`` for *parser*.

    Reads argparse's subparser action so the help table never drifts from the
    real command set.
    """
    action = next(
        (a for a in parser._actions if isinstance(a, argparse._SubParsersAction)),
        None,
    )
    if action is None:  # pragma: no cover - build_parser always adds subparsers
        return [], {}

    rows: list[tuple[str, str]] = []
    for choice in getattr(action, "_choices_actions", []):
        rows.append((choice.dest, choice.help or ""))
    return rows, dict(action.choices)


# ---------------------------------------------------------------------------
# Renderers (Rich imported lazily by the callers above)
# ---------------------------------------------------------------------------


def _commands_table(commands: list[tuple[str, str]]):
    """Build the rounded command/example table."""
    from rich import box
    from rich.style import Style
    from rich.table import Table
    from rich.text import Text

    from ecdat.ui.theme import PALETTE

    table = Table(
        title="Commands",
        title_style=f"bold {PALETTE.accent}",
        title_justify="left",
        border_style=PALETTE.border,
        header_style=Style(color=PALETTE.muted, bold=True),
        box=box.ROUNDED,
        expand=False,
    )
    table.add_column("Command", no_wrap=True)
    table.add_column("Summary")
    table.add_column("Example", no_wrap=True)

    for name, summary in commands:
        example = _EXAMPLES.get(name, f"ecdat {name}")
        table.add_row(
            Text(f"ecdat {name}", style=Style(color=PALETTE.accent, bold=True)),
            Text(summary),
            Text(example),
        )
    return table


def _exit_codes_table():
    """Build the rounded exit-code reference table."""
    from rich import box
    from rich.style import Style
    from rich.table import Table
    from rich.text import Text

    from ecdat.ui.theme import PALETTE

    table = Table(
        title="Exit codes",
        title_style=f"bold {PALETTE.accent}",
        title_justify="left",
        border_style=PALETTE.border,
        header_style=Style(color=PALETTE.muted, bold=True),
        box=box.ROUNDED,
        expand=False,
    )
    table.add_column("Code", no_wrap=True)
    table.add_column("Meaning")

    for code, meaning in _EXIT_CODES:
        table.add_row(
            Text(code, style=Style(color=PALETTE.accent, bold=True)),
            Text(meaning),
        )
    return table
