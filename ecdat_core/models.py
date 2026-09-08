"""Pydantic v2 data models for ECDAT CBOM scanner.

Defines the core domain models: Detection, RiskAssessment, Recommendation,
and ScanResult. These models form the contract for the rest of the system.
"""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, field_validator


class Detection(BaseModel):
    """A single cryptographic artefact discovered during scanning.

    Attributes:
        id: Unique identifier, auto-generated via uuid4 if not provided.
        file_path: Path to the file where the artefact was found.
        line_number: 1-based line number of the match.
        matched_text: The exact text that triggered detection.
        asset_type: CycloneDX-aligned asset classification.
        algorithm_family: Broad algorithm family (e.g. RSA, AES, SHA).
        key_size_bits: Key size in bits, if determinable.
        quantum_vulnerable: Whether the artefact is vulnerable to quantum attacks.
        confidence: Detection confidence score in [0.0, 1.0].
        language: Programming language of the source file.
        detection_method: How the artefact was detected.
    """

    id: str = ""
    file_path: str
    line_number: int
    matched_text: str
    asset_type: Literal["algorithm", "certificate", "protocol", "related-crypto-material"]
    algorithm_family: str
    key_size_bits: int | None = None
    quantum_vulnerable: bool
    confidence: float
    language: str
    detection_method: Literal["regex", "manifest", "certificate-parse"]

    def model_post_init(self, __context: object) -> None:
        """Generate a UUID4 id if one was not provided."""
        if not self.id:
            object.__setattr__(self, "id", str(uuid4()))

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is in the range [0.0, 1.0]."""
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {v}")
        return v


class RiskAssessment(BaseModel):
    """Risk assessment derived from Mosca's inequality.

    Attributes:
        detection_id: Reference to the Detection being assessed.
        migration_time_years: Estimated migration time in years (X).
        shelf_life_years: How long the data must remain secret (Y).
        threat_horizon_years: Quantum threat horizon in years (Z).
        urgency_ratio: (X + Y) / Z — values >= 1.0 indicate immediate risk.
        risk_level: Classified risk severity.
        mosca_violation: Whether Mosca's inequality is violated (X+Y > Z).
    """

    detection_id: str
    migration_time_years: float
    shelf_life_years: float
    threat_horizon_years: float
    urgency_ratio: float
    risk_level: Literal["critical", "high", "medium", "low", "quantum-safe"]
    mosca_violation: bool

    @field_validator("urgency_ratio", mode="after")
    def validate_urgency_ratio(cls, v: float) -> float:
        """Ensure urgency_ratio is non-negative."""
        if v < 0:
            raise ValueError(f"urgency_ratio must be non-negative, got {v}")
        return v

    def model_post_init(self, __context: object) -> None:
        """Check consistency between urgency_ratio and mosca_violation.

        Mosca's inequality states that if X + Y > Z (i.e. urgency_ratio >= 1.0),
        then the artefact is at risk. The mosca_violation flag must be consistent
        with the urgency_ratio.
        """
        expected_violation = self.urgency_ratio >= 1.0
        if self.mosca_violation != expected_violation:
            raise ValueError(
                f"mosca_violation ({self.mosca_violation}) contradicts "
                f"urgency_ratio ({self.urgency_ratio}). "
                f"Expected mosca_violation={expected_violation} "
                f"(urgency_ratio {'>=' if expected_violation else '<'} 1.0)"
            )


class Recommendation(BaseModel):
    """Post-quantum migration recommendation for a detected artefact.

    Attributes:
        detection_id: Reference to the Detection being recommended for.
        recommended_algorithm: NIST-approved post-quantum algorithm.
        fips_reference: FIPS standard reference for the algorithm.
        rationale: Why this algorithm is recommended.
        latency_note: Performance impact advisory.
        migration_note: Migration complexity advisory.
    """

    detection_id: str
    recommended_algorithm: str
    fips_reference: str
    rationale: str
    latency_note: str
    migration_note: str


class ScanResult(BaseModel):
    """Complete result of a CBOM scan operation.

    Attributes:
        scan_id: Unique identifier for this scan.
        target: Path or URL that was scanned.
        detections: All cryptographic artefacts discovered.
        risk_assessments: Risk assessments for each detection.
        recommendations: Migration recommendations for each detection.
        scanned_at: ISO 8601 timestamp of when the scan was performed.
    """

    scan_id: str
    target: str
    detections: list[Detection]
    risk_assessments: list[RiskAssessment]
    recommendations: list[Recommendation]
    scanned_at: str  # ISO timestamp
    files_scanned: int = 0
