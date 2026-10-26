import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("entity", sa.String(50), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(36), nullable=True),
        sa.Column("calls", sa.Integer(), nullable=False),
        sa.Column("reserved_tokens", sa.Integer(), nullable=False),
        sa.Column("reserved_cost", sa.Numeric(18, 8), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("actual_cost", sa.Numeric(18, 8), nullable=False),
    )
    op.create_index("ix_executions_tenant_id", "executions", ["tenant_id"])
    op.create_index("ix_executions_status", "executions", ["status"])
    op.create_table(
        "financial_records",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("entity", sa.String(50), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("scale", sa.String(16), nullable=False),
        sa.Column("designation", sa.String(16), nullable=False),
        sa.Column("revenue", sa.Numeric(24, 4), nullable=False),
        sa.Column("expenses", sa.Numeric(24, 4), nullable=False),
        sa.UniqueConstraint("tenant_id", "entity", "period"),
    )
    op.create_index("ix_financial_records_tenant_id", "financial_records", ["tenant_id"])
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("entity", sa.String(50), nullable=False),
        sa.Column("document_id", sa.String(100), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("source", sa.String(200), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("embedding_model", sa.String(100), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.UniqueConstraint("tenant_id", "entity", "document_id", "chunk_index"),
    )
    op.create_index("ix_document_chunks_tenant_id", "document_chunks", ["tenant_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("execution_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_execution_id", "audit_events", ["execution_id"])
    for table in ("financial_records", "document_chunks"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY source_scope ON {table} USING (tenant_id = current_setting('app.tenant_id', true) AND entity = current_setting('app.entity_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true) AND entity = current_setting('app.entity_id', true))"
        )
    op.execute(
        "CREATE INDEX document_embedding_idx ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    for table in ("audit_events", "document_chunks", "financial_records", "executions"):
        op.drop_table(table)
