"""ECDAT CLI — entry point and command dispatch.

:func:`main` is the single guard rail for the whole CLI: it converts known
user errors (:class:`~ecdat.services.scanner.ScanError`), interrupts, and
broken pipes into clean exit codes, and turns genuinely unexpected exceptions
into a crash-log entry instead of a bare traceback.

Importing this module stays cheap — Rich, the scanner engine, and the crash
logger are all imported lazily.  ``textual`` is never imported here (the TUI
is loaded by its own command, later).
"""

from __future__ import annotations

import os
import sys
from typing import Optional

from ecdat.cli.parser import COMMANDS, build_parser

__all__ = ["main"]


def main(argv: Optional[list] = None) -> int:
    """Run the ECDAT CLI and return a process exit code.

    Args:
        argv: Argument list; defaults to ``sys.argv[1:]``.

    Returns:
        ``0`` on success, ``1`` when ``--fail-on`` is tripped, ``2`` on
        usage/validation errors, ``3`` on unexpected errors, ``130`` on
        ``Ctrl-C``.
    """
    if argv is None:
        argv = list(sys.argv[1:])

    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse handles --help (0) and usage errors (2) itself.
        return _system_exit_code(exc)

    try:
        if getattr(args, "version", False):
            _print_version()
            return 0

        command = getattr(args, "command", None)
        if not command:
            return _run_bare(args)

        module = COMMANDS.get(command)
        if module is None:
            _print_error(args, f"Unknown command: {command}")
            return 2
        return module.run(args)
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        _silence_stdout()
        return 0
    except Exception as exc:  # noqa: BLE001 - top-level guard rail
        return _handle_exception(exc, argv, args)


# ---------------------------------------------------------------------------
# Exit-code / error handling
# ---------------------------------------------------------------------------


def _system_exit_code(exc: SystemExit) -> int:
    """Map an argparse :class:`SystemExit` to a plain integer exit code."""
    code = exc.code
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    return 2


def _handle_exception(exc: Exception, argv: list, args) -> int:
    """Route an exception to the right handler; return the exit code."""
    from ecdat.services.scanner import ScanError

    if isinstance(exc, ScanError):
        _print_scan_error(args, exc)
        return exc.exit_code
    return _handle_unexpected(exc, argv, args)


def _handle_unexpected(exc: Exception, argv: list, args) -> int:
    """Record an unexpected crash and report a friendly message; return 3."""
    from ecdat.services.crashlog import write_crash_log
    from rich.text import Text

    log_path = write_crash_log(exc, argv)
    details = str(log_path) if log_path is not None else "(crash log unavailable)"

    console = _console(stderr=True, args=args)
    console.print(
        Text(
            f"ECDAT hit an unexpected error. Details: {details}. "
            f"Re-run with --debug for the traceback and attach "
            f"`ecdat doctor` output to an issue.",
            style="bold red",
        )
    )

    if _is_debug(args):
        import traceback

        traceback.print_exception(type(exc), exc, exc.__traceback__)

    return 3


def _print_scan_error(args, exc) -> None:
    """Print a known :class:`ScanError` (plus optional hint) to stderr."""
    from rich.text import Text

    console = _console(stderr=True, args=args)
    console.print(Text(f"Error: {exc.user_message}", style="bold red"))
    if exc.hint:
        console.print(Text(f"Hint: {exc.hint}", style="dim"))


def _print_error(args, message: str) -> None:
    """Print a plain error line to stderr."""
    from rich.text import Text

    _console(stderr=True, args=args).print(Text(f"Error: {message}", style="bold red"))


def _print_version() -> None:
    """Write ``ecdat <version>`` to stdout."""
    from ecdat import __version__

    sys.stdout.write(f"ecdat {__version__}\n")


# ---------------------------------------------------------------------------
# Bare invocation
# ---------------------------------------------------------------------------


def _run_bare(args) -> int:
    """Print the banner and example commands (no subcommand given)."""
    from rich.text import Text

    from ecdat import __version__
    from ecdat.ui.banner import render_banner

    console = _console(args=args)
    console.print(render_banner(version=__version__))
    console.print(Text(""))
    console.print(Text("Try one of these:", style="bold"))
    for example in ("ecdat demo", "ecdat scan .", "ecdat about", "ecdat help"):
        console.print(Text(f"  {example}"))
    return 0


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------


def _is_debug(args) -> bool:
    """Return ``True`` when ``--debug`` or ``ECDAT_DEBUG=1`` is set."""
    if args is not None and getattr(args, "debug", False):
        return True
    return os.environ.get("ECDAT_DEBUG", "").strip() == "1"


def _console(*, stderr: bool = False, args=None):
    """Create a themed Rich console via the sanctioned factory."""
    from ecdat.ui.console import make_console

    no_color = None
    if args is not None and getattr(args, "no_color", False):
        no_color = True
    return make_console(stderr=stderr, no_color=no_color)


def _silence_stdout() -> None:
    """Redirect the real stdout fd to ``/dev/null`` after a broken pipe.

    Prevents Python's interpreter-shutdown flush from re-raising on a pipe
    that a downstream reader (e.g. ``head``) already closed.  Best-effort.
    """
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(devnull, sys.stdout.fileno())
        finally:
            os.close(devnull)
    except Exception:
        pass


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
