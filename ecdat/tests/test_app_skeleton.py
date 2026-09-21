"""Tests for the app-layer skeleton."""

import subprocess
import sys


def test_version_flag_exits_zero_and_prints_version():
    """`python -m ecdat --version` exits 0 and prints the version."""
    result = subprocess.run(
        [sys.executable, "-m", "ecdat", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "ecdat" in result.stdout
    # Must print a version string containing digits
    assert any(c.isdigit() for c in result.stdout)


def test_ecdat_core_does_not_pull_in_app_layer():
    """Importing ecdat_core.cli must not pull ecdat or rich into sys.modules."""
    script = """\
import ecdat_core.cli  # noqa: F401
import sys

forbidden = frozenset({"ecdat", "rich"})
forbidden_prefixes = ("ecdat.", "rich.")

found = []
for modname in sorted(sys.modules):
    if modname in forbidden or modname.startswith(forbidden_prefixes):
        found.append(modname)

if found:
    print("FAIL: forbidden modules found:", ", ".join(found))
    sys.exit(1)
print("OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}, stdout: {result.stdout}"