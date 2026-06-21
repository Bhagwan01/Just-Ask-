"""
SQLAlchemy ORM models for Just Ask.

Tables:
- documents: Uploaded PDF metadata and processing status
- document_chunks: Individual text chunks with page tracking
- query_history: All user queries and responses for analytics
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


class TimestampMixin:
    """Mixin that adds created_at and updated_at columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class DocumentStatus(str, enum.Enum):
    """Document processing status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Document(TimestampMixin, Base):
    """Represents an uploaded PDF document."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True,
        comment="SHA-256 hash for duplicate detection"
    )
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_pages: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_chunks: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus),
        default=DocumentStatus.PENDING,
        nullable=False,
        index=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # PDF metadata
    pdf_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    pdf_author: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Relationships
    chunks: Mapped[List["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, filename='{self.original_filename}', status={self.status})>"


class DocumentChunk(TimestampMixin, Base):
    """A text chunk extracted from a document, with page tracking."""

    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="Reference ID in ChromaDB"
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="chunks")

    def __repr__(self) -> str:
        return f"<DocumentChunk(id={self.id}, doc_id={self.document_id}, page={self.page_number})>"


class QueryHistory(TimestampMixin, Base):
    """Record of all user queries for analytics and debugging."""

    __tablename__ = "query_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sources_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="JSON-serialized source citations"
    )
    num_sources: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    was_successful: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    def __repr__(self) -> str:
        return f"<QueryHistory(id={self.id}, query='{self.query_text[:50]}...')>"
