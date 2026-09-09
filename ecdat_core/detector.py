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

        # Collect every raw regex match for this signature, then collapse the
        # ones that resolved to the same physical line. A signature entry often
        # carries several pattern strings (import-style, call-site, bare
        # keyword) that can legitimately co-occur on a single line — e.g. a
        # one-line usage that matches both an import pattern and a call pattern,
        # or `\bAES\b` matching inside `AES-256`. Those describe ONE real-world
        # cryptographic usage, so they must yield exactly one Detection.
        raw_matches: list[Detection] = []
        for pattern in patterns:
            compiled = re.compile(pattern)
            for line_index, line in enumerate(lines):
                line_number = line_index + 1
                key_size_bits = _extract_key_size(
                    signature.key_size_pattern, line
                )
                for match in compiled.finditer(line):
                    raw_matches.append(
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
                            classically_broken=signature.classically_broken,
                            confidence=_compute_confidence(match.group(0)),
                            language=language,
                            detection_method="regex",
                        )
                    )

        detections.extend(_dedupe_detections(raw_matches))
    return detections


def _dedupe_detections(detections: list[Detection]) -> list[Detection]:
    """Collapse same-line duplicates within a single signature's matches.

    When several pattern strings of the same signature entry match the same
    physical line (e.g. an import-style pattern and a call-site pattern both
    firing on a one-line usage, or the ``\\bAES\\b`` bare-keyword pattern
    matching inside ``AES-256``), they all describe the same real-world
    cryptographic usage and must be collapsed into a single :class:`Detection`.

    The caller passes matches from a *single* signature for a *single* file, so
    keying on ``line_number`` here is equivalent to the (signature, file_path,
    line_number) identity that defines one cryptographic usage.

    Tie-break rule, applied deterministically per line:
        1. Prefer the highest-confidence match — an exact API call scores 1.0
           vs a looser import/bare-keyword match at 0.6.
        2. If confidences tie, prefer the most specific pattern, i.e. the one
           whose matched text is longest (``hashlib.md5(`` over ``md5(``, or
           ``AES-256`` over a bare ``AES``). A longer match captures a more
           precisely specified construct and better represents the real usage.

    Each non-collapsed line keeps its first-seen position so the overall output
    order stays stable and deterministic.

    Args:
        detections: Raw matches produced by one signature against one file.

    Returns:
        A deduplicated list with at most one :class:`Detection` per line.
    """
    best_by_line: dict[int, Detection] = {}
    first_seen: list[int] = []

    for detection in detections:
        line = detection.line_number
        current = best_by_line.get(line)
        if current is None:
            best_by_line[line] = detection
            first_seen.append(line)
        elif _is_better_match(detection, current):
            best_by_line[line] = detection

    return [best_by_line[line] for line in first_seen]


def _is_better_match(candidate: Detection, current: Detection) -> bool:
    """Report whether *candidate* should replace *current* on the same line.

    Higher confidence wins; on a confidence tie, the more specific pattern's
    longer matched text wins (see :func:`_dedupe_detections`).
    """
    if candidate.confidence != current.confidence:
        return candidate.confidence > current.confidence
    return len(candidate.matched_text) > len(current.matched_text)


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
