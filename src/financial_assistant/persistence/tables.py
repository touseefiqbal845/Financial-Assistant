from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, DateTime, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Execution(Base):
    __tablename__ = "executions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[str] = mapped_column(String(128))
    entity: Mapped[str] = mapped_column(String(50))
    scope: Mapped[dict[str, Any]] = mapped_column(JSON)
    request: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(36), nullable=True)
    calls: Mapped[int] = mapped_column(Integer, default=0)
    reserved_tokens: Mapped[int] = mapped_column(Integer, default=0)
    reserved_cost: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal(0))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    actual_cost: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal(0))


class FinancialRow(Base):
    __tablename__ = "financial_records"
    __table_args__ = (UniqueConstraint("tenant_id", "entity", "period"),)
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    entity: Mapped[str] = mapped_column(String(50))
    period: Mapped[str] = mapped_column(String(7))
    currency: Mapped[str] = mapped_column(String(3))
    scale: Mapped[str] = mapped_column(String(16))
    designation: Mapped[str] = mapped_column(String(16))
    revenue: Mapped[Decimal] = mapped_column(Numeric(24, 4))
    expenses: Mapped[Decimal] = mapped_column(Numeric(24, 4))


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("tenant_id", "entity", "document_id", "chunk_index"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    entity: Mapped[str] = mapped_column(String(50))
    document_id: Mapped[str] = mapped_column(String(100))
    chunk_index: Mapped[int] = mapped_column(Integer)
    period: Mapped[str] = mapped_column(String(7))
    source: Mapped[str] = mapped_column(String(200))
    page: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(64))
    embedding_model: Mapped[str] = mapped_column(String(100))
    embedding: Mapped[list[float]] = mapped_column(Vector(1536).with_variant(JSON, "sqlite"))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    execution_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(80))
    outcome: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
