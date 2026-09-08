"""Post-quantum recommendation engine for ECDAT.

Produces a :class:`Recommendation` for each detected cryptographic artefact.
For ordinary algorithms the recommendation is a direct pass-through of the
signature's ``pqc_recommendation``. The one special case is an artefact that
*already* uses a NIST-standardized post-quantum algorithm — those get a
"no migration needed" recommendation instead of a migration directive.

Public API:
    - :func:`recommend` -> build a :class:`Recommendation` for a single
      detection against a signature entry.
"""

from __future__ import annotations

from ecdat_core.models import Detection, Recommendation
from ecdat_core.signature_loader import SignatureEntry

# Signature families that are *already* NIST-standardized post-quantum
# schemes. These are quantum-safe, so instead of recommending a migration we
# only note that no migration is required.
_PQC_FAMILIES = frozenset({"pqc-kem", "pqc-signature"})

# Fixed text for the already-quantum-safe recommendation.
_NO_MIGRATION_RATIONALE = (
    "Already using a NIST-standardized post-quantum algorithm; no migration needed."
)
_NO_MIGRATION_MIGRATION_NOTE = "Monitor for future FIPS updates."


def recommend(
    detection: Detection, signature_entry: SignatureEntry
) -> Recommendation:
    """Build a post-quantum migration recommendation for a detection.

    The normal path copies the signature's ``pqc_recommendation`` verbatim
    into a new :class:`Recommendation` keyed to ``detection.id``. The
    exception is an artefact that already uses a NIST-standardized post-quantum
    algorithm (a PQC KEM or signature family that is not quantum-vulnerable) —
    for those, a lightweight "no migration needed" recommendation is returned
    that keeps the signature's FIPS reference but replaces the migration
    guidance with monitoring advice.

    Args:
        detection: The detected cryptographic artefact to recommend for.
        signature_entry: The knowledge-base entry describing this artefact and
            its post-quantum replacement.

    Returns:
        A fully populated :class:`Recommendation`.
    """
    already_pqc = (
        not detection.quantum_vulnerable
        and signature_entry.family in _PQC_FAMILIES
    )
    if already_pqc:
        return Recommendation(
            detection_id=detection.id,
            recommended_algorithm=detection.algorithm_family,
            fips_reference=signature_entry.pqc_recommendation.fips_reference,
            rationale=_NO_MIGRATION_RATIONALE,
            latency_note="",
            migration_note=_NO_MIGRATION_MIGRATION_NOTE,
        )

    rec = signature_entry.pqc_recommendation
    return Recommendation(
        detection_id=detection.id,
        recommended_algorithm=rec.algorithm,
        fips_reference=rec.fips_reference,
        rationale=rec.rationale,
        latency_note=rec.latency_note,
        migration_note=rec.migration_note,
    )
