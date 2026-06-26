"""
Pydantic v2 request/response schemas for the API.

All schemas use model_config with from_attributes=True for ORM compatibility.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Base schemas ─────────────────────────────────────────────────────────


class TimestampSchema(BaseModel):
    """Common timestamp fields."""
    model_config = ConfigDict(from_attributes=True)

    created_at: datetime
    updated_at: datetime


# ── Error response ───────────────────────────────────────────────────────


class ErrorResponse(BaseModel):
    """Standard error response. Never contains stack traces."""

    error_code: str = Field(description="Machine-readable error code")
    message: str = Field(description="User-safe error message")
    detail: Optional[str] = Field(
        default=None,
        description="Additional detail (only in development mode)"
    )
    request_id: Optional[str] = Field(
        default=None,
        description="Correlation ID for this request"
    )


# ── Document schemas ────────────────────────────────────────────────────


class DocumentUploadResponse(BaseModel):
    """Response after initiating a PDF upload."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_size_bytes: int
    status: str
    message: str = "Document upload initiated. Processing in background."


class DocumentResponse(TimestampSchema):
    """Full document detail."""

    id: int
    filename: str = Field(alias="original_filename")
    file_size_bytes: int
    total_pages: Optional[int] = None
    total_chunks: Optional[int] = None
    status: str
    error_message: Optional[str] = None
    pdf_title: Optional[str] = None
    pdf_author: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class DocumentListResponse(BaseModel):
    """Paginated list of documents."""

    documents: List[DocumentResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class DocumentStatusResponse(BaseModel):
    """Lightweight status check."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    total_chunks: Optional[int] = None
    error_message: Optional[str] = None


# ── Chat schemas ─────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    """User query for RAG pipeline."""

    query: str = Field(
        min_length=1,
        max_length=2000,
        description="Natural language question",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of source chunks to retrieve",
    )
    document_ids: Optional[List[int]] = Field(
        default=None,
        description="Limit search to specific document IDs. None = search all.",
    )
    history: Optional[List[Dict[str, str]]] = Field(
        default=None,
        description="Conversation history for context",
    )

    @field_validator("query")
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        """Strip whitespace and basic prompt injection patterns."""
        v = v.strip()
        # Remove attempts to inject system/assistant prompts
        for prefix in ["system:", "assistant:", "<<SYS>>", "[INST]", "</s>"]:
            v = v.replace(prefix, "")
        return v


class SourceCitation(BaseModel):
    """A single source chunk referenced in the answer."""

    document_name: str
    document_id: int
    page_number: int
    snippet: str = Field(max_length=500, description="Relevant text snippet")
    relevance_score: float = Field(ge=0.0, le=1.0)


class ChatResponse(BaseModel):
    """RAG pipeline response with citations."""
    model_config = ConfigDict(protected_namespaces=())

    answer: str
    sources: List[SourceCitation] = []
    query: str
    model_used: str
    latency_ms: float
    num_sources: int = 0


class ChatStreamChunk(BaseModel):
    """A single chunk in a streaming response (SSE)."""
    token: str = ""
    done: bool = False
    sources: Optional[List[SourceCitation]] = None
    error: Optional[str] = None


# ── Health schemas ───────────────────────────────────────────────────────


class ServiceHealth(BaseModel):
    """Health status of a single service."""

    name: str
    status: str = Field(description="'healthy', 'unhealthy', or 'degraded'")
    latency_ms: Optional[float] = None
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    """Full system health check."""

    status: str = Field(description="'healthy', 'degraded', or 'unhealthy'")
    version: str
    uptime_seconds: float
    environment: str
    services: List[ServiceHealth]
    document_count: Optional[int] = None
    chunk_count: Optional[int] = None


# ── Admin schemas ────────────────────────────────────────────────────────


class SystemStats(BaseModel):
    """System-wide statistics."""

    document_count: int
    chunk_count: int
    total_queries: int
    embedding_cache_size: int
    embedding_cache_memory_mb: float
    vector_db_count: int
    database_size_mb: Optional[float] = None
