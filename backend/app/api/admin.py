"""
Admin API router — system statistics and management.

Provides:
- GET /admin/stats — System-wide statistics
- POST /admin/cache/clear — Clear embedding cache
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db_session, get_embedding_service, get_vector_db
from app.core.logging import get_logger
from app.models.database import Document, DocumentChunk, QueryHistory
from app.models.schemas import SystemStats

logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get(
    "/stats",
    response_model=SystemStats,
    summary="Get system statistics",
)
async def get_system_stats(
    db_session: AsyncSession = Depends(get_db_session),
    embedding_service=Depends(get_embedding_service),
    vector_db=Depends(get_vector_db),
):
    """Get comprehensive system statistics."""

    doc_count_result = await db_session.execute(
        select(func.count(Document.id))
    )
    doc_count = doc_count_result.scalar() or 0

    chunk_count_result = await db_session.execute(
        select(func.count(DocumentChunk.id))
    )
    chunk_count = chunk_count_result.scalar() or 0

    query_count_result = await db_session.execute(
        select(func.count(QueryHistory.id))
    )
    query_count = query_count_result.scalar() or 0

    cache_stats = embedding_service.cache_stats

    return SystemStats(
        document_count=doc_count,
        chunk_count=chunk_count,
        total_queries=query_count,
        embedding_cache_size=cache_stats["size"],
        embedding_cache_memory_mb=cache_stats["memory_mb"],
        vector_db_count=vector_db.count(),
    )


@router.post(
    "/cache/clear",
    summary="Clear embedding cache",
)
async def clear_cache(
    embedding_service=Depends(get_embedding_service),
):
    """Clear the embedding cache to free memory."""
    stats_before = embedding_service.cache_stats
    embedding_service.clear_cache()
    return {
        "message": "Cache cleared",
        "cleared_entries": stats_before["size"],
        "freed_memory_mb": stats_before["memory_mb"],
    }
