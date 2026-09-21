"""Argument parser construction for the ``ecdat`` CLI.

:func:`build_parser` assembles the global options and delegates subcommand
registration to each module in :mod:`ecdat.cli.commands`.  Importing this
module must stay cheap: command modules defer heavy imports (Rich, the
scanner engine) to their ``run()`` functions.

Public API:
    - :data:`COMMANDS` — mapping of command name to its command module.
    - :func:`build_parser` — return the configured ArgumentParser.
"""

from __future__ import annotations

import argparse
import sys

from ecdat.cli.commands import about as about_command
from ecdat.cli.commands import demo as demo_command
from ecdat.cli.commands import doctor as doctor_command
from ecdat.cli.commands import explain as explain_command
from ecdat.cli.commands import help_cmd as help_command
from ecdat.cli.commands import history_cmd as history_command
from ecdat.cli.commands import mosca as mosca_command
from ecdat.cli.commands import report as report_command
from ecdat.cli.commands import rules as rules_command
from ecdat.cli.commands import scan as scan_command
from ecdat.cli.commands import tui_cmd as tui_command
from ecdat.cli.commands import version_cmd as version_command

# Command name -> command module.  Every module exposes ``register`` and
# ``run(args) -> int``; ``run`` is looked up at call time so tests can patch it.
COMMANDS: dict[str, object] = {
    scan_command.NAME: scan_command,
    demo_command.NAME: demo_command,
    tui_command.NAME: tui_command,
    history_command.NAME: history_command,
    report_command.NAME: report_command,
    rules_command.NAME: rules_command,
    explain_command.NAME: explain_command,
    mosca_command.NAME: mosca_command,
    help_command.NAME: help_command,
    doctor_command.NAME: doctor_command,
    about_command.NAME: about_command,
    version_command.NAME: version_command,
}

# Alias -> canonical command name.  argparse records the alias the user typed
# in ``args.command`` (e.g. ``ui``), so the dispatcher normalises through this.
ALIASES: dict[str, str] = {}
for _module in COMMANDS.values():
    for _alias in getattr(_module, "ALIASES", ()):  # pragma: no branch
        ALIASES[_alias] = _module.NAME


def resolve_command(name: str) -> object:
    """Return the command module for *name*, following aliases.

    Args:
        name: The command (or alias) the user typed.

    Returns:
        The command module, or ``None`` when *name* is unknown.
    """
    return COMMANDS.get(ALIASES.get(name, name))


class _VersionAction(argparse.Action):
    """Print the full version line to stdout and exit ``0``.

    Deliberately writes to stdout (argparse's built-in version action uses
    stderr) so ``ecdat --version`` and ``ecdat version`` emit identical,
    pipe-friendly payloads.  The version renderer is imported lazily so
    importing this module never pulls in the signature knowledge base.
    """

    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, nargs=0, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        from ecdat.cli.commands.version_cmd import render_version

        sys.stdout.write(render_version() + "\n")
        parser.exit(0)


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level ``ecdat`` argument parser.

    Returns:
        An :class:`argparse.ArgumentParser` with the global flags
        (``--version``, ``--no-color``, ``--debug``) and every registered
        subcommand attached.  The subcommand is optional — a bare ``ecdat``
        invocation prints the banner and example commands.
    """
    parser = argparse.ArgumentParser(
        prog="ecdat",
        description="Enterprise Cryptographic Discovery & Analysis Tool",
    )

    parser.add_argument(
        "--version",
        action=_VersionAction,
        help="Show version info (engine, signatures, Python, OS) and exit",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable coloured output",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print tracebacks for unexpected errors",
    )
    parser.set_defaults(version=False, no_color=False, debug=False)

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    for module in COMMANDS.values():
        module.register(subparsers)

    return parser
