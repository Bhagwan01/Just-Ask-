"""
Production-grade application settings using Pydantic Settings.

All configuration is loaded from environment variables with validated defaults.
Settings are frozen after creation to prevent runtime mutation.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Path constants (resolved once at import time)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent  # backend/app
_BACKEND_ROOT = _PROJECT_ROOT.parent                     # backend/
_DATA_DIR = _BACKEND_ROOT / "data"
_MODELS_DIR = _BACKEND_ROOT / "models"
_LOG_DIR = _BACKEND_ROOT / "logs"
_UPLOAD_DIR = _DATA_DIR / "uploads"


class AppSettings(BaseSettings):
    """Top-level application settings."""

    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Environment ──────────────────────────────────────────────────────
    env: str = Field(default="development", description="Running environment")
    debug: bool = Field(default=True, description="Enable debug mode")
    app_name: str = Field(default="Just Ask", description="Application name")
    app_version: str = Field(default="1.0.0", description="Application version")
    api_prefix: str = Field(default="/api/v1", description="API route prefix")
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, ge=1, le=65535, description="Server port")

    # ── CORS ─────────────────────────────────────────────────────────────
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173"],
        description="Allowed CORS origins",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            # Handle JSON array string from env var
            import json
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                # Handle comma-separated string
                return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # ── Paths ────────────────────────────────────────────────────────────
    data_dir: Path = Field(default=_DATA_DIR)
    models_dir: Path = Field(default=_MODELS_DIR)
    log_dir: Path = Field(default=_LOG_DIR)
    upload_dir: Path = Field(default=_UPLOAD_DIR)

    # ── Logging ──────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO", description="Log level")
    log_format: str = Field(
        default="pretty", description="Log format: 'pretty' or 'json'"
    )
    log_rotation: str = Field(default="10 MB", description="Log file rotation size")
    log_retention: str = Field(default="7 days", description="Log retention period")

    # ── PDF Processing ───────────────────────────────────────────────────
    pdf_chunk_size: int = Field(default=1000, ge=100, le=10000)
    pdf_chunk_overlap: int = Field(default=200, ge=0)
    pdf_min_chunk_length: int = Field(default=50, ge=10)
    pdf_max_file_size_mb: int = Field(default=50, ge=1, le=500)

    # ── Embedding Service ────────────────────────────────────────────────
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="HuggingFace model ID for embeddings",
    )
    embedding_device: str = Field(default="cpu", description="cpu or cuda")
    embedding_batch_size: int = Field(default=32, ge=1, le=512)
    embedding_cache_dir: Optional[Path] = None
    embedding_cache_max_size: int = Field(
        default=10000, ge=100, description="Max items in embedding LRU cache"
    )
    embedding_normalize: bool = Field(default=True)

    # ── Vector Database (ChromaDB) ───────────────────────────────────────
    vector_db_persist_dir: Optional[Path] = None
    vector_db_collection_name: str = Field(default="documents")
    vector_db_distance_metric: str = Field(default="cosine")

    # ── Search ───────────────────────────────────────────────────────────
    search_top_k: int = Field(default=5, ge=1, le=50)
    hybrid_search_vector_weight: float = Field(default=0.7, ge=0.0, le=1.0)

    # ── LLM (Groq) ──────────────────────────────────────────────────────
    groq_api_key: str = Field(
        default="", description="Groq API key (get free at https://console.groq.com)"
    )
    groq_base_url: str = Field(
        default="https://api.groq.com/openai/v1", description="Groq API base URL"
    )
    groq_model: str = Field(
        default="llama-3.3-70b-versatile",
        description="Groq model (llama-3.3-70b-versatile, mixtral-8x7b-32768, etc.)",
    )
    llm_timeout: int = Field(default=120, ge=10, description="LLM request timeout (seconds)")
    llm_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=2048, ge=100, le=32768)
    llm_max_retries: int = Field(default=3, ge=0, le=10)

    # ── PDF Storage ──────────────────────────────────────────────────────
    pdf_delete_after_processing: bool = Field(
        default=True,
        description="Delete raw PDF after embedding to save disk space. Embeddings are kept.",
    )

    # ── Database ─────────────────────────────────────────────────────────
    database_url: str = Field(
        default="sqlite+aiosqlite:///./justask.db",
        description="SQLAlchemy async database URL",
    )
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=10, ge=0, le=100)
    db_echo: bool = Field(default=False, description="Echo SQL queries")

    # ── Security ─────────────────────────────────────────────────────────
    allowed_upload_extensions: List[str] = Field(default=[".pdf"])
    max_query_length: int = Field(default=2000, ge=10, le=10000)
    rate_limit_requests: int = Field(default=60, description="Requests per minute")

    # ── Validators ───────────────────────────────────────────────────────

    @field_validator("database_url")
    @classmethod
    def fix_database_url(cls, v: str) -> str:
        """Auto-convert Render's postgres:// to asyncpg-compatible URL."""
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://") and "+asyncpg" not in v:
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @field_validator("pdf_chunk_overlap")
    @classmethod
    def validate_chunk_overlap(cls, v: int, info) -> int:
        chunk_size = info.data.get("pdf_chunk_size", 1000)
        if v >= chunk_size:
            raise ValueError(
                f"pdf_chunk_overlap ({v}) must be less than pdf_chunk_size ({chunk_size})"
            )
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log_level must be one of {valid}, got '{v}'")
        return upper

    @field_validator("env")
    @classmethod
    def validate_env(cls, v: str) -> str:
        valid = {"development", "production", "testing"}
        if v.lower() not in valid:
            raise ValueError(f"env must be one of {valid}, got '{v}'")
        return v.lower()

    @model_validator(mode="after")
    def set_computed_defaults(self) -> "AppSettings":
        """Set defaults that depend on other fields."""
        if self.embedding_cache_dir is None:
            object.__setattr__(
                self, "embedding_cache_dir", self.models_dir / "embeddings"
            )
        if self.vector_db_persist_dir is None:
            object.__setattr__(
                self, "vector_db_persist_dir", self.data_dir / "chroma_db"
            )
        return self

    @model_validator(mode="after")
    def create_directories(self) -> "AppSettings":
        """Ensure required directories exist."""
        for d in [
            self.data_dir,
            self.models_dir,
            self.log_dir,
            self.upload_dir,
            self.embedding_cache_dir,
            self.vector_db_persist_dir,
        ]:
            if d is not None:
                d.mkdir(parents=True, exist_ok=True)
        return self

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def is_development(self) -> bool:
        return self.env == "development"

    @property
    def is_testing(self) -> bool:
        return self.env == "testing"


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """
    Cached singleton settings loader.

    Call this function from anywhere to get the application settings.
    The settings object is created once and reused for the lifetime of the process.
    """
    return AppSettings()
