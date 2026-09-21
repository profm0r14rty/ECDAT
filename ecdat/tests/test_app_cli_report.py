"""Tests for ecdat.cli.commands.report and ecdat.cli.commands.history_cmd."""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from ecdat.services.history import get_by_id, save_scan
from ecdat_core.cli import run_scan
from ecdat_core.models import ScanResult


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect ECDAT_HOME to a temp directory for every test."""
    monkeypatch.setenv("ECDAT_HOME", str(tmp_path))


@pytest.fixture
def demo_result() -> ScanResult:
    fixture_root = (
        Path(__file__).resolve().parents[2]
        / "ecdat_core" / "tests" / "fixtures" / "demo_repo"
    )
    os.environ["SCAN_WORKSPACE_ROOT"] = str(fixture_root.parent)
    return run_scan(str(fixture_root))


# ---- history command ---------------------------------------------------


def test_history_empty_output() -> None:
    from ecdat.cli.commands.history_cmd import run
    # Mock args — any object with no attrs works.
    class Args:
        pass
    # Redirect stderr to capture output.
    buf = io.StringIO()
    with patch("sys.stderr", buf):
        rc = run(Args())
    assert rc == 0
    assert "No scan history found" in buf.getvalue()


def test_history_with_records(demo_result: ScanResult) -> None:
    save_scan(demo_result)

    from ecdat.cli.commands.history_cmd import run
    class Args:
        pass

    buf = io.StringIO()
    old_stdout = sys.stdout
    try:
        sys.stdout = buf
        rc = run(Args())
    finally:
        sys.stdout = old_stdout

    assert rc == 0
    output = buf.getvalue()
    assert demo_result.scan_id[:8] in output  # partial ID visible


# ---- report command ----------------------------------------------------


def test_report_latest_not_found() -> None:
    from ecdat.cli.commands.report import run
    class Args:
        scan_ref = "latest"
        format = "markdown"

    buf = io.StringIO()
    with patch("sys.stderr", buf):
        rc = run(Args())
    assert rc == 1
    assert "no scan history" in buf.getvalue().lower()


def test_report_by_id_not_found() -> None:
    from ecdat.cli.commands.report import run
    class Args:
        scan_ref = "nonexistent-id"
        format = "markdown"

    buf = io.StringIO()
    with patch("sys.stderr", buf):
        rc = run(Args())
    assert rc == 1
    assert "not found" in buf.getvalue().lower()


def test_report_latest_markdown(demo_result: ScanResult) -> None:
    save_scan(demo_result)

    from ecdat.cli.commands.report import run
    class Args:
        scan_ref = "latest"
        format = "markdown"

    buf = io.StringIO()
    old_stdout = sys.stdout
    try:
        sys.stdout = buf
        rc = run(Args())
    finally:
        sys.stdout = old_stdout

    assert rc == 0
    output = buf.getvalue()
    assert "# ECDAT Scan Report" in output
    assert demo_result.scan_id in output


def test_report_latest_html(demo_result: ScanResult) -> None:
    save_scan(demo_result)

    from ecdat.cli.commands.report import run
    class Args:
        scan_ref = "latest"
        format = "html"

    buf = io.StringIO()
    old_stdout = sys.stdout
    try:
        sys.stdout = buf
        rc = run(Args())
    finally:
        sys.stdout = old_stdout

    assert rc == 0
    output = buf.getvalue()
    assert "<!DOCTYPE html>" in output


def test_report_by_id(demo_result: ScanResult) -> None:
    save_scan(demo_result)

    from ecdat.cli.commands.report import run
    class Args:
        scan_ref = demo_result.scan_id
        format = "markdown"

    buf = io.StringIO()
    old_stdout = sys.stdout
    try:
        sys.stdout = buf
        rc = run(Args())
    finally:
        sys.stdout = old_stdout

    assert rc == 0
    assert "# ECDAT Scan Report" in buf.getvalue()


def test_report_invalid_format(demo_result: ScanResult) -> None:
    save_scan(demo_result)

    from ecdat.cli.commands.report import run
    class Args:
        scan_ref = "latest"
        format = "pdf"  # invalid

    buf = io.StringIO()
    with patch("sys.stderr", buf):
        rc = run(Args())
    assert rc == 2
    assert "unknown format" in buf.getvalue().lower()