"""SQLAlchemy 2.0 ORM models for the ECDAT CBOM scanner backend.

ORM schema (SQLAlchemy 2.0 typed Mapped[...] style, UUID primary keys as strings):

ScanRun: id, target (str), source_type (enum: git_url, local_path), status
      (enum: queued, running, done, failed), created_at (datetime),
      completed_at (datetime, nullable), files_scanned (int, nullable),
      error_message (str, nullable)

DetectionRow: id, scan_id (FK -> ScanRun.id), file_path, line_number,
      matched_text, asset_type, algorithm_family, key_size_bits (nullable),
      quantum_vulnerable (bool), classically_broken (bool), confidence (float),
      language, detection_method

RiskAssessmentRow: id, detection_id (FK -> DetectionRow.id, unique),
      migration_time_years, shelf_life_years, threat_horizon_years,
      urgency_ratio, risk_level, mosca_violation

RecommendationRow: id, detection_id (FK -> DetectionRow.id, unique),
      recommended_algorithm, fips_reference, rationale, latency_note,
      migration_note
"""

from __future__ import annotations

import enum
import uuid as _uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base


def _uuid_str() -> str:
    """Return a UUID hex string for use as a primary key."""
    return _uuid.uuid4().hex


class SourceType(str, enum.Enum):
    git_url = "git_url"
    local_path = "local_path"


class ScanStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class DetectionAssetType(str, enum.Enum):
    algorithm = "algorithm"
    certificate = "certificate"
    protocol = "protocol"
    related_crypto_material = "related-crypto-material"


class RiskLevel(str, enum.Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    quantum_safe = "quantum-safe"


# ---------------------------------------------------------------------------
# ScanRun
# ---------------------------------------------------------------------------


class ScanRun(Base):
    """ORM model for a scan run."""

    __tablename__ = "scan_runs"

    id: Mapped[str] = mapped_column(
        primary_key=True, default=_uuid_str, unique=True
    )
    target: Mapped[str]
    source_type: Mapped[SourceType] = mapped_column(SQLEnum(SourceType))
    status: Mapped[ScanStatus] = mapped_column(SQLEnum(ScanStatus))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    files_scanned: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    detections: Mapped[list["DetectionRow"]] = relationship(back_populates="scan")


# ---------------------------------------------------------------------------
# DetectionRow
# ---------------------------------------------------------------------------


class DetectionRow(Base):
    """ORM model for a cryptographic detection found during a scan."""

    __tablename__ = "detection_rows"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid_str, unique=True)
    scan_id: Mapped[str] = mapped_column(
        ForeignKey("scan_runs.id", ondelete="CASCADE"), nullable=False
    )
    file_path: Mapped[str]
    line_number: Mapped[int]
    matched_text: Mapped[str]
    asset_type: Mapped[DetectionAssetType]
    algorithm_family: Mapped[str]
    key_size_bits: Mapped[int | None] = mapped_column(nullable=True)
    quantum_vulnerable: Mapped[bool]
    classically_broken: Mapped[bool] = mapped_column(default=False)
    confidence: Mapped[float]
    language: Mapped[str]
    detection_method: Mapped[str]

    scan: Mapped["ScanRun"] = relationship(back_populates="detections")


# ---------------------------------------------------------------------------
# RiskAssessmentRow
# ---------------------------------------------------------------------------


class RiskAssessmentRow(Base):
    """ORM model for Mosca's inequality risk assessment."""

    __tablename__ = "risk_assessments"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid_str, unique=True)
    detection_id: Mapped[str] = mapped_column(
        ForeignKey("detection_rows.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    migration_time_years: Mapped[float]
    shelf_life_years: Mapped[float]
    threat_horizon_years: Mapped[float]
    urgency_ratio: Mapped[float]
    risk_level: Mapped[RiskLevel]
    mosca_violation: Mapped[bool]


# ---------------------------------------------------------------------------
# RecommendationRow
# ---------------------------------------------------------------------------


class RecommendationRow(Base):
    """ORM model for PQC migration recommendation."""

    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid_str, unique=True)
    detection_id: Mapped[str] = mapped_column(
        ForeignKey("detection_rows.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    recommended_algorithm: Mapped[str]
    fips_reference: Mapped[str]
    rationale: Mapped[str]
    latency_note: Mapped[str]
    migration_note: Mapped[str]

    detection: Mapped["DetectionRow"] = relationship(back_populates="recommendations")