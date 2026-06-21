"""
FastAPI dependency injection.

Provides singleton service instances via Depends() for clean testability.
Services are initialized during the lifespan event and stored on app.state.
"""

from __future__ import annotations

from functools import lru_cache
from typing import AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import AppSettings, get_settings


# ── Settings dependency ──────────────────────────────────────────────────

def get_app_settings() -> AppSettings:
    """Inject the cached settings singleton."""
    return get_settings()


# ── Service dependencies (resolved from app.state) ──────────────────────

def get_embedding_service(request: Request):
    """Inject the embedding service (initialized at startup)."""
    return request.app.state.embedding_service


def get_vector_db(request: Request):
    """Inject the vector database service (initialized at startup)."""
    return request.app.state.vector_db


def get_llm_service(request: Request):
    """Inject the LLM service (initialized at startup)."""
    return request.app.state.llm_service


def get_rag_service(request: Request):
    """Inject the RAG orchestration service (initialized at startup)."""
    return request.app.state.rag_service


# ── Database session dependency ──────────────────────────────────────────

async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a transactional database session.

    Commits on success, rolls back on exception.
    """
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
