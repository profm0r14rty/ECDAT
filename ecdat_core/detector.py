"""Regex-based detection engine for ECDAT.

Scans source file content line-by-line against the cryptographic signature
knowledge base and emits :class:`Detection` records for every regex match.

Public API:
    - :func:`detect_language` -> map a file path's extension to an ECDAT
      language key, or ``None`` if the file type is unsupported.
    - :func:`scan_file_content` -> run all language signatures against content
      and return the resulting detections.
"""

from __future__ import annotations

import re

from ecdat_core.models import Detection
from ecdat_core.signature_loader import SignatureEntry, get_signatures_for_language

# Extensions -> ECDAT language key. Case is normalised before lookup.
_EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "javascript",
    ".java": "java",
    ".go": "go",
    ".c": "c_cpp",
    ".cpp": "c_cpp",
    ".h": "c_cpp",
}

# Maximum length of the stored matched_text substring.
MAX_MATCHED_TEXT_LENGTH = 200

# Deterministic confidence values: an exact API call is a very strong signal,
# while a looser import-only or bare-keyword match is weaker.
CONFIDENCE_API_CALL = 1.0
CONFIDENCE_IMPORT_KEYWORD = 0.6

# Matches a call-like invocation in matched text, e.g. ``RSA.generate(`` or
# ``hashlib.md5(`` — an identifier immediately followed by an opening paren.
_API_CALL_RE = re.compile(r"\w+\s*\(")

# Families whose asset type is literally an algorithm. The current knowledge
# base only defines these families; certificate/protocol families are mapped
# defensively in case they are added later.
_ALGORITHM_FAMILIES = frozenset(
    {
        "asymmetric-encryption",
        "signature",
        "hash",
        "symmetric-encryption",
        "pqc-kem",
        "pqc-signature",
    }
)


def detect_language(file_path: str) -> str | None:
    """Map a file path's extension to an ECDAT language key.

    Args:
        file_path: Path to the source file (only the extension is inspected).

    Returns:
        The ECDAT language key (e.g. "python", "javascript", "c_cpp") for a
        supported extension, or ``None`` for an unsupported / missing one so
        callers can skip such files.
    """
    suffix = _extension_of(file_path)
    return _EXTENSION_TO_LANGUAGE.get(suffix)


def _extension_of(file_path: str) -> str:
    """Return the lowercased file extension including the dot.

    Returns an empty string when the path has no extension.
    """
    name = file_path.rsplit("/", 1)[-1]
    dot = name.rfind(".")
    if dot <= 0:  # dot at index 0 means a hidden file such as ".gitignore"
        return ""
    return name[dot:].lower()


def scan_file_content(
    file_path: str, content: str, language: str
) -> list[Detection]:
    """Run the language's signatures against content and collect detections.

    Args:
        file_path: Path to the file being scanned (stored on each detection).
        content: Full source file content as a string.
        language: An ECDAT language key, e.g. "python" or "java".

    Returns:
        list[Detection]: One detection per regex match found, in a
        deterministic order derived from line / pattern ordering.
    """
    detections: list[Detection] = []
    lines = content.split("\n")

    for signature in get_signatures_for_language(language):
        patterns = signature.patterns.get(language, [])
        asset_type = _asset_type_for_family(signature.family)
        for pattern in patterns:
            compiled = re.compile(pattern)
            for line_index, line in enumerate(lines):
                line_number = line_index + 1
                key_size_bits = _extract_key_size(
                    signature.key_size_pattern, line
                )
                for match in compiled.finditer(line):
                    detections.append(
                        Detection(
                            file_path=file_path,
                            line_number=line_number,
                            matched_text=_trim_match(match.group(0)),
                            asset_type=asset_type,
                            algorithm_family=signature.name,
                            key_size_bits=key_size_bits,
                            quantum_vulnerable=_resolve_quantum_vulnerable(
                                signature, key_size_bits
                            ),
                            confidence=_compute_confidence(match.group(0)),
                            language=language,
                            detection_method="regex",
                        )
                    )
    return detections


def _asset_type_for_family(family: str) -> str:
    """Map a signature family to a CycloneDX asset type.

    Algorithm families map to ``algorithm``; certificate and protocol families
    map to their corresponding asset types.
    """
    if family in _ALGORITHM_FAMILIES or "algorithm" in family:
        return "algorithm"
    if "certificate" in family:
        return "certificate"
    if "protocol" in family:
        return "protocol"
    return "related-crypto-material"


def _trim_match(matched_text: str) -> str:
    """Trim matched text to at most :data:`MAX_MATCHED_TEXT_LENGTH` chars."""
    if len(matched_text) <= MAX_MATCHED_TEXT_LENGTH:
        return matched_text
    return matched_text[:MAX_MATCHED_TEXT_LENGTH]


def _extract_key_size(
    key_size_pattern: str | None, line: str
) -> int | None:
    """Extract a key size in bits from a line, or None when not determinable."""
    if not key_size_pattern:
        return None
    match = re.search(key_size_pattern, line)
    if not match:
        return None
    return _digits_from_groups(match)


def _digits_from_groups(match: re.Match[str]) -> int | None:
    """Return the first all-digit capture group as an int, else None."""
    for group in match.groups():
        if group is not None and group.isdigit():
            return int(group)
    # Fall back to the whole match if no group holds a pure number.
    digits = "".join(ch for ch in match.group(0) if ch.isdigit())
    return int(digits) if digits else None


def _compute_confidence(matched_text: str) -> float:
    """Return a deterministic confidence for a matched substring.

    An exact API-call match (an identifier immediately followed by an opening
    parenthesis, e.g. ``RSA.generate(``) is scored 1.0. Looser import-only or
    bare-keyword matches (e.g. ``from ... import RSA`` or a lone ``\bMD5\b``)
    are scored 0.6.
    """
    if _API_CALL_RE.search(matched_text):
        return CONFIDENCE_API_CALL
    return CONFIDENCE_IMPORT_KEYWORD


def _resolve_quantum_vulnerable(
    signature: SignatureEntry, key_size_bits: int | None
) -> bool:
    """Resolve quantum-vulnerability for a single detection.

    Symmetric ciphers with a ``min_quantum_safe_key_bits`` threshold are
    evaluated dynamically per-detection: a key size at or above the threshold
    (e.g. AES-192/256) is quantum-safe, while a smaller extracted size is
    flagged. When no key size could be extracted the signature's static
    ``quantum_vulnerable`` applies unchanged — for AES that is the conservative
    ``True`` default.
    """
    threshold = signature.min_quantum_safe_key_bits
    if threshold is not None and key_size_bits is not None:
        return key_size_bits < threshold
    return signature.quantum_vulnerable
