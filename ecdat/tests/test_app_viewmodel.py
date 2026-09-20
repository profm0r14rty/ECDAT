"""Tests for ecdat.services.viewmodel."""

from __future__ import annotations

import tempfile
from pathlib import Path

from ecdat_core.cli import run_scan
from ecdat_core.models import Detection
from ecdat.services.viewmodel import build_scan_vm

DEMO_REPO = (
    Path(__file__).resolve().parents[2]
    / "ecdat_core"
    / "tests"
    / "fixtures"
    / "demo_repo"
)


# ---------------------------------------------------------------------------
# build_scan_vm structural invariants
# ---------------------------------------------------------------------------


def test_counts_sum_equals_total_equals_detections():
    """counts sum == total == len(result.detections)."""
    result = run_scan(str(DEMO_REPO), sandboxed=False)
    vm = build_scan_vm(result, target=str(DEMO_REPO))

    counts_sum = sum(vm.counts.values())
    assert counts_sum == vm.total, f"counts sum {counts_sum} != total {vm.total}"
    assert vm.total == len(result.detections), (
        f"vm.total {vm.total} != result.detections {len(result.detections)}"
    )
    assert len(vm.findings) == vm.total


def test_all_five_count_keys_present():
    """All five risk-level keys are present in counts, even when zero."""
    result = run_scan(str(DEMO_REPO), sandboxed=False)
    vm = build_scan_vm(result, target=str(DEMO_REPO))

    assert set(vm.counts.keys()) == {"critical", "high", "medium", "low", "quantum-safe"}


def test_findings_sorted_by_severity_then_urgency_then_file_then_line():
    """Findings are sorted: risk severity → urgency desc → file path → line."""
    result = run_scan(str(DEMO_REPO), sandboxed=False)
    vm = build_scan_vm(result, target=str(DEMO_REPO))

    risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "quantum-safe": 4}
    for i in range(len(vm.findings) - 1):
        a = vm.findings[i]
        b = vm.findings[i + 1]
        key_a = (risk_order.get(a.risk_level, 99), -a.urgency_ratio, a.file_path, a.line)
        key_b = (risk_order.get(b.risk_level, 99), -b.urgency_ratio, b.file_path, b.line)
        assert key_a <= key_b, (
            f"Sort violation at index {i}: "
            f"({a.risk_level}, {a.urgency_ratio:.3f}, {a.file_path}:{a.line}) vs "
            f"({b.risk_level}, {b.urgency_ratio:.3f}, {b.file_path}:{b.line})"
        )


def test_no_backslashes_in_file_path():
    """Every FindingVM.file_path uses forward slashes — no backslashes."""
    result = run_scan(str(DEMO_REPO), sandboxed=False)
    vm = build_scan_vm(result, target=str(DEMO_REPO))

    for f in vm.findings:
        assert "\\" not in f.file_path, f"Backslash in file_path: {f.file_path!r}"

    # Also verify in priority actions.
    for pa in vm.priority_actions:
        assert "\\" not in pa.file_path, f"Backslash in priority file_path: {pa.file_path!r}"


def test_priority_actions_at_most_10_and_ordered():
    """priority_actions ≤10 and ordered worst risk → count (>0)."""
    result = run_scan(str(DEMO_REPO), sandboxed=False)
    vm = build_scan_vm(result, target=str(DEMO_REPO))

    assert len(vm.priority_actions) <= 10

    risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "quantum-safe": 4}
    for i in range(len(vm.priority_actions) - 1):
        a = vm.priority_actions[i]
        b = vm.priority_actions[i + 1]
        rank_a = risk_order.get(a.worst_risk, 99)
        rank_b = risk_order.get(b.worst_risk, 99)
        assert rank_a <= rank_b, (
            f"Priority sort violation at index {i}: "
            f"({a.family}, {a.file_path}) worst_risk={a.worst_risk} vs "
            f"({b.family}, {b.file_path}) worst_risk={b.worst_risk}"
        )


def test_priority_actions_exclude_quantum_safe():
    """No priority action has worst_risk='quantum-safe'."""
    result = run_scan(str(DEMO_REPO), sandboxed=False)
    vm = build_scan_vm(result, target=str(DEMO_REPO))

    for pa in vm.priority_actions:
        assert pa.worst_risk != "quantum-safe", (
            f"Priority action for ({pa.family}, {pa.file_path}) is quantum-safe"
        )


def test_empty_directory_total_zero_safe_ratio_zero():
    """Scanning an empty temp directory → total=0, safe_ratio=0.0, no exception."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_scan(tmpdir, sandboxed=False)
        vm = build_scan_vm(result, target=tmpdir)

        assert vm.total == 0
        assert vm.safe_ratio == 0.0
        assert len(vm.findings) == 0
        assert vm.counts == {"critical": 0, "high": 0, "medium": 0, "low": 0, "quantum-safe": 0}
        assert len(vm.priority_actions) == 0


def test_hostile_file_path_passes_through_unchanged():
    """A Detection with a hostile file_path is passed through as-is — no escaping."""
    result = run_scan(str(DEMO_REPO), sandboxed=False)

    if not result.detections:
        pytest.skip("No detections to modify")

    hostile_path = "[bold red]x[/].py"
    modified_dets = [
        det if i != 0 else det.model_copy(update={"file_path": hostile_path})
        for i, det in enumerate(result.detections)
    ]
    modified = result.model_copy(update={"detections": modified_dets})

    vm = build_scan_vm(modified, target=str(DEMO_REPO))

    found = [f for f in vm.findings if f.file_path == hostile_path]
    assert len(found) == 1, (
        f"Expected one finding with file_path={hostile_path!r}, got {len(found)}"
    )
    assert found[0].file_path == hostile_path


def test_duration_is_passed_through():
    """duration_s from the caller appears on the ScanVM."""
    result = run_scan(str(DEMO_REPO), sandboxed=False)
    vm = build_scan_vm(result, target="test-target", duration_s=12.34)
    assert vm.duration_s == 12.34


def test_duration_none_when_not_given():
    """duration_s is None when not provided."""
    result = run_scan(str(DEMO_REPO), sandboxed=False)
    vm = build_scan_vm(result, target="test-target")
    assert vm.duration_s is None


def test_finding_algorithm_shows_key_size():
    """When key_size_bits is known, algorithm is "FAMILY-BITS" e.g. "RSA-1024"."""
    result = run_scan(str(DEMO_REPO), sandboxed=False)
    vm = build_scan_vm(result, target=str(DEMO_REPO))

    # The demo repo has RSA with key_size_bits=1024.
    rsa_findings = [f for f in vm.findings if f.family == "RSA"]
    assert len(rsa_findings) > 0, "Expected RSA detections in demo_repo"
    for f in rsa_findings:
        if f.confidence == 1.0:  # Exact API-call match should carry the key size
            assert "RSA-1024" in f.algorithm, f"Expected RSA-1024, got {f.algorithm!r}"