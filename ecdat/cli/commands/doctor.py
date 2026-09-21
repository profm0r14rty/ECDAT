"""``ecdat doctor`` — environment self-check.

Runs a small set of independent checks and prints one row per check with a
status glyph, a short value, and a one-line fix when something needs
attention.  The output is plain and copy-pasteable into a GitHub issue.
Exits ``1`` only when at least one check genuinely fails (``\u2717``);
warnings (``!``) never fail the command.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

NAME = "doctor"

_OK = "\u2713"  # ✓
_WARN = "!"  # !
_FAIL = "\u2717"  # ✗

# Minimum interpreter the app layer supports (see AGENTS.md: 3.10-compatible code).
_MIN_PYTHON = (3, 10)

_ENV_NAMES = ("ECDAT_HOME", "ECDAT_ANIM", "NO_COLOR")


def register(subparsers: "argparse._SubParsersAction") -> None:
    """Attach the ``doctor`` subcommand to *subparsers*."""
    subparsers.add_parser(
        "doctor",
        help="Check your environment for common problems",
        description=(
            "Check Python, platform, install location, git, terminal, "
            "signatures, ECDAT_HOME, and environment overrides.  Every row "
            "carries a one-line fix.  Exits 1 only when a check fails."
        ),
    )


@dataclass(frozen=True)
class Check:
    """A single doctor check result.

    Attributes:
        status: ``"ok"``, ``"warn"``, or ``"fail"``.
        label: Short check name (e.g. ``"Python"``).
        detail: Human-readable value for the check.
        fix: One-line remediation hint (empty when no fix is needed).
    """

    status: str
    label: str
    detail: str
    fix: str = ""


def run(args) -> int:
    """Run all checks, print the report, and return the exit code."""
    from rich.style import Style
    from rich.table import Table
    from rich.text import Text

    from ecdat.ui.console import make_console
    from ecdat.ui.theme import PALETTE

    no_color = True if getattr(args, "no_color", False) else None
    console = make_console(no_color=no_color)

    checks = _run_checks(console)

    table = Table(box=None, show_header=False, padding=(0, 2), expand=False)
    table.add_column(no_wrap=True)
    table.add_column(no_wrap=True)
    table.add_column(overflow="fold")

    for check in checks:
        table.add_row(
            _status_text(check.status),
            Text(check.label),
            _detail_text(check),
        )

    console.print(
        Text(
            "ECDAT doctor \u2014 environment report",
            style=Style(color=PALETTE.accent, bold=True),
        )
    )
    console.print(table)

    failed = [c for c in checks if c.status == "fail"]
    warned = [c for c in checks if c.status == "warn"]
    if failed:
        console.print(
            Text(
                f"{len(failed)} check(s) failed \u2014 see fixes above.",
                style=Style(color=PALETTE.critical, bold=True),
            )
        )
        return 1
    if warned:
        console.print(
            Text(
                "No blocking problems found.",
                style=Style(color=PALETTE.safe),
            )
        )
        return 0
    console.print(Text("All checks passed.", style=Style(color=PALETTE.safe)))
    return 0


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _run_checks(console) -> list[Check]:
    """Collect every environment check, ordered for readability."""
    return [
        _check_python(),
        _check_platform(),
        _check_install_location(),
        _check_git(),
        _check_terminal(console),
        _check_signatures(),
        _check_home_writable(),
        _check_env_overrides(),
    ]


def _check_python() -> Check:
    version = platform.python_version()
    impl = platform.python_implementation()
    if sys.version_info >= _MIN_PYTHON:
        return Check("ok", "Python", f"{version} ({impl})")
    requirement = ".".join(str(part) for part in _MIN_PYTHON)
    return Check(
        "fail",
        "Python",
        f"{version} ({impl}) \u2014 too old",
        f"Install Python {requirement} or newer.",
    )


def _check_platform() -> Check:
    system = platform.system() or "unknown"
    release = platform.release() or "?"
    machine = platform.machine() or "?"
    return Check("ok", "Platform", f"{system} {release} ({machine})")


def _check_install_location() -> Check:
    import ecdat

    location = Path(ecdat.__file__).resolve().parent
    return Check("ok", "Install", str(location))


def _check_git() -> Check:
    git_path = shutil.which("git")
    if git_path is None:
        return Check(
            "warn",
            "git",
            "not found on PATH",
            "Install git to enable repository URL scans.",
        )
    try:
        proc = subprocess.run(
            [git_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = (proc.stdout or proc.stderr).strip()
        version = output.splitlines()[0] if output else "present"
        if proc.returncode != 0:
            return Check(
                "warn",
                "git",
                f"{git_path} (version check exited {proc.returncode})",
                "Verify git runs: git --version",
            )
        return Check("ok", "git", f"{version} ({git_path})")
    except (OSError, subprocess.SubprocessError) as exc:
        return Check(
            "warn",
            "git",
            f"{git_path} (version check failed: {exc})",
            "Verify git runs: git --version",
        )


def _check_terminal(console) -> Check:
    try:
        size = console.size
        dimensions = f"{size.width}x{size.height}"
    except Exception:  # noqa: BLE001 - size is best-effort diagnostics
        dimensions = "?"
    encoding = sys.stdout.encoding or "?"
    color_system = console.color_system or "none"
    term = os.environ.get("TERM") or "(unset)"
    detail = (
        f"interactive={sys.stdout.isatty()}, size={dimensions}, "
        f"color={color_system}, encoding={encoding}, TERM={term}"
    )
    return Check("ok", "Terminal", detail)


def _check_signatures() -> Check:
    try:
        from ecdat_core.signature_loader import get_all_signatures

        count = len(get_all_signatures())
    except Exception as exc:  # noqa: BLE001 - report any load failure verbatim
        return Check(
            "fail",
            "signatures",
            f"failed to load: {exc}",
            "Reinstall ECDAT: pip install --force-reinstall ecdat",
        )
    return Check("ok", "signatures", f"{count} entries loaded")


def _check_home_writable() -> Check:
    from ecdat.services.paths import home_dir

    home = home_dir()
    try:
        home.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(home), prefix=".ecdat-write-test-")
        os.close(fd)
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
    except OSError as exc:
        return Check(
            "fail",
            "ECDAT_HOME",
            f"{home} is not writable: {exc}",
            "Set ECDAT_HOME to a writable directory.",
        )
    return Check("ok", "ECDAT_HOME", f"{home} (writable)")


def _check_env_overrides() -> Check:
    parts = []
    for name in _ENV_NAMES:
        value = os.environ.get(name)
        parts.append(f"{name}={value}" if value else f"{name} (unset)")
    return Check("ok", "env", ", ".join(parts))


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _status_text(status: str):
    """Return the coloured status glyph for *status*."""
    from rich.style import Style
    from rich.text import Text

    from ecdat.ui.theme import PALETTE

    if status == "fail":
        return Text(_FAIL, style=Style(color=PALETTE.critical, bold=True))
    if status == "warn":
        return Text(_WARN, style=Style(color=PALETTE.medium, bold=True))
    return Text(_OK, style=Style(color=PALETTE.safe, bold=True))


def _detail_text(check: Check):
    """Return the detail string plus an optional dimmed fix hint."""
    from rich.style import Style
    from rich.text import Text

    from ecdat.ui.theme import PALETTE

    text = Text(check.detail)
    if check.fix:
        text.append("  \u2192  ")
        text.append(
            check.fix,
            style=Style(color=PALETTE.muted, italic=True),
        )
    return text
