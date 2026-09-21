"""ECDAT CLI entrypoint.

Wired as the ``ecdat`` console script in ``pyproject.toml``.
"""

from __future__ import annotations

import sys

from ecdat.cli.parser import build_parser


def main(argv: list[str] | None = None) -> int:
    """Parse args, dispatch to the correct subcommand, return exit code.

    Args:
        argv: Argument list; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code (0 ok, 1 findings, 2 usage, 3 runtime error).
    """
    parser = build_parser()

    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        # argparse calls sys.exit on --help / invalid args.
        return int(e.code) if e.code is not None else 2

    command: str = args.command  # type: ignore[union-attr]

    if command == "scan":
        from ecdat.cli.commands.scan import run as scan_run
        return scan_run(args)

    elif command == "history":
        from ecdat.cli.commands.history_cmd import run as history_run
        return history_run(args)

    elif command == "report":
        from ecdat.cli.commands.report import run as report_run
        return report_run(args)

    else:
        print(f"Error: unknown command {command!r}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())