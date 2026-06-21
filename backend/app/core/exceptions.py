"""
Production-grade exception hierarchy for Just Ask.

Every exception carries:
- status_code: HTTP status to return
- error_code: Machine-readable error identifier
- user_message: Safe message for API consumers
- detail: Internal detail for server logs (never sent to clients)
"""

from __future__ import annotations

from typing import Optional


class JustAskError(Exception):
    """Base exception for all Just Ask application errors."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    user_message: str = "An unexpected error occurred. Please try again."

    def __init__(
        self,
        detail: Optional[str] = None,
        user_message: Optional[str] = None,
        error_code: Optional[str] = None,
        status_code: Optional[int] = None,
    ) -> None:
        self.detail = detail or self.user_message
        if user_message:
            self.user_message = user_message
        if error_code:
            self.error_code = error_code
        if status_code:
            self.status_code = status_code
        super().__init__(self.detail)


# ── PDF Processing Errors ────────────────────────────────────────────────


class PDFProcessingError(JustAskError):
    status_code = 422
    error_code = "PDF_PROCESSING_ERROR"
    user_message = "Failed to process the PDF document."


class PDFNotFoundError(PDFProcessingError):
    status_code = 404
    error_code = "PDF_NOT_FOUND"
    user_message = "The requested PDF document was not found."


class PDFExtractionError(PDFProcessingError):
    status_code = 422
    error_code = "PDF_EXTRACTION_FAILED"
    user_message = "Failed to extract text from the PDF. The file may be corrupted or contain only images."


class PDFTooLargeError(PDFProcessingError):
    status_code = 413
    error_code = "PDF_TOO_LARGE"
    user_message = "The PDF file exceeds the maximum allowed size."


class InvalidPDFError(PDFProcessingError):
    status_code = 415
    error_code = "INVALID_PDF"
    user_message = "The uploaded file is not a valid PDF document."


class DuplicatePDFError(PDFProcessingError):
    status_code = 409
    error_code = "DUPLICATE_PDF"
    user_message = "This document has already been uploaded."


# ── Embedding Errors ─────────────────────────────────────────────────────


class EmbeddingError(JustAskError):
    status_code = 500
    error_code = "EMBEDDING_ERROR"
    user_message = "Failed to generate document embeddings."


class ModelLoadError(EmbeddingError):
    status_code = 503
    error_code = "MODEL_LOAD_FAILED"
    user_message = "The embedding model is not available. Please try again later."


class EmbeddingGenerationError(EmbeddingError):
    status_code = 500
    error_code = "EMBEDDING_GENERATION_FAILED"
    user_message = "Failed to generate embeddings for the text."


# ── Vector Database Errors ───────────────────────────────────────────────


class VectorDBError(JustAskError):
    status_code = 500
    error_code = "VECTOR_DB_ERROR"
    user_message = "A database error occurred while processing your request."


class CollectionNotFoundError(VectorDBError):
    status_code = 404
    error_code = "COLLECTION_NOT_FOUND"
    user_message = "The document collection was not found."


class VectorInsertError(VectorDBError):
    status_code = 500
    error_code = "VECTOR_INSERT_FAILED"
    user_message = "Failed to store document embeddings."


# ── LLM Errors ───────────────────────────────────────────────────────────


class LLMError(JustAskError):
    status_code = 502
    error_code = "LLM_ERROR"
    user_message = "The AI model encountered an error. Please try again."


class LLMConnectionError(LLMError):
    status_code = 503
    error_code = "LLM_CONNECTION_FAILED"
    user_message = (
        "Cannot connect to the AI model. "
        "Please ensure Ollama is running and try again."
    )


class LLMTimeoutError(LLMError):
    status_code = 504
    error_code = "LLM_TIMEOUT"
    user_message = "The AI model took too long to respond. Please try a shorter question."


class LLMResponseError(LLMError):
    status_code = 502
    error_code = "LLM_RESPONSE_INVALID"
    user_message = "Received an invalid response from the AI model."


# ── RAG Errors ───────────────────────────────────────────────────────────


class RAGError(JustAskError):
    status_code = 500
    error_code = "RAG_ERROR"
    user_message = "Failed to process your query."


class NoRelevantDocumentsError(RAGError):
    status_code = 404
    error_code = "NO_RELEVANT_DOCUMENTS"
    user_message = (
        "No relevant information was found in the uploaded documents. "
        "Try rephrasing your question or uploading more documents."
    )


class NoDocumentsUploadedError(RAGError):
    status_code = 400
    error_code = "NO_DOCUMENTS"
    user_message = "Please upload at least one document before asking questions."


# ── Database Errors ──────────────────────────────────────────────────────


class DatabaseError(JustAskError):
    status_code = 500
    error_code = "DATABASE_ERROR"
    user_message = "A database error occurred."


class DocumentNotFoundError(DatabaseError):
    status_code = 404
    error_code = "DOCUMENT_NOT_FOUND"
    user_message = "The requested document was not found."


# ── Validation Errors ────────────────────────────────────────────────────


class InputValidationError(JustAskError):
    status_code = 422
    error_code = "VALIDATION_ERROR"
    user_message = "Invalid input provided."


class QueryTooLongError(InputValidationError):
    error_code = "QUERY_TOO_LONG"
    user_message = "Your query exceeds the maximum allowed length."
