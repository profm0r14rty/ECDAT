"""Hostile ViewModel factory for hardening tests.

Builds :class:`~ecdat.services.viewmodel.ScanVM` and
:class:`~ecdat.services.viewmodel.FindingVM` instances directly from frozen
dataclasses — never from files on disk, so it works on every platform
including Windows.

Every string field is populated with attacker-controlled values that exercise
the "never-interpreted-as-markup" contract: Rich markup directives, ANSI
escape sequences, HTML/JS injections, Markdown table-breaking characters, and
OSC-8 terminal hyperlinks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from ecdat.services.scanner import ScanOutcome
from ecdat.services.viewmodel import FindingVM, PriorityAction, ScanVM
from ecdat_core.models import Detection, Recommendation, RiskAssessment, ScanResult

# ---------------------------------------------------------------------------
# Hostile value catalog
# ---------------------------------------------------------------------------

HOSTILE = (
    "[bold red]pwn[/]",
    "\x1b[31mred\x1b[0m",
    "\x1b]8;;https://evil.example\x07click\x1b]8;;\x07",
    "[link=https://evil.example]x[/link]",
    "<script>alert(1)</script>",
    '"><img src=x onerror=1>',
    "a|b|c",
    "`tick`",
    "line1\nline2",
    "# heading",
    "{0}{bad}%s",
)

# A file path that is exactly 300 characters.
_LONG_PATH = "x" * 288 + "/done.py"  # 288 + 8 + 4 (slashes in a moment) = 300

# "a/b/c/..." then the long part to make it exactly 300.
_LONG_PATH = ("a" * 280) + "/bbbb/" + ("c" * 10) + ".py"
# 280 + 6 + 10 + 3 = 299, let me be exact:
_LONG_PATH = ("a" * 283) + "/bb/" + ("c" * 10) + ".py"  # 283 + 4 + 10 + 3 = 300


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _h(idx: int) -> str:
    """Hostile value at *idx*, wrapping around."""
    return HOSTILE[idx % len(HOSTILE)]


# ---------------------------------------------------------------------------
# FindingVM builder
# ---------------------------------------------------------------------------

def _build_finding(
    fid: int,
    risk_level: str,
    file_path: str,
    *,
    snippet: Optional[str],
    hostile_offset: int,
) -> FindingVM:
    """Build one :class:`FindingVM` with hostile values in every string field.

    Args:
        fid: Sequential finding number (used for deterministic id / line).
        risk_level: One of ``critical``, ``high``, ``medium``, ``low``, ``quantum-safe``.
        file_path: The ``file_path`` for this finding.
        snippet: When not ``None``, a hostile snippet; when ``None``, the
            field is left as ``None`` (the only optional field on ``FindingVM``).
        hostile_offset: Starting index into :data:`HOSTILE` so each finding
            gets different hostile values in its string fields.
    """
    risk_params = {
        "critical":    (1.5, True,  True,  True),
        "high":        (0.9, False, True,  False),
        "medium":      (0.6, False, True,  False),
        "low":         (0.3, False, True,  False),
        "quantum-safe":(0.0, False, False, False),
    }
    urgency, mosca_violation, quant_vuln, class_broken = risk_params[risk_level]

    return FindingVM(
        id=f"finding-{fid}-{risk_level}",
        risk_level=risk_level,
        algorithm=_h(hostile_offset),
        family=_h(hostile_offset + 1),
        file_path=file_path,
        line=10 + fid,
        language="python",
        confidence=0.85,
        quantum_vulnerable=quant_vuln,
        classically_broken=class_broken,
        urgency_ratio=urgency,
        mosca_x=5.0,
        mosca_y=3.0,
        mosca_z=5.0,
        mosca_violation=mosca_violation,
        rationale=_h(hostile_offset + 2),
        recommended=_h(hostile_offset + 3),
        fips_reference=_h(hostile_offset + 4),
        snippet=snippet,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def make_hostile_vm() -> ScanVM:
    """Build a fully-hostile :class:`ScanVM` with one finding per risk level.

    Every string field of every :class:`FindingVM` (and the :class:`ScanVM`
    ``target``) contains one of the eleven hostile payload values.
    The VM invariants are self-consistent: ``total`` equals ``len(findings)``,
    ``counts`` has all five keys, ``safe_ratio`` is computed correctly,
    ``by_file`` and ``by_recommendation`` group correctly, and
    ``priority_actions`` has at least one entry.

    Returns:
        A :class:`ScanVM` ready for renderers, exporters, and the TUI.
    """
    findings = [
        _build_finding(0, "critical",  "src/" + _h(0), snippet=_h(5), hostile_offset=0),
        _build_finding(1, "high",      "src/" + _h(1), snippet=_h(6), hostile_offset=2),
        _build_finding(2, "medium",    "src/medium.py", snippet=None,   hostile_offset=4),
        _build_finding(3, "low",       "src/" + _h(3), snippet=_h(8), hostile_offset=6),
        _build_finding(4, "quantum-safe", _LONG_PATH,  snippet=_h(9), hostile_offset=8),
    ]

    counts = {
        "critical": 1,
        "high": 1,
        "medium": 1,
        "low": 1,
        "quantum-safe": 1,
    }
    total = len(findings)
    safe_ratio = counts["quantum-safe"] / total  # 0.2

    by_file: dict[str, list[FindingVM]] = {}
    for f in findings:
        by_file.setdefault(f.file_path, []).append(f)

    by_recommendation: dict[str, list[FindingVM]] = {}
    for f in findings:
        key = f.recommended or "(none)"
        by_recommendation.setdefault(key, []).append(f)

    # Build a couple of priority actions (the non-quantum-safe ones).
    priority_actions = [
        PriorityAction(
            family=finding.family,
            file_path=finding.file_path,
            worst_risk=finding.risk_level,
            count=1,
            recommended=finding.recommended,
        )
        for finding in findings
        if finding.risk_level != "quantum-safe"
    ]

    return ScanVM(
        target=_h(10),  # "{0}{bad}%s"
        duration_s=0.5,
        files_scanned=5,
        findings=findings,
        counts=counts,
        total=total,
        safe_ratio=safe_ratio,
        by_file=by_file,
        by_recommendation=by_recommendation,
        priority_actions=priority_actions,
    )


def make_hostile_result() -> ScanResult:
    """Build a :class:`~ecdat_core.models.ScanResult` with hostile values.

    Engine models (:class:`Detection`, :class:`RiskAssessment`,
    :class:`Recommendation`) carry hostile strings in every user-controlled
    field so that exporters (Markdown, HTML) face the same injection
    surface as real-world scans.

    Returns:
        A :class:`~ecdat_core.models.ScanResult` with five detections,
        risk assessments, and recommendations.
    """
    scan_id = _h(0)  # hostile scan id
    target = _h(1)
    scanned_at = datetime(2026, 9, 22, 12, 0, 0, tzinfo=timezone.utc).isoformat()
    files_scanned = 5

    risk_levels = ["critical", "high", "medium", "low", "quantum-safe"]
    file_paths = [
        "src/" + _h(0),
        "src/" + _h(1),
        "src/medium.py",
        "src/" + _h(3),
        _LONG_PATH,
    ]

    detections: list[Detection] = []
    risk_assessments: list[RiskAssessment] = []
    recommendations: list[Recommendation] = []

    for i, (risk_level, file_path) in enumerate(zip(risk_levels, file_paths)):
        det_id = f"det-{i}-{risk_level}"

        detections.append(Detection(
            id=det_id,
            file_path=file_path,
            line_number=10 + i,
            matched_text=_h(4 + i) if i != 2 else "some matched text",  # medium = normal snippet
            asset_type="algorithm",
            algorithm_family=_h(i),
            key_size_bits=256 if risk_level == "quantum-safe" else 2048,
            quantum_vulnerable=risk_level != "quantum-safe",
            classically_broken=risk_level == "critical",
            confidence=0.85,
            language="python",
            detection_method="regex",
        ))

        risk_params = {
            "critical": (1.5, True),
            "high": (0.9, False),
            "medium": (0.6, False),
            "low": (0.3, False),
            "quantum-safe": (0.0, False),
        }
        urgency, mosca_violation = risk_params[risk_level]

        risk_assessments.append(RiskAssessment(
            detection_id=det_id,
            migration_time_years=3.0,
            shelf_life_years=5.0,
            threat_horizon_years=5.0,
            urgency_ratio=urgency,
            risk_level=risk_level,  # type: ignore[arg-type]
            mosca_violation=mosca_violation,
        ))

        recommendations.append(Recommendation(
            detection_id=det_id,
            recommended_algorithm=_h(7 + i),
            fips_reference=_h(8 + i),
            rationale=_h(9 + i),
            latency_note=_h(10 + i),
            migration_note=_h(0 + i),
        ))

    return ScanResult(
        scan_id=scan_id,
        target=target,
        detections=detections,
        risk_assessments=risk_assessments,
        recommendations=recommendations,
        scanned_at=scanned_at,
        files_scanned=files_scanned,
    )


def make_hostile_outcome() -> ScanOutcome:
    """Build a :class:`~ecdat.services.scanner.ScanOutcome` with hostile data.

    Wraps a hostile :class:`ScanVM` and a hostile
    :class:`~ecdat_core.models.ScanResult` so that the TUI and renderers
    both receive attacker-controlled content.

    Returns:
        A :class:`ScanOutcome` suitable for TUI ``ResultsScreen`` tests.
    """
    result = make_hostile_result()
    vm = make_hostile_vm()
    return ScanOutcome(result=result, vm=vm, duration_s=0.5)