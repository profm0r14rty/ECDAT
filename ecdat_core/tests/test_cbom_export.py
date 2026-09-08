"""Tests for the ECDAT CycloneDX 1.6 CBOM export module.

Validates that :func:`export_cbom` produces a well-formed CycloneDX 1.6 BOM
dict and that :func:`export_summary` computes correct aggregate statistics.
"""

from __future__ import annotations

import pytest

from ecdat_core.cbom_export import export_cbom, export_summary
from ecdat_core.models import (
    Detection,
    Recommendation,
    RiskAssessment,
    ScanResult,
)

# ---------------------------------------------------------------------------
# Hand-built test data
# ---------------------------------------------------------------------------

_DET_RSA = Detection(
    id="det-rsa-1",
    file_path="src/auth/crypto.py",
    line_number=10,
    matched_text="RSA.generate(2048)",
    asset_type="algorithm",
    algorithm_family="RSA",
    key_size_bits=2048,
    quantum_vulnerable=True,
    confidence=0.95,
    language="python",
    detection_method="regex",
)

_DET_SHA = Detection(
    id="det-sha-1",
    file_path="src/utils/hashing.py",
    line_number=25,
    matched_text="hashlib.sha256()",
    asset_type="algorithm",
    algorithm_family="SHA",
    key_size_bits=None,
    quantum_vulnerable=True,
    confidence=0.8,
    language="python",
    detection_method="regex",
)

_DET_AES = Detection(
    id="det-aes-1",
    file_path="src/main.py",
    line_number=5,
    matched_text="AES.new(key, AES.MODE_CBC)",
    asset_type="algorithm",
    algorithm_family="AES",
    key_size_bits=256,
    quantum_vulnerable=False,
    confidence=1.0,
    language="python",
    detection_method="regex",
)

_RA_RSA = RiskAssessment(
    detection_id="det-rsa-1",
    migration_time_years=0.5,
    shelf_life_years=10.0,
    threat_horizon_years=4.5,
    urgency_ratio=2.333,
    risk_level="critical",
    mosca_violation=True,
)

_RA_SHA = RiskAssessment(
    detection_id="det-sha-1",
    migration_time_years=0.5,
    shelf_life_years=5.0,
    threat_horizon_years=15.0,
    urgency_ratio=0.367,
    risk_level="low",
    mosca_violation=False,
)

_RA_AES = RiskAssessment(
    detection_id="det-aes-1",
    migration_time_years=0.0,
    shelf_life_years=0.0,
    threat_horizon_years=0.0,
    urgency_ratio=0.0,
    risk_level="quantum-safe",
    mosca_violation=False,
)

_REC_RSA = Recommendation(
    detection_id="det-rsa-1",
    recommended_algorithm="ML-KEM-768 (Kyber)",
    fips_reference="FIPS 203",
    rationale="NIST-standardized KEM.",
    latency_note="~2x CPU overhead.",
    migration_note="Update key exchange.",
)

_REC_SHA = Recommendation(
    detection_id="det-sha-1",
    recommended_algorithm="SLH-SP-128s (SPHINCS+)",
    fips_reference="FIPS 205",
    rationale="NIST-standardized hash-based signature.",
    latency_note="Larger signatures.",
    migration_note="Update signature verification.",
)

_REC_AES = Recommendation(
    detection_id="det-aes-1",
    recommended_algorithm="AES-256 (no change)",
    fips_reference="FIPS 197",
    rationale="Quantum-safe symmetric cipher.",
    latency_note="",
    migration_note="No migration needed.",
)

_SCAN_RESULT = ScanResult(
    scan_id="scan-test-001",
    target="/home/user/myproject",
    detections=[_DET_RSA, _DET_SHA, _DET_AES],
    risk_assessments=[_RA_RSA, _RA_SHA, _RA_AES],
    recommendations=[_REC_RSA, _REC_SHA, _REC_AES],
    scanned_at="2026-09-08T12:00:00Z",
)

_EMPTY_SCAN_RESULT = ScanResult(
    scan_id="scan-empty",
    target="/empty",
    detections=[],
    risk_assessments=[],
    recommendations=[],
    scanned_at="2026-09-08T12:00:00Z",
)

# ---------------------------------------------------------------------------
# export_cbom tests
# ---------------------------------------------------------------------------


class TestExportCbom:
    """Tests for the CycloneDX 1.6 BOM export function."""

    def test_bom_format_and_spec_version(self) -> None:
        """Top-level BOM format and spec version are correct."""
        result = export_cbom(_SCAN_RESULT)
        assert result["bomFormat"] == "CycloneDX"
        assert result["specVersion"] == "1.6"
        assert result["version"] == 1

    def test_serial_number_format(self) -> None:
        """serialNumber is a valid urn:uuid string."""
        result = export_cbom(_SCAN_RESULT)
        sn = result["serialNumber"]
        assert sn.startswith("urn:uuid:")
        # Strip prefix and validate UUID shape (8-4-4-4-12 hex chars).
        uuid_part = sn[len("urn:uuid:"):]
        sections = uuid_part.split("-")
        assert len(sections) == 5
        assert [len(s) for s in sections] == [8, 4, 4, 4, 12]

    def test_metadata_structure(self) -> None:
        """Metadata contains timestamp, tools, and component."""
        result = export_cbom(_SCAN_RESULT)
        meta = result["metadata"]
        assert meta["timestamp"] == "2026-09-08T12:00:00Z"
        tools = meta["tools"]["components"]
        assert len(tools) == 1
        assert tools[0]["name"] == "ECDAT"
        assert tools[0]["version"] == "0.1.0"
        assert meta["component"]["name"] == "/home/user/myproject"

    def test_components_length_matches_detections(self) -> None:
        """Number of components equals number of detections."""
        result = export_cbom(_SCAN_RESULT)
        assert len(result["components"]) == len(_SCAN_RESULT.detections)

    def test_component_has_risk_level_property(self) -> None:
        """Every component has a populated ecdat:riskLevel property."""
        result = export_cbom(_SCAN_RESULT)
        for comp in result["components"]:
            risk_props = [
                p for p in comp["properties"] if p["name"] == "ecdat:riskLevel"
            ]
            assert len(risk_props) == 1
            assert risk_props[0]["value"] != ""

    def test_component_has_required_properties(self) -> None:
        """Every component has all five ecdat property names."""
        required = {
            "ecdat:quantumVulnerable",
            "ecdat:riskLevel",
            "ecdat:confidence",
            "ecdat:recommendedAlgorithm",
            "ecdat:fipsReference",
        }
        result = export_cbom(_SCAN_RESULT)
        for comp in result["components"]:
            names = {p["name"] for p in comp["properties"]}
            assert required.issubset(names), (
                f"Missing properties: {required - names}"
            )

    def test_component_crypto_properties_for_algorithm(self) -> None:
        """Algorithm detections have cryptoProperties with algorithmProperties."""
        result = export_cbom(_SCAN_RESULT)
        for comp in result["components"]:
            cp = comp["cryptoProperties"]
            assert cp["assetType"] == "algorithm"
            assert "algorithmProperties" in cp

    def test_component_evidence_occurrences(self) -> None:
        """Each component's evidence has correct file_path and line."""
        result = export_cbom(_SCAN_RESULT)
        for comp, det in zip(result["components"], _SCAN_RESULT.detections):
            occs = comp["evidence"]["occurrences"]
            assert len(occs) == 1
            assert occs[0]["location"] == det.file_path
            assert occs[0]["line"] == det.line_number

    def test_quantum_vulnerable_component_properties(self) -> None:
        """Quantum-vulnerable detection has correct property value."""
        result = export_cbom(_SCAN_RESULT)
        rsa_comp = next(
            c for c in result["components"] if c["bom-ref"] == "det-rsa-1"
        )
        qv = next(
            p for p in rsa_comp["properties"] if p["name"] == "ecdat:quantumVulnerable"
        )
        assert qv["value"] == "True"

    def test_primitive_classification(self) -> None:
        """Algorithm families get correct primitive values best-effort."""
        result = export_cbom(_SCAN_RESULT)
        sha_comp = next(
            c for c in result["components"] if c["bom-ref"] == "det-sha-1"
        )
        aes_comp = next(
            c for c in result["components"] if c["bom-ref"] == "det-aes-1"
        )
        rsa_comp = next(
            c for c in result["components"] if c["bom-ref"] == "det-rsa-1"
        )
        assert sha_comp["cryptoProperties"]["algorithmProperties"]["primitive"] == "hash"
        assert aes_comp["cryptoProperties"]["algorithmProperties"]["primitive"] == "block-cipher"
        # "RSA" matches no keyword rule — primitive falls back to None.
        assert rsa_comp["cryptoProperties"]["algorithmProperties"]["primitive"] is None

    def test_parameter_set_identifier_from_key_size(self) -> None:
        """parameterSetIdentifier is str(key_size_bits) when present, else None."""
        result = export_cbom(_SCAN_RESULT)
        rsa_comp = next(
            c for c in result["components"] if c["bom-ref"] == "det-rsa-1"
        )
        alg_props = rsa_comp["cryptoProperties"]["algorithmProperties"]
        assert alg_props["parameterSetIdentifier"] == "2048"

        sha_comp = next(
            c for c in result["components"] if c["bom-ref"] == "det-sha-1"
        )
        sha_alg_props = sha_comp["cryptoProperties"]["algorithmProperties"]
        assert sha_alg_props["parameterSetIdentifier"] is None


# ---------------------------------------------------------------------------
# export_summary tests
# ---------------------------------------------------------------------------


class TestExportSummary:
    """Tests for the frontend-friendly summary export function."""

    def test_total_detections(self) -> None:
        """Total detections matches the scan result."""
        result = export_summary(_SCAN_RESULT)
        assert result["total_detections"] == 3

    def test_quantum_vulnerable_counts(self) -> None:
        """Quantum-vulnerable count and percentage are correct."""
        result = export_summary(_SCAN_RESULT)
        assert result["quantum_vulnerable_count"] == 2
        assert result["quantum_vulnerable_percentage"] == pytest.approx(
            2 / 3 * 100
        )

    def test_risk_level_counts(self) -> None:
        """Risk level counts match the test data."""
        result = export_summary(_SCAN_RESULT)
        rl = result["risk_level_counts"]
        assert rl["critical"] == 1
        assert rl["low"] == 1
        assert rl["quantum-safe"] == 1
        assert rl["high"] == 0
        assert rl["medium"] == 0

    def test_algorithm_family_counts(self) -> None:
        """Algorithm family counts match the test data."""
        result = export_summary(_SCAN_RESULT)
        fc = result["algorithm_family_counts"]
        assert fc["RSA"] == 1
        assert fc["SHA"] == 1
        assert fc["AES"] == 1

    def test_top_5_urgency(self) -> None:
        """Top-5 urgency list has correct length and highest-urgency first."""
        result = export_summary(_SCAN_RESULT)
        top = result["top_5_urgency"]
        assert len(top) == 3  # only 3 detections, less than limit of 5
        assert top[0]["detection_id"] == "det-rsa-1"

    def test_top_5_urgency_sorted_descending(self) -> None:
        """Top-5 urgency entries are sorted by urgency_ratio descending."""
        result = export_summary(_SCAN_RESULT)
        ratios = [item["urgency_ratio"] for item in result["top_5_urgency"]]
        assert ratios == sorted(ratios, reverse=True)

    def test_empty_scan_result(self) -> None:
        """Empty scan result produces zeroed summary with no errors."""
        result = export_summary(_EMPTY_SCAN_RESULT)
        assert result["total_detections"] == 0
        assert result["quantum_vulnerable_count"] == 0
        assert result["quantum_vulnerable_percentage"] == 0.0
        assert result["top_5_urgency"] == []
        assert all(v == 0 for v in result["risk_level_counts"].values())
        assert result["algorithm_family_counts"] == {}
