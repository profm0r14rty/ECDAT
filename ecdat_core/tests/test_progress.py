"""Tests for ECDAT scan progress and cancellation hooks.

Validates the ``on_progress`` callback, ``ScanCancelled`` abort flow,
and that the callback receives stages in the expected order with
monotonically non-decreasing ``current`` during the ``detect`` stage.
"""

from __future__ import annotations

import pathlib

import pytest

from ecdat_core.cli import run_scan
from ecdat_core.progress import ScanCancelled, ScanProgress


@pytest.fixture(autouse=True)
def _sandbox_to_tmpdir(monkeypatch, tmp_path: object) -> None:
    """Pin SCAN_WORKSPACE_ROOT to tmp_path so run_scan can scan it."""
    monkeypatch.setenv("SCAN_WORKSPACE_ROOT", str(pathlib.Path(tmp_path)))


def _make_fixture(tmp_path: pathlib.Path) -> str:
    """Create a minimal source tree with a crypto-using Python file."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("import hashlib\nh = hashlib.md5(b'data')\n", encoding="utf-8")
    return str(tmp_path)


# ---------------------------------------------------------------------------
# ≥ 4 tests
# ---------------------------------------------------------------------------


def test_stage_order(tmp_path: pathlib.Path) -> None:
    """Callback must receive stages in the expected pipeline order."""
    root = _make_fixture(tmp_path)
    stages: list[str] = []

    def cb(prog: ScanProgress) -> None:
        stages.append(prog.stage)

    run_scan(root, on_progress=cb)

    # Ingest will fire at least once, then detect, assess, recommend,
    # assemble, done.  Clone only fires for git_url scans.
    seen_ordered: dict[str, int] = {}
    for s in stages:
        seen_ordered.setdefault(s, len(seen_ordered))

    expected_order = ["ingest", "detect", "assess", "recommend", "assemble", "done"]
    # Every stage we see must appear in the expected order (no going backwards
    # among the stages that actually fire).
    for i, stage in enumerate(expected_order):
        if stage in seen_ordered:
            # All later expected stages that fire must come after
            for later in expected_order[i + 1:]:
                if later in seen_ordered:
                    assert seen_ordered[stage] < seen_ordered[later], (
                        f"{stage!r} ({seen_ordered[stage]}) before "
                        f"{later!r} ({seen_ordered[later]})"
                    )


def test_current_non_decreasing_in_detect(tmp_path: pathlib.Path) -> None:
    """During ``detect``, ``current`` must never decrease."""
    root = _make_fixture(tmp_path)
    detect_currents: list[int] = []

    def cb(prog: ScanProgress) -> None:
        if prog.stage == "detect":
            detect_currents.append(prog.current)

    run_scan(root, on_progress=cb)

    assert len(detect_currents) >= 2, "expected ≥2 detect callbacks"
    for i in range(1, len(detect_currents)):
        assert detect_currents[i] >= detect_currents[i - 1], (
            f"current decreased: {detect_currents[i-1]} → {detect_currents[i]}"
        )


def test_scancancelled_aborts(tmp_path: pathlib.Path) -> None:
    """Raising ScanCancelled inside the callback must abort the scan."""
    root = _make_fixture(tmp_path)

    def cb(prog: ScanProgress) -> None:
        if prog.stage == "detect" and prog.current >= 1:
            raise ScanCancelled("test abort", progress=prog)

    with pytest.raises(ScanCancelled, match="test abort"):
        run_scan(root, on_progress=cb)


def test_identical_detections_with_and_without_callback(tmp_path: pathlib.Path) -> None:
    """Providing on_progress must not alter scan results."""
    root = _make_fixture(tmp_path)
    result_without = run_scan(root)
    result_with = run_scan(root, on_progress=lambda _: None)

    assert result_without.files_scanned == result_with.files_scanned
    assert len(result_without.detections) == len(result_with.detections)
    assert len(result_without.risk_assessments) == len(result_with.risk_assessments)
    assert len(result_without.recommendations) == len(result_with.recommendations)

    # Spot-check one detection
    dets_no = result_without.detections
    dets_yes = result_with.detections
    assert [d.algorithm_family for d in dets_no] == [d.algorithm_family for d in dets_yes]