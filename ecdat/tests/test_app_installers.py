"""Static checks for the one-command installers in ``scripts/``.

These tests never execute the installers against the network. They verify the
properties the installers must hold no matter which branch they run on:

* ``scripts/install.sh`` parses as POSIX ``sh`` and is shellcheck-clean when
  shellcheck is available.
* Both scripts expose the documented ``ECDAT_SPEC`` / ``ECDAT_NO_UV`` knobs,
  avoid privileged or destructive operations, and only ever fetch from
  astral.sh (the uv installer).
* ``scripts/install.ps1`` parses with the PowerShell language parser when
  ``pwsh`` is installed.

Environment-dependent checks skip (never fail) when the tool they need is
missing — ``sh``, ``shellcheck`` and ``pwsh`` are not present on every runner.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SH = REPO_ROOT / "scripts" / "install.sh"
PS1 = REPO_ROOT / "scripts" / "install.ps1"

ASTRAL_HOST = "astral.sh"
_URL_RE = re.compile(r"https?://[^\s\"'`)]+")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---- install.sh ----------------------------------------------------------


def test_install_sh_exists_and_is_ascii() -> None:
    """The POSIX installer exists and carries no non-ASCII bytes.

    Non-ASCII would be re-read as cp1252 by some Windows tooling; keeping the
    script ASCII avoids that class of encoding surprise.
    """
    assert SH.is_file(), f"{SH} is missing"
    raw = SH.read_bytes()
    assert all(b < 128 for b in raw), "scripts/install.sh contains non-ASCII bytes"


def test_install_sh_parses_with_sh() -> None:
    """``sh -n`` must accept the script (syntax-only check)."""
    sh = shutil.which("sh")
    if sh is None:
        pytest.skip("sh is not available")
    result = subprocess.run(
        [sh, "-n", SH.name],
        cwd=SH.parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, f"sh -n failed:\n{result.stderr}"


def test_install_sh_passes_shellcheck() -> None:
    """Shellcheck must report nothing, when it is installed."""
    shellcheck = shutil.which("shellcheck")
    if shellcheck is None:
        pytest.skip("shellcheck is not installed")
    result = subprocess.run(
        [shellcheck, SH.name],
        cwd=SH.parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, f"shellcheck failed:\n{result.stdout}{result.stderr}"


def test_install_sh_has_documented_variables() -> None:
    """Both installers honour ECDAT_SPEC and ECDAT_NO_UV."""
    text = _read(SH)
    assert "ECDAT_SPEC" in text
    assert "ECDAT_NO_UV" in text


@pytest.mark.parametrize("script", [SH, PS1], ids=["sh", "ps1"])
def test_installers_avoid_privilege_and_destruction(script: Path) -> None:
    """No ``sudo``, no ``eval``, no ``rm -rf`` in either installer."""
    text = _read(script)
    assert "sudo" not in text, f"{script.name} must not invoke sudo"
    assert "eval " not in text, f"{script.name} must not use eval"
    assert "rm -rf" not in text, f"{script.name} must not remove trees recursively"


@pytest.mark.parametrize("script", [SH, PS1], ids=["sh", "ps1"])
def test_installers_only_fetch_from_astral(script: Path) -> None:
    """Every remote host referenced is astral.sh (uv's official installer)."""
    urls = _URL_RE.findall(_read(script))
    assert urls, f"{script.name} should install uv from astral.sh"
    for url in urls:
        host = url.split("//", 1)[1].split("/", 1)[0]
        assert host == ASTRAL_HOST, f"{script.name} references an unexpected host: {url}"


@pytest.mark.parametrize("script", [SH, PS1], ids=["sh", "ps1"])
def test_installers_are_short(script: Path) -> None:
    """Each installer stays under 120 lines so it can be read top to bottom."""
    lines = _read(script).splitlines()
    assert len(lines) < 120, f"{script.name} is {len(lines)} lines (limit 120)"


# ---- install.ps1 ---------------------------------------------------------


def test_install_ps1_exists_and_is_ascii() -> None:
    """The PowerShell installer exists and carries no non-ASCII bytes."""
    assert PS1.is_file(), f"{PS1} is missing"
    raw = PS1.read_bytes()
    assert all(b < 128 for b in raw), "scripts/install.ps1 contains non-ASCII bytes"


def test_install_ps1_parses_with_powershell() -> None:
    """Parse install.ps1 with the PowerShell language parser, when pwsh exists."""
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("pwsh is not installed")
    script = (
        "$errors = $null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{PS1}', "
        "[ref]$null, [ref]$errors) | Out-Null; "
        "if ($errors.Count -gt 0) { $errors | ForEach-Object { $_.Message }; exit 1 }"
    )
    result = subprocess.run(
        [pwsh, "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, f"PowerShell parse errors:\n{result.stdout}{result.stderr}"
