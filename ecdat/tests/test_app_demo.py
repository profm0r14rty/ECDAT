"""Tests for ``ecdat demo`` and the bundled demo-project service."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ecdat.cli import main
from ecdat.services.demo import demo_project, demo_source

SHOWCASE_REPO = (
    Path(__file__).resolve().parents[2]
    / "ecdat_core"
    / "tests"
    / "fixtures"
    / "showcase_repo"
)


def _scan_summary(path: Path):
    """Return ``(total, counts, files_scanned)`` for a directory scan."""
    from ecdat.services.scanner import classify_target, perform_scan

    outcome = perform_scan(classify_target(str(path)))
    return outcome.vm.total, outcome.vm.counts, outcome.vm.files_scanned


# ---------------------------------------------------------------------------
# Bundled asset
# ---------------------------------------------------------------------------


def test_demo_source_is_the_packaged_project():
    source = demo_source()
    assert source.is_dir()
    names = {child.name for child in source.iterdir()}
    assert {"auth", "quantum", "payments"} <= names


def test_demo_project_matches_showcase_repo_scan():
    """Parity guard: the packaged copy must produce the same scan as showcase."""
    if not SHOWCASE_REPO.is_dir():
        pytest.skip("showcase_repo fixture is not present")

    with demo_project() as path:
        demo_total, demo_counts, demo_files = _scan_summary(path)

    showcase_total, showcase_counts, showcase_files = _scan_summary(SHOWCASE_REPO)

    assert demo_files == showcase_files
    assert demo_total == showcase_total
    assert demo_counts == showcase_counts


def test_demo_project_temp_dir_is_removed():
    with demo_project() as path:
        assert path.is_dir()
        captured = path
    assert not captured.exists()


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


def test_demo_json_format_parses(capsys):
    rc = main(["demo", "-f", "json"])
    captured = capsys.readouterr()
    assert rc == 0
    data = json.loads(captured.out)
    assert isinstance(data["detections"], list)
    assert len(data["detections"]) > 0


def test_demo_summary_format_parses(capsys):
    rc = main(["demo", "-f", "summary"])
    captured = capsys.readouterr()
    assert rc == 0
    data = json.loads(captured.out)
    assert "total_detections" in data


def test_demo_pretty_renders_report_and_note(capsys):
    rc = main(["demo"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "Scan Summary" in captured.out
    assert "demo project (bundled sample)" in captured.out
    assert "intentionally insecure" in captured.err


def test_demo_path_materialises_and_prints(capsys):
    rc = main(["demo", "--path"])
    captured = capsys.readouterr()
    assert rc == 0

    printed = captured.out.strip()
    assert printed
    destination = Path(printed)
    assert destination.is_dir()

    files = [p for p in destination.rglob("*") if p.is_file()]
    assert len(files) >= 8
