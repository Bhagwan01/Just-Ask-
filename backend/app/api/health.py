"""
Health check API router.

Provides:
- /health — Full system health check
- /health/live — Liveness probe (is the process alive?)
- /health/ready — Readiness probe (are all services initialized?)
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request

from app.core.dependencies import (
    get_app_settings,
    get_embedding_service,
    get_llm_service,
    get_vector_db,
)
from app.core.settings import AppSettings
from app.models.schemas import HealthResponse, ServiceHealth

router = APIRouter(prefix="/health", tags=["Health"])

# Track startup time
_startup_time: float = time.time()


def set_startup_time() -> None:
    global _startup_time
    _startup_time = time.time()


@router.get(
    "",
    response_model=HealthResponse,
    summary="Full system health check",
    description="Checks all services: database, ChromaDB, embedding model, LLM.",
)
async def health_check(
    request: Request,
    settings: AppSettings = Depends(get_app_settings),
) -> HealthResponse:
    """Comprehensive health check of all services."""
    services: list[ServiceHealth] = []
    overall_status = "healthy"

    # ── Database ─────────────────────────────────────────────────
    try:
        from app.database.db import check_db_health
        t = time.perf_counter()
        db_ok = await check_db_health(request.app.state.db_engine)
        latency = (time.perf_counter() - t) * 1000
        services.append(ServiceHealth(
            name="database",
            status="healthy" if db_ok else "unhealthy",
            latency_ms=round(latency, 1),
        ))
        if not db_ok:
            overall_status = "degraded"
    except Exception as e:
        services.append(ServiceHealth(
            name="database", status="unhealthy", detail=str(e)[:100]
        ))
        overall_status = "degraded"

    # ── ChromaDB ─────────────────────────────────────────────────
    try:
        vector_db = request.app.state.vector_db
        t = time.perf_counter()
        chroma_ok = vector_db.health_check()
        latency = (time.perf_counter() - t) * 1000
        count = vector_db.count()
        services.append(ServiceHealth(
            name="chromadb",
            status="healthy" if chroma_ok else "unhealthy",
            latency_ms=round(latency, 1),
            detail=f"{count} chunks stored",
        ))
        if not chroma_ok:
            overall_status = "degraded"
    except Exception as e:
        services.append(ServiceHealth(
            name="chromadb", status="unhealthy", detail=str(e)[:100]
        ))
        overall_status = "degraded"

    # ── Embedding Model ──────────────────────────────────────────
    try:
        emb_service = request.app.state.embedding_service
        services.append(ServiceHealth(
            name="embedding_model",
            status="healthy",
            detail=f"dim={emb_service.embedding_dim}, cache={emb_service.cache_stats['size']}",
        ))
    except Exception as e:
        services.append(ServiceHealth(
            name="embedding_model", status="unhealthy", detail=str(e)[:100]
        ))
        overall_status = "unhealthy"

    # ── LLM (Groq) ───────────────────────────────────────────────
    try:
        llm = request.app.state.llm_service
        t = time.perf_counter()
        llm_ok = await llm.health_check()
        latency = (time.perf_counter() - t) * 1000
        services.append(ServiceHealth(
            name="groq_llm",
            status="healthy" if llm_ok else "unhealthy",
            latency_ms=round(latency, 1),
            detail=f"model={llm.config.model}",
        ))
        if not llm_ok:
            overall_status = "degraded"
    except Exception as e:
        services.append(ServiceHealth(
            name="groq_llm", status="unhealthy", detail=str(e)[:100]
        ))
        overall_status = "degraded"

    # Determine overall status
    statuses = [s.status for s in services]
    if all(s == "healthy" for s in statuses):
        overall_status = "healthy"
    elif any(s == "unhealthy" for s in statuses):
        if "embedding_model" in [s.name for s in services if s.status == "unhealthy"]:
            overall_status = "unhealthy"  # Can't function without embeddings
        else:
            overall_status = "degraded"

    return HealthResponse(
        status=overall_status,
        version=settings.app_version,
        uptime_seconds=round(time.time() - _startup_time, 1),
        environment=settings.env,
        services=services,
    )


@router.get(
    "/live",
    summary="Liveness probe",
    description="Returns 200 if the process is alive. For container health checks.",
)
async def liveness() -> dict:
    """Simple liveness probe — always returns OK."""
    return {"status": "alive"}


@router.get(
    "/ready",
    summary="Readiness probe",
    description="Returns 200 if all services are initialized and ready.",
)
async def readiness(request: Request) -> dict:
    """Check if all services are initialized and ready to serve."""
    checks = {
        "database": hasattr(request.app.state, "db_engine"),
        "embedding_service": hasattr(request.app.state, "embedding_service"),
        "vector_db": hasattr(request.app.state, "vector_db"),
        "llm_service": hasattr(request.app.state, "llm_service"),
        "rag_service": hasattr(request.app.state, "rag_service"),
    }

    all_ready = all(checks.values())

    if not all_ready:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "services": checks},
        )

    return {"status": "ready", "services": checks}
