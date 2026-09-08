"""Mosca's inequality risk engine for ECDAT.

Evaluates post-quantum risk for detected cryptographic artefacts by computing
Mosca's inequality: ``X + Y > Z`` where X is migration time, Y is data
shelf life, and Z is the quantum threat horizon. When the inequality holds
(urgency_ratio >= 1.0), the artefact is at immediate risk.

Public API:
    - :func:`assess_risk` -> compute a :class:`RiskAssessment` for a single
      detection against a signature entry.
"""

from __future__ import annotations

from ecdat_core.models import Detection, RiskAssessment
from ecdat_core.signature_loader import SignatureEntry

# ---------------------------------------------------------------------------
# Sensitive-path keywords for shelf-life heuristic (Y).
# If any of these appear case-insensitively in the file path, the artefact
# is assumed to protect high-sensitivity data with a longer shelf life.
# ---------------------------------------------------------------------------
_SENSITIVE_PATH_KEYWORDS = ("payment", "auth", "pii", "secret", "key")

# ---------------------------------------------------------------------------
# Asset-type → default migration time (X) mapping.
# Different asset types have very different migration complexity: swapping an
# algorithm in a library is fast; rotating certificates or crypto material
# across an enterprise is much slower.
# ---------------------------------------------------------------------------
_MIGRATION_TIME_BY_ASSET: dict[str, float] = {
    "algorithm": 0.5,
    "protocol": 2.0,
    "certificate": 1.0,
    "related-crypto-material": 5.0,
}


def assess_risk(
    detection: Detection,
    signature_entry: SignatureEntry,
    shelf_life_override: float | None = None,
    migration_time_override: float | None = None,
) -> RiskAssessment:
    """Evaluate post-quantum risk for a single detection via Mosca's inequality.

    Mosca's inequality states that a cryptographic artefact is at risk when::

        X + Y > Z

    where:
        - **X** (`migration_time_years`): estimated time to migrate away from
          the artefact to a post-quantum alternative.
        - **Y** (`shelf_life_years`): how long the data protected by the
          artefact must remain confidential.
        - **Z** (`threat_horizon_years`): estimated time before a cryptographically
          relevant quantum computer exists.

    The urgency ratio ``(X + Y) / Z`` quantifies the severity: values >= 1.0
    indicate that migration must already be underway.

    Classically-broken artefacts (MD5, SHA-1, DES, 3DES, RC4) are broken today
    by classical attacks, independent of quantum computing. They always resolve
    to ``risk_level="critical"`` with ``mosca_violation=True`` and an urgency
    ratio floored at 1.0 — this represents a classical break, **not** a
    quantum-specific one, and such artefacts are never reported as
    "quantum-safe". X/Y/Z are still computed via the normal heuristics so the
    numbers remain visible for transparency.

    Args:
        detection: The detected cryptographic artefact to assess.
        signature_entry: The knowledge-base entry for this artefact's family,
            providing the default threat horizon.
        shelf_life_override: Explicit shelf life in years (Y). When ``None``,
            a default is chosen based on file-path heuristics.
        migration_time_override: Explicit migration time in years (X). When
            ``None``, a default is chosen based on asset type.

    Returns:
        A fully populated :class:`RiskAssessment` with consistent risk_level,
        urgency_ratio, and mosca_violation fields.

    Raises:
        pydantic.ValidationError: If the computed fields are internally
            inconsistent (e.g. mosca_violation disagrees with urgency_ratio).
    """
    # ------------------------------------------------------------------
    # 1. Classically-broken — critical, unconditionally.
    #    MD5, SHA-1, DES, 3DES, RC4 are broken *today* by classical
    #    attacks, independent of any quantum computer, so they must never
    #    fall through to the quantum-safe short-circuit below. X/Y/Z are
    #    still computed via the normal heuristics/overrides so the numbers
    #    are visible for transparency, and the naive urgency ratio is
    #    floored at 1.0 so the Pydantic consistency validator
    #    (mosca_violation == urgency_ratio >= 1.0) holds with the forced
    #    critical / mosca_violation=True classification.
    # ------------------------------------------------------------------
    if detection.classically_broken:
        z = _adjusted_threat_horizon(detection, signature_entry)
        if shelf_life_override is not None:
            y = shelf_life_override
        else:
            y = _default_shelf_life(detection.file_path)
        if migration_time_override is not None:
            x = migration_time_override
        else:
            x = _default_migration_time(detection.asset_type)
        naive_urgency_ratio = (x + y) / z
        urgency_ratio = max(naive_urgency_ratio, 1.0)
        return RiskAssessment(
            detection_id=detection.id,
            migration_time_years=x,
            shelf_life_years=y,
            threat_horizon_years=z,
            urgency_ratio=urgency_ratio,
            risk_level="critical",
            mosca_violation=True,
        )

    # ------------------------------------------------------------------
    # 2. Quantum-safe short-circuit — no formula needed. Only reachable
    #    when classically_broken is False (branch 1 above already
    #    returned), so a classically-broken-but-not-quantum-vulnerable
    #    artefact can never be mislabelled "quantum-safe".
    # ------------------------------------------------------------------
    if not detection.quantum_vulnerable:
        return RiskAssessment(
            detection_id=detection.id,
            migration_time_years=0.0,
            shelf_life_years=0.0,
            threat_horizon_years=0.0,
            urgency_ratio=0.0,
            risk_level="quantum-safe",
            mosca_violation=False,
        )

    # ------------------------------------------------------------------
    # Z — Threat horizon (years) with key-size adjustment.
    # ------------------------------------------------------------------
    z = _adjusted_threat_horizon(detection, signature_entry)

    # ------------------------------------------------------------------
    # Y — Shelf life (years).
    # ------------------------------------------------------------------
    if shelf_life_override is not None:
        y = shelf_life_override
    else:
        y = _default_shelf_life(detection.file_path)

    # ------------------------------------------------------------------
    # X — Migration time (years).
    # ------------------------------------------------------------------
    if migration_time_override is not None:
        x = migration_time_override
    else:
        x = _default_migration_time(detection.asset_type)

    # ------------------------------------------------------------------
    # 4. Urgency ratio, risk level, Mosca violation.
    # ------------------------------------------------------------------
    urgency_ratio = (x + y) / z
    risk_level = _classify_risk(urgency_ratio)
    mosca_violation = urgency_ratio >= 1.0

    return RiskAssessment(
        detection_id=detection.id,
        migration_time_years=x,
        shelf_life_years=y,
        threat_horizon_years=z,
        urgency_ratio=urgency_ratio,
        risk_level=risk_level,
        mosca_violation=mosca_violation,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _adjusted_threat_horizon(
    detection: Detection, signature_entry: SignatureEntry
) -> float:
    """Compute the threat horizon (Z) with key-size-based adjustments.

    Smaller keys are vulnerable to brute-force sooner, even before a full
    cryptographically relevant quantum computer materialises — an attacker
    with limited quantum resources could still break them.  Conversely,
    very large classical keys buy extra time.

    Adjustment thresholds (documented here and in the caller's docstring):

    **RSA** (algorithm_family contains "RSA"):
        - key_size <= 1024: scale Z by 0.3  (breakable with near-term QC)
        - key_size < 2048:  scale Z by 0.5  (weakened but not trivially breakable)
        - key_size >= 4096: scale Z by 1.2  (extra breathing room)
        - otherwise:        use default unchanged

    **EC / ECC** (algorithm_family contains "EC"):
        - key_size < 256:   scale Z by 0.5  (below NIST P-256 minimum)

    **DSA** (algorithm_family contains "DSA"):
        - key_size < 2048:  scale Z by 0.5  (below NIST minimum)

    All other families or missing key sizes use the default unchanged.
    """
    z = signature_entry.threat_horizon_years_default
    key_size = detection.key_size_bits
    family_upper = detection.algorithm_family.upper()

    if key_size is not None:
        if "RSA" in family_upper:
            if key_size <= 1024:
                z *= 0.3
            elif key_size < 2048:
                z *= 0.5
            elif key_size >= 4096:
                z *= 1.2
            # 2048 <= key < 4096: no adjustment — use default

        elif "EC" in family_upper:
            if key_size < 256:
                z *= 0.5

        elif "DSA" in family_upper:
            if key_size < 2048:
                z *= 0.5

    return z


def _default_shelf_life(file_path: str) -> float:
    """Choose a default shelf life (Y) based on file-path heuristics.

    Paths containing sensitive keywords (payment, auth, pii, secret, key)
    are assumed to handle data that must remain secret longer.
    """
    path_lower = file_path.lower()
    if any(kw in path_lower for kw in _SENSITIVE_PATH_KEYWORDS):
        return 10.0
    return 5.0


def _default_migration_time(asset_type: str) -> float:
    """Choose a default migration time (X) based on the CycloneDX asset type."""
    return _MIGRATION_TIME_BY_ASSET.get(asset_type, 0.5)


def _classify_risk(urgency_ratio: float) -> str:
    """Classify risk level from the urgency ratio.

    Thresholds:
        - >= 1.0  → critical  (Mosca violated — migration needed now)
        - >= 0.8  → high
        - >= 0.5  → medium
        - <  0.5  → low
    """
    if urgency_ratio >= 1.0:
        return "critical"
    if urgency_ratio >= 0.8:
        return "high"
    if urgency_ratio >= 0.5:
        return "medium"
    return "low"
