"""Tests for ECDAT pydantic data models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ecdat_core.models import (
    Detection,
    Recommendation,
    RiskAssessment,
    ScanResult,
)


def make_detection(**overrides) -> dict:
    """Build a valid Detection kwargs dict with sensible defaults."""
    defaults = {
        "file_path": "src/main.py",
        "line_number": 42,
        "matched_text": "RSA.generate(2048)",
        "asset_type": "algorithm",
        "algorithm_family": "RSA",
        "key_size_bits": 2048,
        "quantum_vulnerable": True,
        "confidence": 0.95,
        "language": "python",
        "detection_method": "regex",
    }
    defaults.update(overrides)
    return defaults


def make_risk_assessment(**overrides) -> dict:
    """Build a valid RiskAssessment kwargs dict with sensible defaults."""
    defaults = {
        "detection_id": "det-1",
        "migration_time_years": 5.0,
        "shelf_life_years": 10.0,
        "threat_horizon_years": 15.0,
        "urgency_ratio": 1.0,
        "risk_level": "critical",
        "mosca_violation": True,
    }
    defaults.update(overrides)
    return defaults


def make_recommendation(**overrides) -> dict:
    """Build a valid Recommendation kwargs dict with sensible defaults."""
    defaults = {
        "detection_id": "det-1",
        "recommended_algorithm": "ML-KEM-768 (Kyber)",
        "fips_reference": "FIPS 203",
        "rationale": "Key encapsulation replacement for RSA-OAEP.",
        "latency_note": "~2x CPU overhead vs ECDH on typical hardware.",
        "migration_note": "Update key exchange protocol and libraries.",
    }
    defaults.update(overrides)
    return defaults


def make_scan_result(**overrides) -> dict:
    """Build a valid ScanResult kwargs dict with sensible defaults."""
    defaults = {
        "scan_id": "scan-1",
        "target": "/path/to/project",
        "detections": [Detection(**make_detection())],
        "risk_assessments": [RiskAssessment(**make_risk_assessment())],
        "recommendations": [Recommendation(**make_recommendation())],
        "scanned_at": "2026-09-08T12:00:00Z",
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


class TestDetection:
    def test_valid_construction(self):
        det = Detection(**make_detection())
        assert det.id  # auto-generated uuid
        assert det.file_path == "src/main.py"
        assert det.line_number == 42
        assert det.matched_text == "RSA.generate(2048)"
        assert det.asset_type == "algorithm"
        assert det.algorithm_family == "RSA"
        assert det.key_size_bits == 2048
        assert det.quantum_vulnerable is True
        assert det.confidence == 0.95
        assert det.language == "python"
        assert det.detection_method == "regex"

    def test_id_generation_when_not_provided(self):
        det1 = Detection(**make_detection())
        det2 = Detection(**make_detection())
        assert det1.id != det2.id  # uuid4 generates unique ids

    def test_id_respected_when_provided(self):
        det = Detection(**make_detection(id="my-custom-id"))
        assert det.id == "my-custom-id"

    def test_key_size_optional(self):
        det = Detection(**make_detection(key_size_bits=None))
        assert det.key_size_bits is None

    def test_confidence_low_boundary(self):
        Detection(**make_detection(confidence=0.0))

    def test_confidence_high_boundary(self):
        Detection(**make_detection(confidence=1.0))

    def test_confidence_out_of_range_high(self):
        with pytest.raises(ValidationError):
            Detection(**make_detection(confidence=1.1))

    def test_confidence_out_of_range_low(self):
        with pytest.raises(ValidationError):
            Detection(**make_detection(confidence=-0.1))

    def test_invalid_asset_type_rejected(self):
        with pytest.raises(ValidationError):
            Detection(**make_detection(asset_type="bogus"))

    def test_invalid_detection_method_rejected(self):
        with pytest.raises(ValidationError):
            Detection(**make_detection(detection_method="guess"))


# ---------------------------------------------------------------------------
# RiskAssessment
# ---------------------------------------------------------------------------


class TestRiskAssessment:
    def test_valid_construction(self):
        ra = RiskAssessment(**make_risk_assessment())
        assert ra.detection_id == "det-1"
        assert ra.migration_time_years == 5.0
        assert ra.shelf_life_years == 10.0
        assert ra.threat_horizon_years == 15.0
        assert ra.urgency_ratio == 1.0
        assert ra.risk_level == "critical"
        assert ra.mosca_violation is True

    def test_mosca_violation_true_with_ratio_geq_1(self):
        # urgency_ratio == 1.0 -> violation expected
        ra = RiskAssessment(**make_risk_assessment())
        assert ra.mosca_violation is True

    def test_mosca_violation_true_with_ratio_gt_1(self):
        ra = RiskAssessment(
            **make_risk_assessment(urgency_ratio=1.5, mosca_violation=True)
        )
        assert ra.urgency_ratio == 1.5
        assert ra.mosca_violation is True

    def test_mosca_violation_false_with_ratio_lt_1(self):
        ra = RiskAssessment(
            **make_risk_assessment(urgency_ratio=0.5, mosca_violation=False)
        )
        assert ra.urgency_ratio == 0.5
        assert ra.mosca_violation is False

    def test_inconsistent_high_ratio_with_no_violation(self):
        # urgency_ratio >= 1.0 but mosca_violation False -> contradiction
        with pytest.raises(ValidationError):
            RiskAssessment(**make_risk_assessment(mosca_violation=False))

    def test_inconsistent_low_ratio_with_violation(self):
        # urgency_ratio < 1.0 but mosca_violation True -> contradiction
        with pytest.raises(ValidationError):
            RiskAssessment(
                **make_risk_assessment(urgency_ratio=0.3, mosca_violation=True)
            )

    def test_negative_urgency_ratio_rejected(self):
        with pytest.raises(ValidationError):
            RiskAssessment(
                **make_risk_assessment(urgency_ratio=-1.0, mosca_violation=False)
            )

    def test_invalid_risk_level_rejected(self):
        with pytest.raises(ValidationError):
            RiskAssessment(**make_risk_assessment(risk_level="extreme"))


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------


class TestRecommendation:
    def test_valid_construction(self):
        rec = Recommendation(**make_recommendation())
        assert rec.detection_id == "det-1"
        assert rec.recommended_algorithm == "ML-KEM-768 (Kyber)"
        assert rec.fips_reference == "FIPS 203"
        assert rec.rationale
        assert rec.latency_note
        assert rec.migration_note

    def test_all_fields_required(self):
        with pytest.raises(ValidationError):
            Recommendation(
                detection_id="det-1",
                recommended_algorithm="ML-KEM-768",
                fips_reference="FIPS 203",
                rationale="x",
                latency_note="y",
                # migration_note missing
            )


# ---------------------------------------------------------------------------
# ScanResult
# ---------------------------------------------------------------------------


class TestScanResult:
    def test_valid_construction(self):
        result = ScanResult(**make_scan_result())
        assert result.scan_id == "scan-1"
        assert result.target == "/path/to/project"
        assert len(result.detections) == 1
        assert len(result.risk_assessments) == 1
        assert len(result.recommendations) == 1
        assert result.scanned_at == "2026-09-08T12:00:00Z"

    def test_empty_lists_allowed(self):
        result = ScanResult(
            **make_scan_result(detections=[], risk_assessments=[], recommendations=[])
        )
        assert result.detections == []
        assert result.risk_assessments == []
        assert result.recommendations == []
