"""CycloneDX 1.6 CBOM export module for ECDAT.

Converts an ECDAT :class:`ScanResult` into a dict matching the real
CycloneDX 1.6 BOM JSON structure, and provides a lightweight summary
format optimised for frontend consumption.

Public API:
    - :func:`export_cbom` -> full CycloneDX 1.6 BOM dict.
    - :func:`export_summary` -> frontend-friendly summary dict.
"""

from __future__ import annotations

from collections import Counter
from uuid import uuid4

from ecdat_core.models import Detection, Recommendation, RiskAssessment, ScanResult

# ---------------------------------------------------------------------------
# ECDAT tool identity embedded in every CBOM.
# ---------------------------------------------------------------------------
_TOOL_NAME = "ECDAT"
_TOOL_VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# Algorithm family keywords → CycloneDX ``algorithmProperties.primitive``.
# Checked case-insensitively against ``algorithm_family``.
# ---------------------------------------------------------------------------
_PRIMITIVE_RULES: list[tuple[str, str]] = [
    ("sign", "signature"),
    ("dsa", "signature"),
    ("ecdsa", "signature"),
    ("sha", "hash"),
    ("md5", "hash"),
    ("hash", "hash"),
    ("aes", "block-cipher"),
    ("des", "block-cipher"),
    ("blowfish", "block-cipher"),
    ("cast", "block-cipher"),
    ("idea", "block-cipher"),
    ("rc4", "block-cipher"),
    ("chacha", "block-cipher"),
    ("salsa", "block-cipher"),
    ("dh", "key-agreement"),
    ("ecdh", "key-agreement"),
    ("key-agreement", "key-agreement"),
    ("key-exchange", "key-agreement"),
    ("kem", "key-agreement"),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def export_cbom(scan_result: ScanResult) -> dict:
    """Produce a CycloneDX 1.6 BOM dict from a :class:`ScanResult`.

    The returned dict conforms to the real CycloneDX 1.6 specification with
    ``bomFormat`` set to ``"CycloneDX"``, ``specVersion`` set to ``"1.6"``,
    and each detection mapped to a ``cryptographic-asset`` component.

    Args:
        scan_result: The complete scan result to export.

    Returns:
        A dict matching the CycloneDX 1.6 BOM structure.
    """
    risk_lookup: dict[str, RiskAssessment] = {
        ra.detection_id: ra for ra in scan_result.risk_assessments
    }
    rec_lookup: dict[str, Recommendation] = {
        rec.detection_id: rec for rec in scan_result.recommendations
    }

    components = [
        _build_component(det, risk_lookup, rec_lookup)
        for det in scan_result.detections
    ]

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": scan_result.scanned_at,
            "tools": {
                "components": [
                    {
                        "type": "application",
                        "name": _TOOL_NAME,
                        "version": _TOOL_VERSION,
                    }
                ]
            },
            "component": {
                "type": "application",
                "name": scan_result.target,
            },
        },
        "components": components,
    }


def export_summary(scan_result: ScanResult) -> dict:
    """Produce a frontend-friendly summary dict from a :class:`ScanResult`.

    Includes detection counts, quantum-vulnerability statistics, risk-level
    breakdown, algorithm-family distribution, and the five highest-urgency
    detections.

    Args:
        scan_result: The complete scan result to summarise.

    Returns:
        A dict with aggregated statistics ready for frontend consumption.
    """
    total = len(scan_result.detections)
    vuln_count = sum(
        1 for det in scan_result.detections if det.quantum_vulnerable
    )

    risk_lookup: dict[str, RiskAssessment] = {
        ra.detection_id: ra for ra in scan_result.risk_assessments
    }

    # Risk level counts (initialise all buckets so the frontend always sees
    # every level even when the count is zero).
    risk_level_counts: dict[str, int] = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "quantum-safe": 0,
    }
    for ra in scan_result.risk_assessments:
        risk_level_counts[ra.risk_level] = risk_level_counts.get(ra.risk_level, 0) + 1

    # Algorithm family counts.
    family_counter: Counter[str] = Counter(
        det.algorithm_family for det in scan_result.detections
    )

    # Top-5 highest-urgency detections.
    top_5 = _top_urgency(scan_result.detections, risk_lookup, limit=5)

    return {
        "total_detections": total,
        "quantum_vulnerable_count": vuln_count,
        "quantum_vulnerable_percentage": (vuln_count / total * 100.0) if total else 0.0,
        "risk_level_counts": risk_level_counts,
        "algorithm_family_counts": dict(family_counter),
        "top_5_urgency": top_5,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _classify_primitive(algorithm_family: str) -> str | None:
    """Best-effort classification of an algorithm family to a CycloneDX primitive.

    Args:
        algorithm_family: The algorithm family name (e.g. ``"RSA"``, ``"SHA"``).

    Returns:
        One of ``"signature"``, ``"hash"``, ``"block-cipher"``,
        ``"key-agreement"``, or ``None`` if unclassifiable.
    """
    family_lower = algorithm_family.lower()
    for keyword, primitive in _PRIMITIVE_RULES:
        if keyword in family_lower:
            return primitive
    return None


def _build_component(
    detection: Detection,
    risk_lookup: dict[str, RiskAssessment],
    rec_lookup: dict[str, Recommendation],
) -> dict:
    """Build a single CycloneDX component dict for a detection.

    Args:
        detection: The detection to represent as a component.
        risk_lookup: Map from detection ID to its risk assessment.
        rec_lookup: Map from detection ID to its recommendation.

    Returns:
        A dict matching the CycloneDX 1.6 component structure for
        ``cryptographic-asset`` components.
    """
    ra = risk_lookup.get(detection.id)
    rec = rec_lookup.get(detection.id)

    # --- cryptoProperties ---
    crypto_props: dict = {"assetType": detection.asset_type}
    if detection.asset_type == "algorithm":
        algo_props: dict = {}
        primitive = _classify_primitive(detection.algorithm_family)
        if primitive is not None:
            algo_props["primitive"] = primitive
        else:
            algo_props["primitive"] = None
        algo_props["parameterSetIdentifier"] = (
            str(detection.key_size_bits) if detection.key_size_bits is not None else None
        )
        crypto_props["algorithmProperties"] = algo_props

    # --- properties ---
    properties = [
        {"name": "ecdat:quantumVulnerable", "value": str(detection.quantum_vulnerable)},
        {"name": "ecdat:classicallyBroken", "value": str(detection.classically_broken)},
        {"name": "ecdat:riskLevel", "value": ra.risk_level if ra else ""},
        {"name": "ecdat:confidence", "value": str(detection.confidence)},
        {"name": "ecdat:recommendedAlgorithm", "value": rec.recommended_algorithm if rec else ""},
        {"name": "ecdat:fipsReference", "value": rec.fips_reference if rec else ""},
    ]

    return {
        "type": "cryptographic-asset",
        "bom-ref": detection.id,
        "name": detection.algorithm_family,
        "cryptoProperties": crypto_props,
        "evidence": {
            "occurrences": [
                {"location": detection.file_path, "line": detection.line_number}
            ]
        },
        "properties": properties,
    }


def _top_urgency(
    detections: list[Detection],
    risk_lookup: dict[str, RiskAssessment],
    limit: int = 5,
) -> list[dict]:
    """Return the *limit* highest-urgency detections as a list of dicts.

    Each dict contains ``detection_id``, ``algorithm_family``, ``risk_level``,
    ``urgency_ratio``, ``file_path``, and ``line_number``.

    Args:
        detections: All detections to consider.
        risk_lookup: Map from detection ID to its risk assessment.
        limit: Maximum number of results (default 5).

    Returns:
        A list of dicts sorted by ``urgency_ratio`` descending.
    """
    paired = []
    for det in detections:
        ra = risk_lookup.get(det.id)
        if ra is None:
            continue
        paired.append(
            {
                "detection_id": det.id,
                "algorithm_family": det.algorithm_family,
                "risk_level": ra.risk_level,
                "urgency_ratio": ra.urgency_ratio,
                "file_path": det.file_path,
                "line_number": det.line_number,
            }
        )
    paired.sort(key=lambda item: item["urgency_ratio"], reverse=True)
    return paired[:limit]
