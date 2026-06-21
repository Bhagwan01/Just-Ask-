"""
Chat API router — the core Q&A interface.

Provides:
- POST /chat/query — Ask a question, get answer with citations
- POST /chat/stream — Streaming response via SSE
- GET /chat/history — Query history (paginated)
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db_session, get_rag_service
from app.core.logging import get_logger
from app.models.database import QueryHistory
from app.models.schemas import ChatRequest, ChatResponse, SourceCitation

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post(
    "/query",
    response_model=ChatResponse,
    summary="Ask a question about your documents",
    description="Queries uploaded documents using hybrid search (vector + keyword) and generates an answer with citations.",
)
async def query_documents(
    request: ChatRequest,
    db_session: AsyncSession = Depends(get_db_session),
    rag_service=Depends(get_rag_service),
) -> ChatResponse:
    """Ask a natural language question about uploaded documents."""

    result = await rag_service.query(
        question=request.query,
        db_session=db_session,
        top_k=request.top_k,
        document_ids=request.document_ids,
    )

    return ChatResponse(
        answer=result["answer"],
        sources=[
            SourceCitation(
                document_name=s["document_name"],
                document_id=s["document_id"],
                page_number=s["page_number"],
                snippet=s["snippet"],
                relevance_score=s["relevance_score"],
            )
            for s in result["sources"]
        ],
        query=result["query"],
        model_used=result["model_used"],
        latency_ms=result["latency_ms"],
        num_sources=result["num_sources"],
    )


@router.post(
    "/stream",
    summary="Stream a response (Server-Sent Events)",
    description="Same as /query but returns tokens as they are generated via SSE.",
)
async def stream_query(
    request: ChatRequest,
    db_session: AsyncSession = Depends(get_db_session),
    rag_service=Depends(get_rag_service),
):
    """Stream a RAG response token by token via SSE."""

    async def event_generator():
        try:
            async for chunk in rag_service.query_stream(
                question=request.query,
                db_session=db_session,
                top_k=request.top_k,
                document_ids=request.document_ids,
            ):
                data = json.dumps(chunk, default=str)
                yield f"data: {data}\n\n"

        except Exception as e:
            error_data = json.dumps({
                "token": "",
                "done": True,
                "error": str(e),
            })
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
        },
    )


@router.get(
    "/history",
    summary="Get query history",
    description="Returns paginated list of past queries and responses.",
)
async def get_query_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db_session: AsyncSession = Depends(get_db_session),
):
    """Get paginated query history."""

    # Count total
    count_result = await db_session.execute(
        select(func.count(QueryHistory.id))
    )
    total = count_result.scalar() or 0

    # Fetch page
    offset = (page - 1) * page_size
    result = await db_session.execute(
        select(QueryHistory)
        .order_by(QueryHistory.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    queries = result.scalars().all()

    return {
        "queries": [
            {
                "id": q.id,
                "query": q.query_text,
                "answer": q.answer_text,
                "sources": json.loads(q.sources_json) if q.sources_json else [],
                "num_sources": q.num_sources,
                "latency_ms": q.latency_ms,
                "was_successful": q.was_successful,
                "model_used": q.model_used,
                "created_at": q.created_at.isoformat() if q.created_at else None,
            }
            for q in queries
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (offset + page_size) < total,
    }
