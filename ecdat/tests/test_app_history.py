"""Tests for ecdat.services.history."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ecdat.services.history import (
    _MAX_RECORDS,
    get_by_id,
    get_latest,
    load_history,
    save_scan,
)
from ecdat.services.paths import history_dir
from ecdat_core.cli import run_scan
from ecdat_core.models import ScanResult


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect ECDAT_HOME to a temp directory for every test."""
    monkeypatch.setenv("ECDAT_HOME", str(tmp_path))


@pytest.fixture
def demo_scan_result(tmp_path: Path) -> ScanResult:
    """Return a real ScanResult from scanning the demo fixture."""
    fixture_root = Path(__file__).resolve().parents[2] / "ecdat_core" / "tests" / "fixtures" / "demo_repo"
    # Pin SCAN_WORKSPACE_ROOT so the sandbox check passes.
    import os as _os
    _os.environ["SCAN_WORKSPACE_ROOT"] = str(fixture_root.parent)
    return run_scan(str(fixture_root))


# ---- save_scan ----------------------------------------------------------


def test_save_creates_file(demo_scan_result: ScanResult) -> None:
    save_scan(demo_scan_result)
    hist_dir = history_dir()
    files = list(hist_dir.glob("*.json"))
    assert len(files) == 1
    assert files[0].name == f"{demo_scan_result.scan_id}.json"


def test_saved_scan_is_valid_json(demo_scan_result: ScanResult) -> None:
    save_scan(demo_scan_result)
    path = history_dir() / f"{demo_scan_result.scan_id}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["scan_id"] == demo_scan_result.scan_id
    assert raw["target"] == demo_scan_result.target


def test_save_does_not_raise_on_permission_error(
    demo_scan_result: ScanResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """save_scan must swallow errors (warning on stderr)."""
    # Create a scenario where writing will fail: ECDAT_HOME points to a
    # path where the parent is a regular file, not a directory.
    bad_parent = Path(os.environ["ECDAT_HOME"]) / "not-a-dir"
    bad_parent.write_text("")
    monkeypatch.setenv("ECDAT_HOME", str(bad_parent / "sub"))

    # Must not raise.
    save_scan(demo_scan_result)


# ---- load_history -------------------------------------------------------


def test_load_empty_history() -> None:
    assert load_history() == []


def test_load_history_returns_records(demo_scan_result: ScanResult) -> None:
    save_scan(demo_scan_result)
    records = load_history()
    assert len(records) == 1
    assert records[0].scan_id == demo_scan_result.scan_id


def test_load_history_skips_corrupt(tmp_path: Path) -> None:
    """Corrupt JSON files must be skipped with no exception."""
    hist_dir = history_dir()
    (hist_dir / "corrupt.json").write_text("not valid {{{", encoding="utf-8")
    records = load_history()
    # Should not crash, and the corrupt file is ignored.
    assert isinstance(records, list)


def test_load_history_newest_first(demo_scan_result: ScanResult, monkeypatch: pytest.MonkeyPatch) -> None:
    """Records must be sorted by scanned_at descending."""
    # Create a second result with a newer timestamp.
    from datetime import datetime, timezone
    import copy

    result2 = ScanResult(
        scan_id="newer-id",
        target=demo_scan_result.target,
        detections=[],
        risk_assessments=[],
        recommendations=[],
        scanned_at=datetime(2099, 1, 1, tzinfo=timezone.utc).isoformat(),
        files_scanned=0,
    )
    save_scan(demo_scan_result)
    save_scan(result2)

    records = load_history()
    assert len(records) >= 2
    assert records[0].scan_id == "newer-id"


# ---- get_latest ---------------------------------------------------------


def test_get_latest_none_when_empty() -> None:
    assert get_latest() is None


def test_get_latest_returns_newest(demo_scan_result: ScanResult) -> None:
    save_scan(demo_scan_result)
    latest = get_latest()
    assert latest is not None
    assert latest.scan_id == demo_scan_result.scan_id


# ---- get_by_id ----------------------------------------------------------


def test_get_by_id_found(demo_scan_result: ScanResult) -> None:
    save_scan(demo_scan_result)
    result = get_by_id(demo_scan_result.scan_id)
    assert result is not None
    assert result.scan_id == demo_scan_result.scan_id


def test_get_by_id_not_found() -> None:
    assert get_by_id("nonexistent-uuid") is None


def test_get_by_id_corrupt_returns_none(tmp_path: Path) -> None:
    """A corrupt file for a given ID returns None (with stderr warning)."""
    hist_dir = history_dir()
    (hist_dir / "bad-id.json").write_text("garbage", encoding="utf-8")
    result = get_by_id("bad-id")
    assert result is None


# ---- eviction ------------------------------------------------------------


def test_max_records_eviction(demo_scan_result: ScanResult) -> None:
    """When exceeding MAX_RECORDS, oldest entries are evicted."""
    hist_dir = history_dir()

    # Create MAX_RECORDS + 5 entries.
    for i in range(_MAX_RECORDS + 5):
        r = ScanResult(
            scan_id=f"scan-{i:04d}",
            target=demo_scan_result.target,
            detections=[],
            risk_assessments=[],
            recommendations=[],
            scanned_at=f"2024-01-{(i % 28) + 1:02d}T00:00:00+00:00",
            files_scanned=i,
        )
        save_scan(r)

    # Should have at most MAX_RECORDS on disk.
    files = list(hist_dir.glob("[!.]*.json"))
    assert len(files) <= _MAX_RECORDS