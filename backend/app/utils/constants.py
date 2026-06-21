"""
Application constants and enumerations.
"""

from __future__ import annotations

# ── Application ──────────────────────────────────────────────────────────
APP_NAME = "Just Ask"
API_VERSION = "v1"
API_PREFIX = f"/api/{API_VERSION}"

# ── File Upload ──────────────────────────────────────────────────────────
ALLOWED_EXTENSIONS = {".pdf"}
PDF_MAGIC_BYTES = b"%PDF"
MAX_FILENAME_LENGTH = 255

# ── Pagination ───────────────────────────────────────────────────────────
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# ── HTTP Headers ─────────────────────────────────────────────────────────
HEADER_REQUEST_ID = "X-Request-ID"
HEADER_RESPONSE_TIME = "X-Response-Time-Ms"

# ── Error Codes ──────────────────────────────────────────────────────────
ERROR_CODES = {
    "INTERNAL_ERROR": "An unexpected error occurred",
    "VALIDATION_ERROR": "Invalid input",
    "PDF_NOT_FOUND": "PDF file not found",
    "PDF_PROCESSING_ERROR": "PDF processing failed",
    "PDF_TOO_LARGE": "PDF exceeds size limit",
    "INVALID_PDF": "Invalid PDF file",
    "DUPLICATE_PDF": "Duplicate document",
    "EMBEDDING_ERROR": "Embedding generation failed",
    "MODEL_LOAD_FAILED": "Model initialization failed",
    "VECTOR_DB_ERROR": "Vector database error",
    "LLM_ERROR": "LLM generation error",
    "LLM_CONNECTION_FAILED": "Cannot connect to LLM",
    "LLM_TIMEOUT": "LLM request timed out",
    "NO_DOCUMENTS": "No documents uploaded",
    "NO_RELEVANT_DOCUMENTS": "No relevant documents found",
    "DOCUMENT_NOT_FOUND": "Document not found",
    "QUERY_TOO_LONG": "Query exceeds length limit",
}
