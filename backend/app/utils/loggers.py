"""
Logger utilities — re-exports from core.logging for backward compatibility.
"""

from app.core.logging import get_logger, setup_logging, correlation_id_var

__all__ = ["get_logger", "setup_logging", "correlation_id_var"]
