"""Argument parser construction for the ``ecdat`` CLI.

:func:`build_parser` assembles the global options and delegates subcommand
registration to each module in :mod:`ecdat.cli.commands`.  Importing this
module must stay cheap: command modules defer heavy imports (Rich, the
scanner engine) to their ``run()`` functions.
"""

from __future__ import annotations

import argparse

from ecdat.cli.commands import scan as scan_command

# Command name -> command module.  Every module exposes ``register`` and
# ``run(args) -> int``; ``run`` is looked up at call time so tests can patch it.
COMMANDS: dict[str, object] = {
    scan_command.NAME: scan_command,
}


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
        description="Cryptographic Discovery & Analysis Tool",
    )

    parser.add_argument(
        "--version",
        action="store_true",
        help="Show the ECDAT version and exit",
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
