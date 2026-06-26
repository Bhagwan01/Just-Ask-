"""
Just Ask — Production FastAPI Application Entry Point.

Features:
- Lifespan events (startup/shutdown) for service initialization
- Global exception handler (no stack traces leak to clients)
- CORS, correlation ID, and request logging middleware
- API router registration with versioned prefix
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.exceptions import JustAskError
from app.core.logging import correlation_id_var, get_logger, setup_logging
from app.core.middleware import CorrelationIDMiddleware, RequestLoggingMiddleware
from app.core.settings import get_settings
from app.models.schemas import ErrorResponse
from app.core.limiter import limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler

logger = get_logger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# LIFESPAN — Initialize & shutdown all services
# ══════════════════════════════════════════════════════════════════════════


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.

    Startup: Initialize logging, database, embedding model, ChromaDB, LLM client.
    Shutdown: Gracefully close all connections.
    """
    settings = get_settings()

    # ── Startup ──────────────────────────────────────────────────────
    setup_logging(
        log_level=settings.log_level,
        log_format=settings.log_format,
        log_dir=str(settings.log_dir),
        log_rotation=settings.log_rotation,
        log_retention=settings.log_retention,
    )

    logger.info(
        f"Starting {settings.app_name} v{settings.app_version} "
        f"(env={settings.env})"
    )

    # 1. Database
    from app.database.db import create_engine, create_session_factory, init_db

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    await init_db(engine)
    app.state.db_engine = engine
    app.state.db_session_factory = session_factory
    logger.info("✓ Database initialized")

    # 2. Embedding service
    from app.services.embedding_service import EmbeddingConfig, EmbeddingService

    emb_config = EmbeddingConfig.from_settings(settings)
    app.state.embedding_service = EmbeddingService(config=emb_config)
    logger.info("✓ Embedding service initialized")

    # 3. Vector database (ChromaDB)
    from app.services.vector_db import VectorDatabase, VectorDBConfig

    vdb_config = VectorDBConfig.from_settings(settings)
    app.state.vector_db = VectorDatabase(config=vdb_config)
    logger.info("✓ Vector database initialized")

    # 4. LLM service
    from app.services.llm_service import LLMConfig, LLMService

    llm_config = LLMConfig.from_settings(settings)
    app.state.llm_service = LLMService(config=llm_config)
    logger.info("✓ LLM service initialized")

    # 5. RAG orchestration service
    from app.services.pdf_parser import PDFConfig, PDFProcessor
    from app.services.rag_service import RAGService

    pdf_config = PDFConfig.from_settings(settings)
    pdf_processor = PDFProcessor(config=pdf_config)

    app.state.rag_service = RAGService(
        pdf_processor=pdf_processor,
        embedding_service=app.state.embedding_service,
        vector_db=app.state.vector_db,
        llm_service=app.state.llm_service,
        settings=settings,
    )
    logger.info("✓ RAG service initialized")

    # Set startup time for health endpoint
    from app.api.health import set_startup_time
    set_startup_time()

    logger.info(
        f"🚀 {settings.app_name} is ready! "
        f"API at http://{settings.host}:{settings.port}{settings.api_prefix}"
    )

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("Shutting down...")

    # Close LLM client
    if hasattr(app.state, "llm_service"):
        await app.state.llm_service.close()

    # Close database
    if hasattr(app.state, "db_engine"):
        from app.database.db import close_db
        await close_db(app.state.db_engine)

    logger.info("Shutdown complete")


# ══════════════════════════════════════════════════════════════════════════
# APPLICATION FACTORY
# ══════════════════════════════════════════════════════════════════════════

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description=(
            "Production-grade Retrieval Augmented Generation (RAG) application. "
            "Upload PDF documents and ask natural language questions with citations."
        ),
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        openapi_url="/openapi.json" if settings.is_development else None,
    )

    # ── Middleware (order matters: first added = outermost) ───────
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Response-Time-Ms"],
    )

    # Request logging (before correlation ID so it can use the ID)
    app.add_middleware(RequestLoggingMiddleware)

    # Correlation ID (innermost — sets the context var first)
    app.add_middleware(CorrelationIDMiddleware)

    # Rate Limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # ── Global exception handler ─────────────────────────────────
    @app.exception_handler(JustAskError)
    async def justask_error_handler(
        request: Request, exc: JustAskError
    ) -> JSONResponse:
        """Handle all JustAskError subclasses with safe error responses."""
        logger.error(
            f"[{exc.error_code}] {exc.detail}",
            status_code=exc.status_code,
        )

        content = ErrorResponse(
            error_code=exc.error_code,
            message=exc.user_message,
            detail=exc.detail if settings.is_development else None,
            request_id=correlation_id_var.get(None),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=content.model_dump(exclude_none=True),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Catch-all for unhandled exceptions — never leak stack traces."""
        logger.exception(f"Unhandled exception: {exc}")

        content = ErrorResponse(
            error_code="INTERNAL_ERROR",
            message="An unexpected error occurred. Please try again.",
            detail=str(exc) if settings.is_development else None,
            request_id=correlation_id_var.get(None),
        )
        return JSONResponse(
            status_code=500,
            content=content.model_dump(exclude_none=True),
        )

    # ── Register routers ─────────────────────────────────────────
    from app.api.chat import router as chat_router
    from app.api.documents import router as documents_router
    from app.api.health import router as health_router
    from app.api.admin import router as admin_router

    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(documents_router, prefix=settings.api_prefix)
    app.include_router(chat_router, prefix=settings.api_prefix)
    app.include_router(admin_router, prefix=settings.api_prefix)

    # ── Root endpoint ────────────────────────────────────────────
    @app.get("/", tags=["Root"])
    async def root():
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs" if settings.is_development else "disabled",
            "health": f"{settings.api_prefix}/health",
        }

    return app


# Create the app instance
app = create_app()
