"""Pure tests for :mod:`ecdat.services.filtering` (Phase 85).

No Textual, no Rich — these exercise only the filter/sort contract on
hand-built :class:`~ecdat.services.viewmodel.FindingVM` instances, so they run
in milliseconds and pin the behaviour the Findings tab relies on.
"""

from __future__ import annotations

from typing import List

from ecdat.services.filtering import (
    SORT_LABELS,
    SORT_MODES,
    filter_findings,
    sort_findings,
)
from ecdat.services.viewmodel import FindingVM


def _finding(
    *,
    id: str,
    risk_level: str = "critical",
    algorithm: str = "RSA-2048",
    family: str = "RSA",
    file_path: str = "auth/login.py",
    line: int = 1,
    urgency_ratio: float = 1.0,
    quantum_vulnerable: bool = True,
    classically_broken: bool = False,
) -> FindingVM:
    """Build a FindingVM with sensible defaults for the fields under test."""
    return FindingVM(
        id=id,
        risk_level=risk_level,
        algorithm=algorithm,
        family=family,
        file_path=file_path,
        line=line,
        language="python",
        confidence=0.9,
        quantum_vulnerable=quantum_vulnerable,
        classically_broken=classically_broken,
        urgency_ratio=urgency_ratio,
        mosca_x=0.5,
        mosca_y=1.0,
        mosca_z=10.0,
        mosca_violation=False,
        rationale="because",
        recommended="ML-KEM",
        fips_reference="FIPS 203",
        snippet=None,
    )


def _sample() -> List[FindingVM]:
    return [
        _finding(id="a", risk_level="critical", algorithm="MD5", family="MD5",
                 file_path="auth/login.py", line=70, urgency_ratio=10.5,
                 quantum_vulnerable=False, classically_broken=True),
        _finding(id="b", risk_level="medium", algorithm="DH", family="DH",
                 file_path="keyexchange/channel.go", line=4, urgency_ratio=0.7),
        _finding(id="c", risk_level="quantum-safe", algorithm="ML-KEM",
                 family="ML-KEM", file_path="quantum/pqc_utils.py", line=3,
                 urgency_ratio=0.0, quantum_vulnerable=False),
        _finding(id="d", risk_level="high", algorithm="RSA-1024", family="RSA",
                 file_path="auth/login.py", line=24, urgency_ratio=2.33),
        _finding(id="e", risk_level="low", algorithm="ECDSA", family="ECDSA",
                 file_path="tokens/signing.js", line=2, urgency_ratio=0.37),
    ]


# ---------------------------------------------------------------------------
# SORT_MODES contract
# ---------------------------------------------------------------------------


def test_sort_modes_and_labels_align() -> None:
    assert SORT_MODES == ("urgency", "file", "algorithm", "risk")
    assert set(SORT_LABELS) == set(SORT_MODES)


# ---------------------------------------------------------------------------
# filter_findings
# ---------------------------------------------------------------------------


def test_no_filters_returns_everything_in_order() -> None:
    findings = _sample()
    assert filter_findings(findings) == findings


def test_levels_subset_keeps_only_those_levels() -> None:
    result = filter_findings(_sample(), levels={"critical"})
    assert [f.id for f in result] == ["a"]


def test_levels_multiple() -> None:
    result = filter_findings(_sample(), levels={"critical", "low"})
    assert {f.id for f in result} == {"a", "e"}


def test_empty_levels_matches_nothing() -> None:
    assert filter_findings(_sample(), levels=set()) == []


def test_query_is_case_insensitive_over_algorithm() -> None:
    assert [f.id for f in filter_findings(_sample(), query="MD5")] == ["a"]
    assert [f.id for f in filter_findings(_sample(), query="md5")] == ["a"]


def test_query_matches_file_path() -> None:
    result = filter_findings(_sample(), query="login")
    assert {f.id for f in result} == {"a", "d"}


def test_query_matches_family() -> None:
    assert [f.id for f in filter_findings(_sample(), query="ECDSA")] == ["e"]


def test_query_whitespace_is_ignored() -> None:
    assert filter_findings(_sample(), query="   ") == _sample()


def test_query_with_no_match_is_empty() -> None:
    assert filter_findings(_sample(), query="zzz") == []


def test_file_filter_is_exact() -> None:
    result = filter_findings(_sample(), file="auth/login.py")
    assert {f.id for f in result} == {"a", "d"}
    assert filter_findings(_sample(), file="login.py") == []


def test_family_filter_is_exact() -> None:
    result = filter_findings(_sample(), family="RSA")
    assert [f.id for f in result] == ["d"]
    assert filter_findings(_sample(), family="RS") == []


def test_combined_filters_are_anded() -> None:
    result = filter_findings(
        _sample(), levels={"critical", "high"}, file="auth/login.py", query="rsa"
    )
    assert [f.id for f in result] == ["d"]


def test_combined_filters_can_yield_empty() -> None:
    result = filter_findings(_sample(), levels={"low"}, family="RSA")
    assert result == []


def test_filter_does_not_mutate_input() -> None:
    findings = _sample()
    before = list(findings)
    filter_findings(findings, levels={"critical"}, query="md5", file="auth/login.py")
    assert findings == before


# ---------------------------------------------------------------------------
# sort_findings
# ---------------------------------------------------------------------------


def test_sort_urgency_is_descending() -> None:
    result = sort_findings(_sample(), "urgency")
    assert [f.id for f in result] == ["a", "d", "b", "e", "c"]
    assert [f.urgency_ratio for f in result] == sorted(
        (f.urgency_ratio for f in result), reverse=True
    )


def test_sort_file_orders_by_path_then_line() -> None:
    result = sort_findings(_sample(), "file")
    keys = [(f.file_path, f.line) for f in result]
    assert keys == sorted(keys)


def test_sort_algorithm_is_case_insensitive() -> None:
    result = sort_findings(_sample(), "algorithm")
    names = [f.algorithm.lower() for f in result]
    assert names == sorted(names)


def test_sort_risk_puts_worst_first() -> None:
    result = sort_findings(_sample(), "risk")
    assert [f.risk_level for f in result] == [
        "critical",
        "high",
        "medium",
        "low",
        "quantum-safe",
    ]


def test_unknown_mode_falls_back_to_urgency() -> None:
    assert [f.id for f in sort_findings(_sample(), "nope")] == [
        f.id for f in sort_findings(_sample(), "urgency")
    ]


def test_sort_is_stable_for_equal_keys() -> None:
    findings = [
        _finding(id="x", file_path="a.py", line=1, urgency_ratio=1.0),
        _finding(id="y", file_path="a.py", line=1, urgency_ratio=1.0),
        _finding(id="z", file_path="a.py", line=1, urgency_ratio=1.0),
    ]
    assert [f.id for f in sort_findings(findings, "urgency")] == ["x", "y", "z"]


def test_sort_does_not_mutate_input() -> None:
    findings = _sample()
    before = list(findings)
    sort_findings(findings, "risk")
    assert findings == before


def test_filter_then_sort_composes() -> None:
    filtered = filter_findings(_sample(), levels={"critical", "medium", "low"})
    ordered = sort_findings(filtered, "urgency")
    assert [f.id for f in ordered] == ["a", "b", "e"]
