"""Frozen ViewModel dataclasses for the ECDAT app layer.

These are the ONLY types that renderers, exporters, and the TUI consume.
Engine models (:mod:`ecdat_core.models`) are touched in exactly one place:
:func:`build_scan_vm`.  Raw strings are stored unchanged — escaping is the
renderers' job.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from ecdat_core.models import Detection, Recommendation, RiskAssessment, ScanResult

# Risk-level sort order (lower index = worse / more severe).
_RISK_ORDER: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "quantum-safe": 4,
}


@dataclass(frozen=True)
class FindingVM:
    """A single finding view-model, joining Detection + RiskAssessment + Recommendation.

    Every field is derived from the engine models — nothing is invented.
    Where a risk assessment or recommendation is missing (shouldn't happen in
    normal operation), sensible defaults are used.
    """

    __slots__ = (
        "id",
        "risk_level",
        "algorithm",
        "family",
        "file_path",
        "line",
        "language",
        "confidence",
        "quantum_vulnerable",
        "classically_broken",
        "urgency_ratio",
        "mosca_x",
        "mosca_y",
        "mosca_z",
        "mosca_violation",
        "rationale",
        "recommended",
        "fips_reference",
        "snippet",
    )

    id: str
    risk_level: str  # critical | high | medium | low | quantum-safe
    algorithm: str  # Most specific display name (e.g. "RSA-2048"), else family
    family: str  # algorithm_family from Detection
    file_path: str  # Forward slashes, no leading "./"
    line: int  # 1-based line number
    language: str
    confidence: float  # 0..1
    quantum_vulnerable: bool
    classically_broken: bool
    urgency_ratio: float
    mosca_x: float  # migration_time_years
    mosca_y: float  # shelf_life_years
    mosca_z: float  # threat_horizon_years
    mosca_violation: bool
    rationale: str
    recommended: str  # recommended_algorithm
    fips_reference: str
    snippet: Optional[str]  # ≤6 lines / ≤400 chars, or None


@dataclass(frozen=True)
class PriorityAction:
    """A grouped priority action — one per (family, file_path).

    Excludes quantum-safe findings.  Groups by (family, file_path), ranked by
    worst risk → max urgency → count.
    """

    __slots__ = ("family", "file_path", "worst_risk", "count", "recommended")

    family: str
    file_path: str
    worst_risk: str  # The most severe risk_level in the group
    count: int  # Number of findings in this group
    recommended: str  # Representative recommendation algorithm


@dataclass(frozen=True)
class ScanVM:
    """Complete scan view-model: aggregates all findings into renderer-ready form.

    ``counts`` ALWAYS has all five keys ("critical", "high", "medium", "low",
    "quantum-safe"), even when some counts are zero.
    ``safe_ratio`` is ``quantum-safe / total``; ``0.0`` when ``total == 0``.
    ``priority_actions`` holds at most 10 grouped actions, excluding
    quantum-safe findings.
    """

    __slots__ = (
        "target",
        "duration_s",
        "files_scanned",
        "findings",
        "counts",
        "total",
        "safe_ratio",
        "by_file",
        "by_recommendation",
        "priority_actions",
    )

    target: str
    duration_s: Optional[float]
    files_scanned: int
    findings: list[FindingVM]  # Sorted: severity → urgency desc → file → line
    counts: dict[str, int]  # ALWAYS all five keys
    total: int
    safe_ratio: float
    by_file: dict[str, list[FindingVM]]
    by_recommendation: dict[str, list[FindingVM]]
    priority_actions: list[PriorityAction]  # ≤10


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_scan_vm(
    result: ScanResult,
    *,
    target: str,
    duration_s: Optional[float] = None,
) -> ScanVM:
    """Build a :class:`ScanVM` from an engine :class:`~ecdat_core.models.ScanResult`.

    Joins detections ↔ risk assessments ↔ recommendations exactly like
    :func:`ecdat_core.cbom_export.export_cbom` does.  Raw strings are stored
    unchanged — escaping is the renderers' job.

    Args:
        result: The complete scan result from the engine.
        target: Display label for the scan (e.g. path or URL).
        duration_s: Wall-clock duration of the scan, if available.

    Returns:
        A fully populated :class:`ScanVM`.
    """
    risk_lookup: dict[str, RiskAssessment] = {
        ra.detection_id: ra for ra in result.risk_assessments
    }
    rec_lookup: dict[str, Recommendation] = {
        rec.detection_id: rec for rec in result.recommendations
    }

    findings: list[FindingVM] = []
    for det in result.detections:
        ra = risk_lookup.get(det.id)
        rec = rec_lookup.get(det.id)
        findings.append(_build_finding(det, ra, rec))

    # Sort: severity (risk_level order), then urgency descending, then file,
    # then line — deterministic tie-breaking.
    findings.sort(
        key=lambda f: (
            _RISK_ORDER.get(f.risk_level, 99),
            -f.urgency_ratio,
            f.file_path,
            f.line,
        )
    )

    # Counts — ALWAYS all five keys.
    counts: dict[str, int] = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "quantum-safe": 0,
    }
    for f in findings:
        counts[f.risk_level] = counts.get(f.risk_level, 0) + 1

    total = len(findings)
    quantum_safe_count = counts.get("quantum-safe", 0)
    safe_ratio = (quantum_safe_count / total) if total > 0 else 0.0

    # Group by file.
    by_file: dict[str, list[FindingVM]] = defaultdict(list)
    for f in findings:
        by_file[f.file_path].append(f)

    # Group by recommendation.
    by_recommendation: dict[str, list[FindingVM]] = defaultdict(list)
    for f in findings:
        key = f.recommended or "(none)"
        by_recommendation[key].append(f)

    priority_actions = _build_priority_actions(findings)

    return ScanVM(
        target=target,
        duration_s=duration_s,
        files_scanned=result.files_scanned,
        findings=findings,
        counts=counts,
        total=total,
        safe_ratio=safe_ratio,
        by_file=dict(by_file),
        by_recommendation=dict(by_recommendation),
        priority_actions=priority_actions,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_finding(
    det: Detection,
    ra: Optional[RiskAssessment],
    rec: Optional[Recommendation],
) -> FindingVM:
    """Build a single :class:`FindingVM` from engine model instances."""
    # Most specific display name: "RSA-2048" when key size is known, else the
    # algorithm family name.
    if det.key_size_bits is not None:
        algorithm = f"{det.algorithm_family}-{det.key_size_bits}"
    else:
        algorithm = det.algorithm_family

    # Normalise the file path: forward slashes, strip leading "./".
    file_path = det.file_path.replace("\\", "/")
    if file_path.startswith("./"):
        file_path = file_path[2:]

    # Snippet: matched text, capped at 6 lines / 400 chars.
    matched = det.matched_text
    if matched:
        lines = matched.split("\n")
        if len(lines) > 6:
            snippet = "\n".join(lines[:6])
        else:
            snippet = matched
        if len(snippet) > 400:
            snippet = snippet[:400]
    else:
        snippet = None

    return FindingVM(
        id=det.id,
        risk_level=ra.risk_level if ra else "quantum-safe",
        algorithm=algorithm,
        family=det.algorithm_family,
        file_path=file_path,
        line=det.line_number,
        language=det.language,
        confidence=det.confidence,
        quantum_vulnerable=det.quantum_vulnerable,
        classically_broken=det.classically_broken,
        urgency_ratio=ra.urgency_ratio if ra else 0.0,
        mosca_x=ra.migration_time_years if ra else 0.0,
        mosca_y=ra.shelf_life_years if ra else 0.0,
        mosca_z=ra.threat_horizon_years if ra else 0.0,
        mosca_violation=ra.mosca_violation if ra else False,
        rationale=rec.rationale if rec else "",
        recommended=rec.recommended_algorithm if rec else "",
        fips_reference=rec.fips_reference if rec else "",
        snippet=snippet,
    )


def _build_priority_actions(
    findings: list[FindingVM],
) -> list[PriorityAction]:
    """Group non-quantum-safe findings into priority actions.

    Groups by ``(family, file_path)``, then ranks by worst risk → max urgency
    → count.  Returns at most 10 actions.
    """
    groups: dict[tuple[str, str], list[FindingVM]] = defaultdict(list)
    for f in findings:
        if f.risk_level == "quantum-safe":
            continue
        groups[(f.family, f.file_path)].append(f)

    # Compute per-group data for sorting.
    group_data: list[tuple[str, str, str, int, float, str]] = []
    for (family, file_path), group in groups.items():
        worst_risk = min(
            group, key=lambda f: _RISK_ORDER.get(f.risk_level, 99)
        ).risk_level
        max_urgency = max(f.urgency_ratio for f in group)
        recommended = group[0].recommended
        group_data.append(
            (family, file_path, worst_risk, len(group), max_urgency, recommended)
        )

    # Rank: worst risk first, then highest max_urgency, then largest count.
    group_data.sort(
        key=lambda x: (
            _RISK_ORDER.get(x[2], 99),
            -x[4],
            -x[3],
        )
    )

    return [
        PriorityAction(
            family=family,
            file_path=file_path,
            worst_risk=worst_risk,
            count=count,
            recommended=recommended,
        )
        for family, file_path, worst_risk, count, _ur, recommended in group_data[:10]
    ]