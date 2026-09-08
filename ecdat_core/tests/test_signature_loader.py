"""Tests for the ECDAT cryptographic signature knowledge base loader."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from ecdat_core.signature_loader import (
    SUPPORTED_LANGUAGES,
    SignatureEntry,
    get_all_signatures,
    get_signatures_for_language,
)

SIGNATURES_PATH = Path(__file__).resolve().parent.parent / "signatures.json"


@pytest.fixture(scope="module")
def raw_signatures() -> list:
    """Load the raw signatures.json payload as plain JSON."""
    with open(SIGNATURES_PATH, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def entries() -> list[SignatureEntry]:
    """Return all validated SignatureEntry instances."""
    return get_all_signatures()


# ---------------------------------------------------------------------------
# JSON loads without error
# ---------------------------------------------------------------------------


class TestJsonLoads:
    def test_signatures_json_is_valid_json(self, raw_signatures):
        assert isinstance(raw_signatures, list)
        assert len(raw_signatures) > 0

    def test_loader_imports_without_error(self):
        # Re-importing the module exercises the import-time validation path.
        import importlib

        import ecdat_core.signature_loader as sl

        importlib.reload(sl)
        assert callable(sl.get_all_signatures)

    def test_all_entries_parse_as_signature_entries(self, raw_signatures):
        for item in raw_signatures:
            SignatureEntry.model_validate(item)


# ---------------------------------------------------------------------------
# Every entry has a non-empty patterns dict for at least one language
# ---------------------------------------------------------------------------


class TestPatterns:
    def test_every_entry_has_non_empty_patterns(self, entries):
        assert len(entries) > 0
        for entry in entries:
            assert entry.patterns, f"{entry.name} has empty patterns"
            assert isinstance(entry.patterns, dict)

    def test_every_entry_has_at_least_one_supported_language(self, entries):
        for entry in entries:
            overlap = set(entry.patterns.keys()) & set(SUPPORTED_LANGUAGES)
            assert overlap, f"{entry.name} has no supported-language patterns"

    def test_all_pattern_lists_non_empty(self, entries):
        for entry in entries:
            for lang, regexes in entry.patterns.items():
                assert regexes, f"{entry.name}/{lang} has an empty pattern list"
                for regex in regexes:
                    assert isinstance(regex, str) and regex.strip()

    def test_only_supported_language_keys(self, entries):
        for entry in entries:
            unknown = set(entry.patterns.keys()) - set(SUPPORTED_LANGUAGES)
            assert not unknown, f"{entry.name} has unknown languages: {unknown}"


# ---------------------------------------------------------------------------
# Every entry's fips_reference is a non-empty string
# ---------------------------------------------------------------------------


class TestFipsReference:
    def test_every_entry_has_non_empty_fips_reference(self, entries):
        for entry in entries:
            ref = entry.pqc_recommendation.fips_reference
            assert isinstance(ref, str)
            assert ref.strip(), f"{entry.name} has empty fips_reference"


# ---------------------------------------------------------------------------
# Fix Phase 1: classically_broken / min_quantum_safe_key_bits split
# ---------------------------------------------------------------------------


class TestClassicalVsQuantumSplit:
    def test_every_entry_sets_classically_broken_explicitly(self, raw_signatures):
        # No entry may rely on a model default: the JSON payload must carry the
        # flag explicitly so the split is auditable in the knowledge base.
        for item in raw_signatures:
            assert "classically_broken" in item, (
                f"{item['name']} must set classically_broken explicitly"
            )
            assert isinstance(item["classically_broken"], bool)

    def test_classically_broken_flags_correct(self, entries):
        flags = {e.name: e.classically_broken for e in entries}
        # Broken today, independent of quantum computers.
        assert flags["MD5"] is True
        assert flags["SHA-1"] is True
        assert flags["DES"] is True
        assert flags["3DES"] is True
        assert flags["RC4"] is True
        # Everything else is not classically broken (including AES and PQC).
        assert flags["AES"] is False
        assert flags["RSA"] is False
        assert flags["ML-KEM"] is False
        assert flags["ML-DSA"] is False
        assert flags["SLH-DSA"] is False

    def test_aes_has_min_quantum_safe_key_bits_of_192(self, entries):
        aes = next(e for e in entries if e.name == "AES")
        assert aes.min_quantum_safe_key_bits == 192
        # Always classically sound; only quantum (Grover) considerations apply.
        assert aes.classically_broken is False

    def test_aes_python_patterns_match_bare_new_call(self, entries):
        # The AES-128-only entry required a literal "128" in the matched line,
        # so `AES.new(key, AES.MODE_GCM)` with no key size was invisible. The
        # generic AES entry must match a bare, unspecified-key-size usage.
        aes = next(e for e in entries if e.name == "AES")
        line = "cipher = AES.new(key, AES.MODE_GCM)"
        assert any(re.search(pattern, line) for pattern in aes.patterns["python"])
        assert all(
            "128" not in pattern for pattern in aes.patterns["python"]
        )


# ---------------------------------------------------------------------------
# Loader function behaviour
# ---------------------------------------------------------------------------


class TestLoaderFunctions:
    def test_get_all_signatures_returns_everything(self, entries):
        assert get_all_signatures() == entries

    def test_get_all_signatures_returns_copy(self):
        result = get_all_signatures()
        result.clear()
        # Original module state must be unaffected.
        assert len(get_all_signatures()) == len(
            [e for e in __import__("ecdat_core.signature_loader", fromlist=["_SIGNATURES"])._SIGNATURES]
        )

    def test_quantum_vulnerable_flags_present(self, entries):
        flags = {e.name: e.quantum_vulnerable for e in entries}
        # Quantum-vulnerable asymmetric + AES should be flagged.
        assert flags["RSA"] is True
        assert flags["ECDH"] is True
        assert flags["ECDSA"] is True
        assert flags["AES"] is True
        # PQC families should NOT be flagged.
        assert flags["ML-KEM"] is False
        assert flags["ML-DSA"] is False
        assert flags["SLH-DSA"] is False
        # Classically weak (non-quantum) should be False per model.
        assert flags["MD5"] is False

    def test_get_signatures_for_language_filters(self, entries):
        python_entries = get_signatures_for_language("python")
        assert python_entries
        for entry in python_entries:
            assert "python" in entry.patterns

    def test_get_signatures_for_language_unknown_raises(self):
        with pytest.raises(ValueError):
            get_signatures_for_language("rust")

    def test_unsupported_language_enum_rejected(self):
        with pytest.raises(ValidationError):
            SignatureEntry.model_validate(
                {
                    "name": "bogus",
                    "family": "signature",
                    "quantum_vulnerable": True,
                    "classically_broken": False,
                    "threat_horizon_years_default": 10,
                    "patterns": {"rust": ["foo"]},
                    "key_size_pattern": None,
                    "pqc_recommendation": {
                        "algorithm": "x",
                        "fips_reference": "FIPS 203",
                        "rationale": "x",
                        "latency_note": "x",
                        "migration_note": "x",
                    },
                }
            )
