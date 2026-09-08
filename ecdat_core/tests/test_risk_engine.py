"""Tests for the ECDAT Mosca's algorithm risk engine.

Validates that :func:`assess_risk` correctly computes urgency ratios,
classifies risk levels, and produces outputs consistent with the Phase 1
:class:`RiskAssessment` Pydantic validators.
"""

from __future__ import annotations

import pytest

from ecdat_core.models import Detection
from ecdat_core.risk_engine import assess_risk
from ecdat_core.signature_loader import SignatureEntry


# ---------------------------------------------------------------------------
# Fixture factories
# ---------------------------------------------------------------------------


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


def make_signature_entry(**overrides) -> dict:
    """Build a valid SignatureEntry kwargs dict with sensible defaults."""
    defaults = {
        "name": "RSA",
        "family": "asymmetric-encryption",
        "quantum_vulnerable": True,
        "classically_broken": False,
        "threat_horizon_years_default": 15.0,
        "patterns": {"python": ["RSA\\.generate\\((?P<size>\\d+)\\)"]},
        "key_size_pattern": r"generate\((?P<size>\d+)\)",
        "pqc_recommendation": {
            "algorithm": "ML-KEM-768 (Kyber)",
            "fips_reference": "FIPS 203",
            "rationale": "NIST-standardized KEM replacement.",
            "latency_note": "~2x CPU overhead.",
            "migration_note": "Update key exchange.",
        },
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAssessRisk:
    def test_quantum_safe_short_circuits(self):
        """Quantum-safe detections return zeroed risk with no formula evaluation."""
        det = Detection(**make_detection(quantum_vulnerable=False))
        sig = SignatureEntry(**make_signature_entry())
        result = assess_risk(det, sig)

        assert result.risk_level == "quantum-safe"
        assert result.mosca_violation is False
        assert result.urgency_ratio == 0.0
        assert result.migration_time_years == 0.0
        assert result.shelf_life_years == 0.0
        assert result.threat_horizon_years == 0.0
        assert result.detection_id == det.id

    def test_classically_broken_is_critical_not_quantum_safe(self):
        """A classically-broken but not quantum-vulnerable artefact (MD5-like)
        resolves to critical / mosca_violation=True, never "quantum-safe".

        X/Y/Z are still computed via the normal heuristics for transparency,
        but the naive urgency ratio is floored at 1.0. With a 20-year threat
        horizon the naive ratio is (0.5 + 5.0) / 20.0 = 0.275, which must be
        floored to exactly 1.0 — satisfying the Pydantic consistency
        validator (mosca_violation == urgency_ratio >= 1.0).
        """
        det = Detection(**make_detection(
            algorithm_family="MD5",
            matched_text="hashlib.md5(b'data')",
            quantum_vulnerable=False,
            classically_broken=True,
        ))
        sig = SignatureEntry(**make_signature_entry(
            name="MD5",
            family="hash",
            quantum_vulnerable=False,
            classically_broken=True,
            threat_horizon_years_default=20.0,
            patterns={"python": ["hashlib\\.md5\\s*\\("]},
            key_size_pattern=None,
        ))
        result = assess_risk(det, sig)

        assert result.risk_level == "critical"
        assert result.mosca_violation is True
        assert result.urgency_ratio >= 1.0
        assert result.urgency_ratio == pytest.approx(1.0)
        assert result.migration_time_years == 0.5
        assert result.shelf_life_years == 5.0
        assert result.threat_horizon_years == pytest.approx(20.0)

    def test_genuinely_quantum_safe_still_short_circuits(self):
        """A genuinely quantum-safe detection (classically_broken=False,
        quantum_vulnerable=False — e.g. AES-256) still short-circuits to
        "quantum-safe" with a zeroed Mosca formula."""
        det = Detection(**make_detection(
            algorithm_family="AES",
            matched_text="AES.new(key, AES.MODE_GCM)",
            key_size_bits=256,
            quantum_vulnerable=False,
            classically_broken=False,
        ))
        sig = SignatureEntry(**make_signature_entry(
            name="AES",
            family="symmetric-encryption",
            quantum_vulnerable=False,
            classically_broken=False,
            threat_horizon_years_default=15.0,
            patterns={"python": ["AES\\.new\\s*\\("]},
            key_size_pattern=None,
        ))
        result = assess_risk(det, sig)

        assert result.risk_level == "quantum-safe"
        assert result.mosca_violation is False
        assert result.urgency_ratio == 0.0
        assert result.migration_time_years == 0.0
        assert result.shelf_life_years == 0.0
        assert result.threat_horizon_years == 0.0

    def test_critical_rsa_1024_in_auth_path(self):
        """RSA-1024 in an auth path produces critical risk.

        Expected math:
            Z = 15.0 * 0.3 = 4.5  (RSA < 1024 → scale 0.3)
            Y = 10.0               (path contains 'auth')
            X = 0.5                (asset_type == 'algorithm')
            urgency = (0.5 + 10.0) / 4.5 ≈ 2.333
        """
        det = Detection(**make_detection(
            key_size_bits=1024,
            file_path="src/auth/service.py",
        ))
        sig = SignatureEntry(**make_signature_entry(threat_horizon_years_default=15.0))
        result = assess_risk(det, sig)

        assert result.risk_level == "critical"
        assert result.mosca_violation is True
        assert result.urgency_ratio >= 1.0
        assert result.threat_horizon_years == pytest.approx(4.5)
        assert result.shelf_life_years == 10.0
        assert result.migration_time_years == 0.5
        assert result.urgency_ratio == pytest.approx(10.5 / 4.5)

    def test_low_risk_large_key_non_sensitive(self):
        """Large key in non-sensitive path produces low risk.

        Expected math:
            Z = 15.0 * 1.2 = 18.0  (RSA >= 4096 → scale 1.2)
            Y = 5.0                 (non-sensitive path)
            X = 0.5                 (asset_type == 'algorithm')
            urgency = (0.5 + 5.0) / 18.0 ≈ 0.306
        """
        det = Detection(**make_detection(
            key_size_bits=4096,
            file_path="src/utils/helper.py",
        ))
        sig = SignatureEntry(**make_signature_entry(threat_horizon_years_default=15.0))
        result = assess_risk(det, sig)

        assert result.risk_level == "low"
        assert result.mosca_violation is False
        assert result.urgency_ratio < 1.0
        assert result.threat_horizon_years == pytest.approx(18.0)
        assert result.shelf_life_years == 5.0
        assert result.migration_time_years == 0.5
        assert result.urgency_ratio == pytest.approx(5.5 / 18.0)

    def test_consistency_with_risk_assessment_validator(self):
        """Multiple risk levels are internally consistent with Pydantic validators.

        The RiskAssessment model enforces that mosca_violation matches
        urgency_ratio >= 1.0. If our computed fields are inconsistent,
        model construction will raise ValidationError.
        """
        cases = [
            # (key_size, asset_type, path)
            (1024, "algorithm", "src/auth/login.py"),       # critical
            (2048, "algorithm", "src/main.py"),              # medium or low
            (4096, "algorithm", "src/utils/data.py"),        # low
            (512, "protocol", "src/payment/gateway.py"),     # protocol + sensitive
        ]
        for key_bits, asset_type, path in cases:
            det = Detection(**make_detection(
                key_size_bits=key_bits,
                asset_type=asset_type,
                file_path=path,
            ))
            sig = SignatureEntry(**make_signature_entry())
            # If the model validator fails, this will raise ValidationError
            result = assess_risk(det, sig)

            # Verify internal consistency
            assert result.mosca_violation == (result.urgency_ratio >= 1.0)
            if result.urgency_ratio >= 1.0:
                assert result.risk_level == "critical"
            elif result.urgency_ratio >= 0.8:
                assert result.risk_level == "high"
            elif result.urgency_ratio >= 0.5:
                assert result.risk_level == "medium"
            else:
                assert result.risk_level == "low"

    def test_overrides_take_precedence(self):
        """Explicit shelf_life and migration_time overrides override defaults.

        Default path 'src/auth/service.py' would yield Y=10.0.
        Default asset_type 'algorithm' would yield X=0.5.
        Overrides: Y=20.0, X=3.0.
        Z = 15.0 (no key_size adjustment for 2048).
        urgency = (3.0 + 20.0) / 15.0 ≈ 1.533
        """
        det = Detection(**make_detection(
            file_path="src/auth/service.py",
            asset_type="algorithm",
        ))
        sig = SignatureEntry(**make_signature_entry())
        result = assess_risk(det, sig, shelf_life_override=20.0, migration_time_override=3.0)

        assert result.shelf_life_years == 20.0
        assert result.migration_time_years == 3.0
        assert result.threat_horizon_years == pytest.approx(15.0)
        assert result.urgency_ratio == pytest.approx(23.0 / 15.0)
        assert result.risk_level == "critical"
        assert result.mosca_violation is True
