"""Tests for the ECDAT regex-based detection engine.

Uses inline string fixtures passed directly to :func:`scan_file_content`, so
no files need to be written to disk.
"""

from __future__ import annotations

import pytest

from ecdat_core.detector import detect_language, scan_file_content


# ---------------------------------------------------------------------------
# detect_language extension mapping
# ---------------------------------------------------------------------------


class TestDetectLanguage:
    def test_supported_extensions(self):
        assert detect_language("a.py") == "python"
        assert detect_language("a.ts") == "javascript"
        assert detect_language("a.js") == "javascript"
        assert detect_language("a.java") == "java"
        assert detect_language("a.go") == "go"
        assert detect_language("a.c") == "c_cpp"
        assert detect_language("a.cpp") == "c_cpp"
        assert detect_language("a.h") == "c_cpp"

    def test_case_insensitive_extensions(self):
        assert detect_language("A.PY") == "python"
        assert detect_language("a.CPP") == "c_cpp"

    def test_unsupported_extension_returns_none(self):
        assert detect_language("a.txt") is None
        assert detect_language("a.md") is None

    def test_no_extension_returns_none(self):
        assert detect_language("Makefile") is None
        assert detect_language("") is None


# ---------------------------------------------------------------------------
# Detection output shape
# ---------------------------------------------------------------------------


class TestDetectionShape:
    def test_asset_type_and_method(self):
        snippet = "key = RSA.generate(2048)"
        [detection] = scan_file_content("sample.py", snippet, "python")
        assert detection.asset_type == "algorithm"
        assert detection.detection_method == "regex"
        assert detection.language == "python"
        assert detection.file_path == "sample.py"

    def test_matched_text_trimmed_to_200_chars(self):
        long_call = "x" * 400
        snippet = f"key = RSA.generate({long_call})"
        [detection] = scan_file_content("sample.py", snippet, "python")
        assert len(detection.matched_text) <= 200


# ---------------------------------------------------------------------------
# Python RSA via Crypto.PublicKey
# ---------------------------------------------------------------------------


class TestPythonRSA:
    SNIPPET = (
        "from Crypto.PublicKey import RSA\n"
        "key = RSA.generate(2048)\n"
    )
    IMPORT_SNIPPET = (
        "from cryptography.hazmat.primitives.asymmetric import RSA\n"
        "key = RSA.generate(2048)\n"
    )

    def test_api_call_detection(self):
        detections = scan_file_content("sample.py", self.SNIPPET, "python")
        call = next(d for d in detections if d.line_number == 2)
        assert call.algorithm_family == "RSA"
        assert call.quantum_vulnerable is True
        assert call.line_number == 2
        assert call.key_size_bits == 2048
        assert call.confidence == 1.0

    def test_import_detection_lower_confidence(self):
        # The KB's Python import pattern matches the cryptography-style import
        # (`from cryptography.hazmat... import ...RSA`), not the Crypto-style
        # import, so use IMPORT_SNIPPET to exercise the 0.6 confidence path.
        detections = scan_file_content("sample.py", self.IMPORT_SNIPPET, "python")
        import_match = next(d for d in detections if d.line_number == 1)
        assert import_match.algorithm_family == "RSA"
        assert import_match.quantum_vulnerable is True
        assert import_match.line_number == 1
        assert import_match.confidence == 0.6


# ---------------------------------------------------------------------------
# Java RSA via KeyPairGenerator
# ---------------------------------------------------------------------------


class TestJavaRSA:
    SNIPPET = (
        'KeyPairGenerator keyGen = KeyPairGenerator.getInstance("RSA");\n'
        "keyGen.initialize(2048);\n"
    )

    def test_rsa_detection(self):
        detections = scan_file_content("sample.java", self.SNIPPET, "java")
        call = next(d for d in detections if d.line_number == 1)
        assert call.algorithm_family == "RSA"
        assert call.quantum_vulnerable is True
        assert call.line_number == 1
        assert call.confidence == 1.0
        # The RSA key_size_pattern targets Python/C/Go call forms, not the
        # Java KeyPairGenerator line, so no key size is extractable here.
        assert call.key_size_bits is None


# ---------------------------------------------------------------------------
# Python hashlib.md5
# ---------------------------------------------------------------------------


class TestPythonMd5:
    SNIPPET = (
        "import hashlib\n"
        "digest = hashlib.md5(data).hexdigest()\n"
    )

    def test_md5_detection_not_quantum_vulnerable(self):
        detections = scan_file_content("sample.py", self.SNIPPET, "python")
        line_two = [d for d in detections if d.line_number == 2]
        # Both the hashlib.md5( call and the generic md5( pattern match.
        assert line_two
        for detection in line_two:
            assert detection.algorithm_family == "MD5"
            # MD5 is classically weak, but NOT quantum-vulnerable.
            assert detection.quantum_vulnerable is False
            assert detection.line_number == 2
            assert detection.confidence == 1.0


# ---------------------------------------------------------------------------
# Python AES — generic key size matching
# ---------------------------------------------------------------------------


class TestPythonAes:
    SNIPPET = (
        "from Crypto.Cipher import AES\n"
        "cipher = AES.new(key, AES.MODE_GCM)\n"
    )

    def test_bare_aes_new_matches_conservative_default(self):
        # Fix Phase 1: the generic AES entry matches AES.new() regardless of
        # key size — the old AES-128-only entry required a literal "128" and
        # missed this line entirely. With no key size present, the static
        # conservative default (quantum_vulnerable=True) applies.
        detections = scan_file_content("sample.py", self.SNIPPET, "python")
        assert detections
        call = next(d for d in detections if d.line_number == 2)
        assert call.algorithm_family == "AES"
        assert call.quantum_vulnerable is True
        assert call.key_size_bits is None
        assert call.confidence == 1.0

    def test_labeled_aes256_resolves_quantum_safe(self):
        # When the matched line carries an extractable key size, the
        # min_quantum_safe_key_bits threshold (192) applies dynamically:
        # AES-256 is above it and must NOT be flagged quantum-vulnerable.
        snippet = (
            "from Crypto.Cipher import AES\n"
            "cipher = AES.new(key, AES.MODE_GCM)  # AES-256\n"
        )
        detections = scan_file_content("sample.py", snippet, "python")
        call = next(d for d in detections if d.line_number == 2)
        assert call.key_size_bits == 256
        assert call.quantum_vulnerable is False
