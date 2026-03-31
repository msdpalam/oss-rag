"""
SQLAlchemy ORM models — mirrors the PostgreSQL schema in infra/postgres/init.sql.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    TIMESTAMP,
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    display_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)


class InvestorProfile(Base):
    """Per-user investor profile — personalises every analyst response."""

    __tablename__ = "investor_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    age: Mapped[int | None] = mapped_column(Integer)
    risk_tolerance: Mapped[int | None] = mapped_column(Integer)       # 1 (very conservative) – 5 (very aggressive)
    horizon_years: Mapped[int | None] = mapped_column(Integer)         # investment horizon
    goals: Mapped[list | None] = mapped_column(ARRAY(String))          # ['retirement','growth','income','preservation']
    portfolio_size_usd: Mapped[int | None] = mapped_column(BigInteger)
    monthly_contribution_usd: Mapped[int | None] = mapped_column(Integer)
    tax_accounts: Mapped[list | None] = mapped_column(ARRAY(String))   # ['401k','roth_ira','traditional_ira','taxable']
    preferred_agent: Mapped[str | None] = mapped_column(String(50))    # default agent id
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    title: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    last_message_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="session", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    retrieved_chunks: Mapped[list | None] = mapped_column(JSONB)
    search_query: Mapped[str | None] = mapped_column(Text)
    model_used: Mapped[str | None] = mapped_column(String(100))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    feedback: Mapped[str | None] = mapped_column(String(10))
    feedback_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    session: Mapped["Session"] = relationship("Session", back_populates="messages")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    original_name: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    s3_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    s3_bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="uploaded")
    error_message: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    chunk_count: Mapped[int | None] = mapped_column(Integer)
    has_images: Mapped[bool | None] = mapped_column(Boolean, default=False)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    indexed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    title: Mapped[str | None] = mapped_column(String(500))
    author: Mapped[str | None] = mapped_column(String(255))
    doc_language: Mapped[str | None] = mapped_column(String(10))

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
    )


class PortfolioPosition(Base):
    """Per-user virtual portfolio — one row per ticker."""

    __tablename__ = "portfolio_positions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(20), default="stock")   # stock|etf|crypto|crypto_etf
    shares: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    avg_cost_usd: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    added_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    qdrant_point_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(20), default="text")
    char_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)

    document: Mapped["Document"] = relationship("Document", back_populates="chunks")
