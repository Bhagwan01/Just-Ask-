"""
FastAPI middleware stack for production.

- CorrelationIDMiddleware: Injects X-Request-ID for request tracing
- RequestLoggingMiddleware: Logs every request with timing
"""

from __future__ import annotations

import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import correlation_id_var, get_logger

logger = get_logger(__name__)


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Injects a unique correlation ID into every request.

    - If the client sends X-Request-ID, it is reused.
    - Otherwise, a new UUID is generated.
    - The ID is set into a ContextVar so Loguru includes it in every log line.
    - The ID is returned in the response X-Request-ID header.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Set context variable for Loguru
        token = correlation_id_var.set(request_id)

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            correlation_id_var.reset(token)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs every HTTP request with method, path, status code, and latency.

    Skips logging for health check endpoints to reduce noise.
    """

    SKIP_PATHS = {"/api/v1/health/live", "/api/v1/health/ready", "/favicon.ico"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        start_time = time.perf_counter()
        method = request.method
        path = request.url.path
        client_ip = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown")
        )

        try:
            response = await call_next(request)
            latency_ms = (time.perf_counter() - start_time) * 1000

            log_msg = (
                f"{method} {path} → {response.status_code} "
                f"({latency_ms:.1f}ms) [{client_ip}]"
            )

            if response.status_code >= 500:
                logger.error(log_msg)
            elif response.status_code >= 400:
                logger.warning(log_msg)
            else:
                logger.info(log_msg)

            # Add timing header
            response.headers["X-Response-Time-Ms"] = f"{latency_ms:.1f}"
            return response

        except Exception as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"{method} {path} → UNHANDLED EXCEPTION ({latency_ms:.1f}ms) [{client_ip}]: {exc}"
            )
            raise
