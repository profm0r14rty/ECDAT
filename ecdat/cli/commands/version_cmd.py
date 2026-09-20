"""``ecdat version`` — version, engine, signature count, Python, and OS.

Also backs the global ``--version`` flag via
:func:`ecdat.cli.commands.version_cmd.render_version` in
:mod:`ecdat.cli.parser`.  Everything heavy (the signature knowledge base) is
imported lazily inside :func:`render_version`.
"""

from __future__ import annotations

import argparse
import sys

NAME = "version"


def register(subparsers: "argparse._SubParsersAction") -> None:
    """Attach the ``version`` subcommand to *subparsers*."""
    subparsers.add_parser(
        "version",
        help="Show version, engine, signature count, Python and OS",
        description=(
            "Print the ECDAT version line: distribution version, engine "
            "package, number of loaded signatures, Python version, and OS."
        ),
    )


def render_version() -> str:
    """Build the single-line version string (``ecdat <ver> \u00b7 ...``)."""
    import platform

    from ecdat import __version__
    from ecdat_core.signature_loader import get_all_signatures

    signature_count = len(get_all_signatures())
    os_name = platform.system() or "unknown"
    return (
        f"ecdat {__version__} \u00b7 engine ecdat_core \u00b7 "
        f"{signature_count} signatures \u00b7 Python {platform.python_version()} "
        f"\u00b7 {os_name}"
    )


def run(args) -> int:
    """Write the version line to stdout; return exit code 0."""
    sys.stdout.write(render_version() + "\n")
    return 0
