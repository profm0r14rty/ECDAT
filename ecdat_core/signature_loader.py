"""Loader and validation for the ECDAT cryptographic signature knowledge base.

Loads ``signatures.json`` and validates it against the :class:`SignatureEntry`
Pydantic model at import time. A malformed JSON document raises a clear error
immediately, so downstream code can rely on the in-memory signature list being
valid.

Public API:
    - :func:`get_all_signatures` -> list of all signature entries.
    - :func:`get_signatures_for_language` -> entries that define patterns for a
      given language.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Languages supported by the signature knowledge base. The JSON payload uses
# these exact keys for each entry's ``patterns`` mapping.
SUPPORTED_LANGUAGES = frozenset({"python", "javascript", "java", "go", "c_cpp"})

_SIGNATURES_PATH = Path(__file__).with_name("signatures.json")


class PqcRecommendation(BaseModel):
    """Post-quantum migration recommendation attached to a signature entry.

    Attributes:
        algorithm: Recommended NIST post-quantum algorithm name.
        fips_reference: FIPS standard reference (e.g. "FIPS 203"), or "N/A" for
            non-quantum-specific fixes (e.g. classical hash weaknesses).
        rationale: Why this algorithm is the recommended replacement.
        latency_note: Performance impact advisory.
        migration_note: Migration complexity and steps advisory.
    """

    algorithm: str
    fips_reference: str
    rationale: str
    latency_note: str
    migration_note: str

    @field_validator("fips_reference")
    @classmethod
    def fips_reference_non_empty(cls, v: str) -> str:
        """Require fips_reference to be a non-empty string."""
        v = v.strip()
        if not v:
            raise ValueError("fips_reference must be a non-empty string")
        return v


class SignatureEntry(BaseModel):
    """A single detection signature for one algorithm/family.

    Attributes:
        name: Human-readable algorithm name (e.g. "RSA").
        family: Broad algorithm family classification.
        quantum_vulnerable: Whether the algorithm is vulnerable to quantum
            attacks. For symmetric ciphers with a
            ``min_quantum_safe_key_bits`` threshold this is the conservative
            static default used when the extracted key size is unavailable;
            per-detection it should be recomputed from the extracted key size
            (see :data:`min_quantum_safe_key_bits`).
        classically_broken: Whether the algorithm is already broken/deprecated
            today, independent of quantum computing entirely (e.g. MD5, SHA-1,
            DES, 3DES, RC4). Must be set explicitly on every entry — there is
            no default.
        min_quantum_safe_key_bits: Minimum key size (in bits) at which the
            algorithm's post-quantum security is acceptable; only meaningful
            for symmetric ciphers whose ``quantum_vulnerable`` should depend on
            the extracted key size rather than being static. ``None`` elsewhere.
        threat_horizon_years_default: Default Mosca threat horizon (Z) in years.
        patterns: Map of language -> list of regex patterns used to detect this
            algorithm in source code of that language.
        key_size_pattern: Optional regex (with a capture group) used to extract
            key size from matched source; ``None`` when key size is not relevant.
        pqc_recommendation: Post-quantum migration recommendation.
    """

    name: str
    family: Literal[
        "asymmetric-encryption",
        "signature",
        "hash",
        "symmetric-encryption",
        "pqc-kem",
        "pqc-signature",
    ]
    quantum_vulnerable: bool
    classically_broken: bool
    min_quantum_safe_key_bits: int | None = None
    threat_horizon_years_default: float = Field(ge=0)
    patterns: dict[str, list[str]]
    key_size_pattern: str | None = None
    pqc_recommendation: PqcRecommendation

    @field_validator("name")
    @classmethod
    def name_non_empty(cls, v: str) -> str:
        """Require name to be a non-empty string."""
        v = v.strip()
        if not v:
            raise ValueError("name must be a non-empty string")
        return v

    @field_validator("patterns")
    @classmethod
    def patterns_have_at_least_one_language(
        cls, v: dict[str, list[str]]
    ) -> dict[str, list[str]]:
        """Require patterns for at least one supported language.

        Each supported language key must map to a non-empty list of non-empty
        regex strings. Unknown language keys are rejected.
        """
        if not v:
            raise ValueError("patterns must contain at least one language")

        unknown = set(v.keys()) - SUPPORTED_LANGUAGES
        if unknown:
            raise ValueError(
                f"patterns contains unsupported language(s): {sorted(unknown)}"
            )

        for lang, regexes in v.items():
            if not regexes:
                raise ValueError(f"patterns[{lang!r}] must be a non-empty list")
            if any(not isinstance(r, str) or not r.strip() for r in regexes):
                raise ValueError(f"patterns[{lang!r}] contains an empty pattern")

        return v


def _load_signatures() -> list[SignatureEntry]:
    """Load and validate ``signatures.json`` into SignatureEntry instances."""
    try:
        raw = json.loads(_SIGNATURES_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Cannot find cryptographic signature knowledge base at "
            f"{_SIGNATURES_PATH}. Ensure ecdat_core/signatures.json is present."
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"signatures.json is not valid JSON: {exc.msg} "
            f"(line {exc.lineno}, column {exc.colno})"
        ) from exc

    if not isinstance(raw, list):
        raise ValueError(
            f"signatures.json must be a JSON array of entries, "
            f"got {type(raw).__name__}"
        )

    entries: list[SignatureEntry] = []
    for idx, item in enumerate(raw):
        try:
            entries.append(SignatureEntry.model_validate(item))
        except Exception as exc:  # noqa: BLE001 - surface any validation failure
            raise ValueError(
                f"signatures.json entry #{idx} failed validation: {exc}"
            ) from exc

    return entries


# Load and validate once at import time. Any malformed entry aborts the import
# with a descriptive error rather than surfacing later during a scan.
_SIGNATURES: list[SignatureEntry] = _load_signatures()


def get_all_signatures() -> list[SignatureEntry]:
    """Return all validated signature entries from the knowledge base.

    Returns:
        list[SignatureEntry]: Every signature entry defined in signatures.json.
    """
    return list(_SIGNATURES)


def get_signatures_for_language(lang: str) -> list[SignatureEntry]:
    """Return signature entries that define patterns for the given language.

    Args:
        lang: A supported language name (e.g. "python", "go").

    Returns:
        list[SignatureEntry]: Entries with at least one detection pattern for
        the requested language.

    Raises:
        ValueError: If ``lang`` is not a supported language.
    """
    if lang not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Unsupported language {lang!r}; expected one of "
            f"{sorted(SUPPORTED_LANGUAGES)}"
        )
    return [entry for entry in _SIGNATURES if lang in entry.patterns]
