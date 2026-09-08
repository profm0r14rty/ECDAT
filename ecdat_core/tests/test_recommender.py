"""Tests for the ECDAT post-quantum recommendation engine.

Validates that :func:`recommend` produces a pass-through recommendation from
the signature's ``pqc_recommendation`` for ordinary algorithms, and emits a
"no migration needed" recommendation for artefacts already using a
NIST-standardized post-quantum algorithm.
"""

from __future__ import annotations

from ecdat_core.models import Detection
from ecdat_core.recommender import recommend
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
            "algorithm": "ML-KEM (FIPS 203)",
            "fips_reference": "FIPS 203",
            "rationale": "RSA is broken by Shor's algorithm; migrate to ML-KEM.",
            "latency_note": "ML-KEM is fast.",
            "migration_note": "Replace RSA key generation with ML-KEM.",
        },
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRecommend:
    def test_rsa_detection_passes_through_pqc_recommendation(self):
        """A quantum-vulnerable RSA detection gets the signature's migration.

        The recommendation is keyed to the detection id and carries the
        signature's FIPS reference (FIPS 203) plus a non-empty rationale.
        """
        det = Detection(**make_detection())
        sig = SignatureEntry(**make_signature_entry())
        result = recommend(det, sig)

        assert result.detection_id == det.id
        assert result.fips_reference == "FIPS 203"
        assert result.recommended_algorithm == "ML-KEM (FIPS 203)"
        assert result.rationale.strip()
        assert result.latency_note == "ML-KEM is fast."
        assert result.migration_note == "Replace RSA key generation with ML-KEM."

    def test_ml_kem_detection_gets_no_migration_needed(self):
        """An ML-KEM (already PQC) detection gets the 'no migration needed' message.

        The recommended algorithm falls back to the detection's algorithm
        family, but the FIPS reference still comes from the signature.
        """
        det = Detection(**make_detection(
            algorithm_family="ML-KEM",
            quantum_vulnerable=False,
        ))
        sig = SignatureEntry(**make_signature_entry(
            name="ML-KEM",
            family="pqc-kem",
            quantum_vulnerable=False,
            threat_horizon_years_default=0.0,
            patterns={"python": ["ML\\-KEM\\b"]},
            key_size_pattern=None,
            pqc_recommendation={
                "algorithm": "ML-KEM (FIPS 203)",
                "fips_reference": "FIPS 203",
                "rationale": "Already NIST-standardized.",
                "latency_note": "Efficient.",
                "migration_note": "No migration required.",
            },
        ))
        result = recommend(det, sig)

        assert result.detection_id == det.id
        assert result.recommended_algorithm == "ML-KEM"
        assert result.fips_reference == "FIPS 203"
        assert result.rationale == (
            "Already using a NIST-standardized post-quantum algorithm; "
            "no migration needed."
        )
        assert result.latency_note == ""
        assert result.migration_note == "Monitor for future FIPS updates."

    def test_md5_detection_gets_sha256_sha3_recommendation(self):
        """A classically-weak MD5 detection still gets a real replacement.

        MD5 is not quantum-vulnerable, but it is not a PQC algorithm either, so
        the signature's recommendation (SHA-256 / SHA-3) is passed through.
        """
        det = Detection(**make_detection(
            algorithm_family="MD5",
            matched_text="hashlib.md5(b'data')",
            quantum_vulnerable=False,
        ))
        sig = SignatureEntry(**make_signature_entry(
            name="MD5",
            family="hash",
            quantum_vulnerable=False,
            threat_horizon_years_default=1.0,
            patterns={"python": ["hashlib\\.md5\\s*\\("]},
            key_size_pattern=None,
            pqc_recommendation={
                "algorithm": "SHA-256 / SHA-3",
                "fips_reference": "N/A (classical collision weakness, not quantum-specific)",
                "rationale": "MD5 has broken collision resistance; use SHA-256 or SHA-3.",
                "latency_note": "Comparable performance.",
                "migration_note": "Replace all MD5 usage with SHA-256 or SHA-3.",
            },
        ))
        result = recommend(det, sig)

        assert result.detection_id == det.id
        assert result.recommended_algorithm == "SHA-256 / SHA-3"
        assert result.rationale.strip()
