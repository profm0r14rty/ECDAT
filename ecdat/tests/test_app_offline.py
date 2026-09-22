"""Hardening tests: ECDAT must never use the network except for ``git clone``.

These tests verify the offline contract:
- CLI commands complete with no network access when run against local paths.
- The TUI scans a local folder with no network access.
- No module under ``ecdat/`` (excluding tests) imports ``requests``,
  ``httpx``, ``aiohttp``, ``urllib.request``, ``http.client``, or ``socket``
  directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixture: block all network access
# ---------------------------------------------------------------------------


def _boom(*args, **kwargs):
    raise AssertionError("network access attempted")


@pytest.fixture
def block_network(monkeypatch):
    """Block ALL network access by monkeypatching socket functions.

    Patches both ``socket.getaddrinfo`` and ``socket.create_connection`` so
    any attempt to resolve or connect raises ``AssertionError``.
    """
    monkeypatch.setattr("socket.getaddrinfo", _boom)
    monkeypatch.setattr("socket.create_connection", _boom)
    # Also block urllib's connection path (used by some stdlib callers).
    monkeypatch.setattr("http.client.HTTPConnection", _boom, raising=False)
    yield


# ---------------------------------------------------------------------------
# Path to the demo repo fixture (engine's own test data).
# ---------------------------------------------------------------------------

DEMO_REPO = (
    Path(__file__).resolve().parents[2]
    / "ecdat_core" / "tests" / "fixtures" / "demo_repo"
)

DEMO_REPO_STR = str(DEMO_REPO)


# ---------------------------------------------------------------------------
# CLI commands tested under block_network
# ---------------------------------------------------------------------------


def test_scan_local_under_block_network(block_network) -> None:
    """``ecdat scan <DEMO_REPO> -f json`` must succeed with no network."""
    from ecdat.cli.main import main

    code = main(["scan", DEMO_REPO_STR, "-f", "json"])
    # Can exit 0 (no fail-on) or 1 (findings at/above default).
    assert code in (0, 1), f"scan exited {code}"
    # Acceptance: no exception was raised (block_network would have caught it).


def test_demo_under_block_network(block_network) -> None:
    """``ecdat demo -f json`` must succeed with no network."""
    from ecdat.cli.main import main

    code = main(["demo", "-f", "json"])
    assert code == 0, f"demo exited {code}"


def test_history_under_block_network(block_network) -> None:
    """``ecdat history`` must succeed with no network (may be empty)."""
    from ecdat.cli.main import main

    code = main(["history"])
    assert code == 0, f"history exited {code}"


def test_report_latest_under_block_network(block_network) -> None:
    """``ecdat report latest -f markdown`` must exit 0 after seeding history.

    First runs ``scan`` (which persists to history), then calls ``report latest``.
    Both must complete with no network access.
    """
    from ecdat.cli.main import main

    # Seed history — this persists to ECDAT_HOME (already tmp'd by conftest).
    scan_code = main(["scan", DEMO_REPO_STR, "-f", "json"])
    assert scan_code in (0, 1), f"seed scan exited {scan_code}"

    # Now report latest.
    code = main(["report", "latest", "-f", "markdown"])
    assert code == 0, f"report latest exited {code}"


def test_rules_under_block_network(block_network) -> None:
    """``ecdat rules rsa`` must exit 0 with no network."""
    from ecdat.cli.main import main

    code = main(["rules", "rsa"])
    assert code == 0, f"rules rsa exited {code}"


def test_explain_under_block_network(block_network) -> None:
    """``ecdat explain rsa`` must exit 0 with no network."""
    from ecdat.cli.main import main

    code = main(["explain", "rsa"])
    assert code == 0, f"explain rsa exited {code}"


def test_mosca_under_block_network(block_network) -> None:
    """``ecdat mosca -x 10 -y 3 -z 8`` must exit 0 with no network."""
    from ecdat.cli.main import main

    code = main(["mosca", "-x", "10", "-y", "3", "-z", "8"])
    assert code == 0, f"mosca exited {code}"


def test_doctor_under_block_network(block_network) -> None:
    """``ecdat doctor`` must exit 0 or 1 (if git missing) with no network."""
    from ecdat.cli.main import main

    code = main(["doctor"])
    assert code in (0, 1), f"doctor exited {code}"


def test_about_no_spin_under_block_network(block_network) -> None:
    """``ecdat about --spin 0`` must exit 0, no animation, no network."""
    from ecdat.cli.main import main

    code = main(["about", "--spin", "0"])
    assert code == 0, f"about --spin 0 exited {code}"


# ---------------------------------------------------------------------------
# TUI: scan a tiny local folder under block_network
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tui_scan_local_under_block_network(block_network, tmp_path: Path) -> None:
    """Push a local folder scan through the TUI under ``block_network``.

    Creates a tiny temp dir with one ``.py`` file, pushes a ``ScanScreen``
    directly (same pattern as existing TUI scan tests), and asserts the screen
    reaches ``ResultsScreen`` with ``vm.total >= 0``.
    Skips on Windows (Textual headless TUI not fully supported).
    """
    if sys.platform == "win32":
        pytest.skip("TUI headless not fully supported on Windows")

    from ecdat.tui.app import EcdatApp
    from ecdat.tui.screens.results import ResultsScreen
    from ecdat.tui.screens.scan import ScanScreen

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from tui_helpers import wait_until  # noqa: E402

    # Create a tiny temp dir with one .py file.
    py_file = tmp_path / "test_mod.py"
    py_file.write_text(
        'import hashlib\n\ndef hash_it(data):\n    return hashlib.sha256(data).hexdigest()\n',
        encoding="utf-8",
    )

    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()

        # Push ScanScreen directly (same pattern as test_app_tui_scan.py).
        screen = ScanScreen(str(tmp_path), label="offline-test")
        app.push_screen(screen)
        await pilot.pause()

        # Wait for scan to complete (up to 30s).
        results = await wait_until(
            pilot,
            lambda: app.screen if isinstance(app.screen, ResultsScreen) else None,
            timeout=30.0,
        )

        assert results.vm.total >= 0, "ResultsScreen vm.total is negative (bug)"
        await pilot.pause(0.3)


# ---------------------------------------------------------------------------
# Source-audit: no forbidden network imports under ecdat/ (excluding tests)
# ---------------------------------------------------------------------------


_FORBIDDEN_IMPORTS: list[tuple[str, str]] = [
    ("import requests", "requests"),
    ("import httpx", "httpx"),
    ("import aiohttp", "aiohttp"),
    # urllib.request specifically — urllib.parse is used and allowed.
    ("urllib.request", "urllib.request"),
    ("http.client", "http.client"),
    ("import socket", "import socket"),
    ("from socket", "from socket"),
]


def test_no_forbidden_network_imports() -> None:
    """Every ``*.py`` under ``ecdat/`` (excluding tests) must contain zero
    forbidden network-import patterns: ``requests``, ``httpx``, ``aiohttp``,
    ``urllib.request``, ``http.client``, or direct ``socket`` imports.
    """
    ecdat_root = Path(__file__).resolve().parents[1]  # ecdat/
    tests_root = ecdat_root / "tests"

    violations: list[str] = []

    for py_file in sorted(ecdat_root.rglob("*.py")):
        if tests_root in py_file.parents:
            continue  # skip test files

        lines = py_file.read_text(encoding="utf-8").splitlines()
        for line_no, line in enumerate(lines, start=1):
            stripped = line.strip()
            # Skip comments / docstrings (they can mention forbidden names).
            if stripped.startswith("#"):
                continue

            for pattern, label in _FORBIDDEN_IMPORTS:
                if pattern in stripped:
                    # False-positive guard: "urllib.parse" is allowed
                    # (matches "urllib.request" only).
                    if pattern == "urllib.request" and "urllib.parse" in stripped:
                        continue
                    # False-positive guard: "from socket import" is the pattern,
                    # but "import socket" could be in test-only modules.
                    violations.append(
                        f"  {py_file.relative_to(ecdat_root)}:{line_no}: "
                        f"'{label}' — {stripped.strip()}"
                    )

    if violations:
        pytest.fail(
            f"{len(violations)} forbidden network import(s) found:\n"
            + "\n".join(violations)
        )