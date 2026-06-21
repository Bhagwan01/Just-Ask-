"""
Structured logging with Loguru.

Features:
- JSON output in production, pretty-print in development
- Correlation ID per request (injected via middleware)
- Log rotation and retention
- Sensitive data scrubbing
"""

from __future__ import annotations

import sys
from contextvars import ContextVar
from typing import Optional

from loguru import logger

# ── Context variable for per-request correlation ID ──────────────────────
correlation_id_var: ContextVar[Optional[str]] = ContextVar(
    "correlation_id", default=None
)


def _correlation_id_filter(record: dict) -> bool:
    """Inject correlation_id into every log record."""
    record["extra"]["correlation_id"] = correlation_id_var.get(None) or "no-request"
    return True


def _scrub_sensitive(message: str) -> str:
    """Remove sensitive data patterns from log messages."""
    import re

    patterns = [
        (r"(password|passwd|pwd|secret|token|api_key|apikey)=\S+", r"\1=***REDACTED***"),
        (r"(Authorization:\s*Bearer\s+)\S+", r"\1***REDACTED***"),
    ]
    for pattern, replacement in patterns:
        message = re.sub(pattern, replacement, message, flags=re.IGNORECASE)
    return message


def _scrubbing_format(record: dict) -> str:
    """Format with sensitive data scrubbed (for pretty-print mode)."""
    record["message"] = _scrub_sensitive(record["message"])
    cid = record["extra"].get("correlation_id", "no-request")
    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        f"<dim>[{{extra[correlation_id]}}]</dim> | "
        "<level>{message}</level>\n"
    )
    if record["exception"]:
        fmt += "{exception}\n"
    return fmt


def setup_logging(
    log_level: str = "INFO",
    log_format: str = "pretty",
    log_dir: Optional[str] = None,
    log_rotation: str = "10 MB",
    log_retention: str = "7 days",
) -> None:
    """
    Configure application-wide Loguru logging.

    Args:
        log_level: Minimum log level.
        log_format: 'pretty' for human-readable, 'json' for structured.
        log_dir: Directory for log files. None = no file logging.
        log_rotation: When to rotate log files.
        log_retention: How long to keep old log files.
    """
    # Remove default Loguru handler
    logger.remove()

    # ── Console handler ──────────────────────────────────────────────
    if log_format == "json":
        logger.add(
            sys.stderr,
            level=log_level,
            serialize=True,  # JSON output
            filter=_correlation_id_filter,
            enqueue=True,  # Thread-safe
        )
    else:
        logger.add(
            sys.stderr,
            level=log_level,
            format=_scrubbing_format,
            filter=_correlation_id_filter,
            colorize=True,
            enqueue=True,
        )

    # ── File handler ─────────────────────────────────────────────────
    if log_dir:
        from pathlib import Path

        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        # Application log (all levels)
        logger.add(
            str(log_path / "justask.log"),
            level=log_level,
            rotation=log_rotation,
            retention=log_retention,
            compression="gz",
            serialize=True,  # Always JSON for file logs (machine-parseable)
            filter=_correlation_id_filter,
            enqueue=True,
        )

        # Error-only log (for alerting / monitoring)
        logger.add(
            str(log_path / "justask_errors.log"),
            level="ERROR",
            rotation=log_rotation,
            retention="30 days",
            compression="gz",
            serialize=True,
            filter=_correlation_id_filter,
            enqueue=True,
        )

    logger.info(
        "Logging initialized",
        level=log_level,
        format=log_format,
        file_logging=bool(log_dir),
    )


def get_logger(name: str = __name__):
    """Get a Loguru logger bound with a module name."""
    return logger.bind(module=name)
