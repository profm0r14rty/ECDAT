"""Initial migration for ECDAT backend.

Phase 14 rewrite: the original script was never executable — it lacked the
mandatory alembic ``revision``/``down_revision`` attrs (so alembic treated the
tree as empty and ``upgrade head`` no-op'd), emitted PostgreSQL-invalid
``CREATE TYPE IF NOT EXISTS``, and passed the type *name* as the
``sa.Enum`` *value* list. Enum value sets below match ``models_orm`` exactly.
"""

from alembic import op
import sqlalchemy as sa

revision = "initial"
down_revision = None


def upgrade() -> None:
    # --- scan_runs ---
    op.create_table(
        "scan_runs",
        sa.Column("id", sa.String, primary_key=True, nullable=False),
        sa.Column("target", sa.String, nullable=False),
        sa.Column(
            "source_type", sa.Enum("git_url", "local_path", name="source_type"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("queued", "running", "done", "failed", name="scan_status"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("files_scanned", sa.Integer, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
    )

    # --- detection_rows ---
    op.create_table(
        "detection_rows",
        sa.Column("id", sa.String, primary_key=True, nullable=False),
        sa.Column(
            "scan_id", sa.String, sa.ForeignKey("scan_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_path", sa.String, nullable=False),
        sa.Column("line_number", sa.Integer, nullable=False),
        sa.Column("matched_text", sa.String, nullable=False),
        sa.Column(
            "asset_type",
            sa.Enum(
                "algorithm", "certificate", "protocol", "related-crypto-material",
                name="detection_asset_type",
            ),
            nullable=False,
        ),
        sa.Column("algorithm_family", sa.String, nullable=False),
        sa.Column("key_size_bits", sa.Integer, nullable=True),
        sa.Column("quantum_vulnerable", sa.Boolean, nullable=False),
        sa.Column(
            "classically_broken", sa.Boolean, nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("language", sa.String, nullable=False),
        sa.Column("detection_method", sa.String, nullable=False),
    )

    # --- risk_assessments ---
    op.create_table(
        "risk_assessments",
        sa.Column("id", sa.String, primary_key=True, nullable=False),
        sa.Column(
            "detection_id", sa.String,
            sa.ForeignKey("detection_rows.id", ondelete="CASCADE"),
            unique=True, nullable=False,
        ),
        sa.Column("migration_time_years", sa.Float, nullable=False),
        sa.Column("shelf_life_years", sa.Float, nullable=False),
        sa.Column("threat_horizon_years", sa.Float, nullable=False),
        sa.Column("urgency_ratio", sa.Float, nullable=False),
        sa.Column(
            "risk_level",
            sa.Enum("critical", "high", "medium", "low", "quantum-safe",
                    name="risk_level"),
            nullable=False,
        ),
        sa.Column("mosca_violation", sa.Boolean, nullable=False),
    )

    # --- recommendations ---
    op.create_table(
        "recommendations",
        sa.Column("id", sa.String, primary_key=True, nullable=False),
        sa.Column(
            "detection_id", sa.String,
            sa.ForeignKey("detection_rows.id", ondelete="CASCADE"),
            unique=True, nullable=False,
        ),
        sa.Column("recommended_algorithm", sa.String, nullable=False),
        sa.Column("fips_reference", sa.String, nullable=False),
        sa.Column("rationale", sa.String, nullable=False),
        sa.Column("latency_note", sa.String, nullable=False),
        sa.Column("migration_note", sa.String, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("recommendations")
    op.drop_table("risk_assessments")
    op.drop_table("detection_rows")
    op.drop_table("scan_runs")

    op.execute("DROP TYPE IF EXISTS risk_level")
    op.execute("DROP TYPE IF EXISTS detection_asset_type")
    op.execute("DROP TYPE IF EXISTS scan_status")
    op.execute("DROP TYPE IF EXISTS source_type")