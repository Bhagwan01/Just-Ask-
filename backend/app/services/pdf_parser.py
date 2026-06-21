"""
Production-grade PDF processing service.

Fixes from original:
- doc.page_data → doc.page_content (crash bug)
- PDFConfig → PDFConfig() (instantiation bug)

Production additions:
- Magic bytes validation (not just extension)
- File size limits
- Async wrapper for CPU-bound parsing
- SHA-256 hashing for duplicate detection
- Robust page mapping
- Memory-efficient processing
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Dict, List, Optional

from pypdf import PdfReader
from app.utils.splitters import RecursiveCharacterTextSplitter

from app.core.exceptions import (
    InvalidPDFError,
    PDFExtractionError,
    PDFNotFoundError,
    PDFTooLargeError,
)
from app.core.logging import get_logger
from app.core.settings import AppSettings

logger = get_logger(__name__)

# PDF magic bytes: %PDF
PDF_MAGIC_BYTES = b"%PDF"


@dataclass
class PDFConfig:
    """PDF processing configuration with validation."""

    chunk_size: int = 1000
    chunk_overlap: int = 200
    min_chunk_length: int = 50
    max_file_size_mb: int = 50
    separators: List[str] = field(
        default_factory=lambda: ["\n\n", "\n", ". ", " ", ""]
    )

    def __post_init__(self) -> None:
        if self.chunk_size < 100:
            raise ValueError("chunk_size must be >= 100")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be < chunk_size")
        if self.min_chunk_length < 10:
            raise ValueError("min_chunk_length must be >= 10")

    @classmethod
    def from_settings(cls, settings: AppSettings) -> "PDFConfig":
        """Create config from application settings."""
        return cls(
            chunk_size=settings.pdf_chunk_size,
            chunk_overlap=settings.pdf_chunk_overlap,
            min_chunk_length=settings.pdf_min_chunk_length,
            max_file_size_mb=settings.pdf_max_file_size_mb,
        )


@dataclass
class PDFResult:
    """Result of PDF text extraction."""

    text: str
    page_data: List[Dict]
    total_pages: int
    file_hash: str
    metadata: Dict


@dataclass
class ChunkResult:
    """A single processed chunk with metadata."""

    content: str
    page_number: int
    chunk_index: int
    word_count: int
    char_count: int


class PDFProcessor:
    """
    Production PDF processing pipeline.

    Handles: validation → extraction → chunking → metadata tracking.
    All CPU-bound operations are wrapped for async execution.
    """

    def __init__(self, config: Optional[PDFConfig] = None) -> None:
        self.config = config or PDFConfig()
        logger.info(
            f"PDFProcessor initialized: chunk_size={self.config.chunk_size}, "
            f"overlap={self.config.chunk_overlap}, "
            f"max_file_size={self.config.max_file_size_mb}MB"
        )

    # ── Public API ───────────────────────────────────────────────────

    async def process_pdf(self, pdf_path: str) -> List[ChunkResult]:
        """
        Full async PDF processing pipeline.

        1. Validate file
        2. Extract text with page tracking
        3. Chunk text with page mapping
        4. Return list of ChunkResult objects

        Args:
            pdf_path: Absolute path to the PDF file.

        Returns:
            List of ChunkResult objects ready for embedding.
        """
        logger.info(f"Starting PDF pipeline: {pdf_path}")

        # Run CPU-bound work in thread pool
        return await asyncio.to_thread(self._process_pdf_sync, pdf_path)

    def _process_pdf_sync(self, pdf_path: str) -> List[ChunkResult]:
        """Synchronous PDF processing (runs in thread pool)."""
        self._validate_file(pdf_path)
        extracted = self._extract_text(pdf_path)
        chunks = self._chunk_text(extracted)
        logger.info(
            f"Pipeline complete: {len(chunks)} chunks from "
            f"{extracted.total_pages} pages ({extracted.file_hash[:12]}...)"
        )
        return chunks

    @staticmethod
    def compute_file_hash(file_path: str) -> str:
        """Compute SHA-256 hash of a file for duplicate detection."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for block in iter(lambda: f.read(8192), b""):
                sha256.update(block)
        return sha256.hexdigest()

    @staticmethod
    def validate_pdf_magic_bytes(file_path: str) -> bool:
        """Check if a file starts with PDF magic bytes (%PDF)."""
        try:
            with open(file_path, "rb") as f:
                header = f.read(4)
            return header == PDF_MAGIC_BYTES
        except Exception:
            return False

    # ── Private methods ──────────────────────────────────────────────

    def _validate_file(self, pdf_path: str) -> None:
        """Validate file exists, is a PDF, and is within size limits."""
        path = Path(pdf_path)

        if not path.exists():
            raise PDFNotFoundError(detail=f"File not found: {pdf_path}")

        if not path.is_file():
            raise InvalidPDFError(detail=f"Not a file: {pdf_path}")

        # Check file extension
        if path.suffix.lower() != ".pdf":
            raise InvalidPDFError(
                detail=f"Invalid extension: {path.suffix}",
                user_message=f"Only PDF files are accepted. Got: {path.suffix}",
            )

        # Check magic bytes
        if not self.validate_pdf_magic_bytes(pdf_path):
            raise InvalidPDFError(
                detail=f"Invalid PDF magic bytes in {pdf_path}",
                user_message="The file does not appear to be a valid PDF.",
            )

        # Check file size
        file_size_mb = path.stat().st_size / (1024 * 1024)
        if file_size_mb > self.config.max_file_size_mb:
            raise PDFTooLargeError(
                detail=f"File size {file_size_mb:.1f}MB exceeds limit of {self.config.max_file_size_mb}MB",
                user_message=f"File size ({file_size_mb:.1f}MB) exceeds the maximum of {self.config.max_file_size_mb}MB.",
            )

        logger.info(f"File validated: {path.name} ({file_size_mb:.1f}MB)")

    def _extract_text(self, pdf_path: str) -> PDFResult:
        """Extract text content from PDF with page tracking."""
        try:
            reader = PdfReader(pdf_path)
            
            if not reader.pages:
                raise PDFExtractionError(
                    detail=f"No pages found in: {pdf_path}"
                )

            logger.info(f"Loaded PDF with {len(reader.pages)} pages")

            full_text = ""
            page_data: List[Dict] = []

            for i, page in enumerate(reader.pages):
                page_num = i + 1  # 1-indexed
                page_text = page.extract_text() or ""

                if not page_text.strip():
                    logger.warning(f"Page {page_num} is empty, skipping")
                    continue

                page_data.append({
                    "page_number": page_num,
                    "start_char": len(full_text),
                    "text_length": len(page_text),
                })
                full_text += page_text + "\n\n"

            if not full_text.strip():
                raise PDFExtractionError(
                    detail="No text content found in PDF",
                    user_message="The PDF appears to be empty or contains only images/scanned pages.",
                )

            # Compute file hash
            file_hash = self.compute_file_hash(pdf_path)

            # Extract PDF metadata
            metadata = {}
            if reader.metadata:
                m = reader.metadata
                metadata = {
                    "title": m.get("/Title", ""),
                    "author": m.get("/Author", ""),
                    "source": m.get("/Producer", ""),
                }

            logger.info(
                f"Extracted {len(full_text)} chars from {len(page_data)} pages"
            )

            return PDFResult(
                text=full_text,
                page_data=page_data,
                total_pages=len(reader.pages),
                file_hash=file_hash,
                metadata=metadata,
            )

        except (PDFExtractionError, PDFNotFoundError, InvalidPDFError):
            raise
        except Exception as e:
            logger.error(f"PDF extraction failed: {e}")
            raise PDFExtractionError(
                detail=f"Failed to extract text: {e}"
            ) from e

    def _chunk_text(self, extracted: PDFResult) -> List[ChunkResult]:
        """Split extracted text into chunks with page number tracking."""
        try:
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.config.chunk_size,
                chunk_overlap=self.config.chunk_overlap,
                separators=self.config.separators,
            )

            chunk_strings = splitter.split_text(extracted.text)

            if not chunk_strings:
                raise PDFExtractionError(
                    detail="Text splitter produced zero chunks"
                )

            logger.info(f"Splitter produced {len(chunk_strings)} raw chunks")

            chunks: List[ChunkResult] = []
            chunk_index = 0

            for chunk_content in chunk_strings:
                content = chunk_content.strip()

                # Skip chunks below minimum length
                if len(content) < self.config.min_chunk_length:
                    logger.debug(f"Skipping small chunk ({len(content)} chars)")
                    continue

                page_num = self._find_chunk_page(
                    content, extracted.text, extracted.page_data
                )

                chunks.append(ChunkResult(
                    content=content,
                    page_number=page_num,
                    chunk_index=chunk_index,
                    word_count=len(content.split()),
                    char_count=len(content),
                ))
                chunk_index += 1

            if not chunks:
                raise PDFExtractionError(
                    detail="All chunks were below minimum length after filtering"
                )

            # Log statistics
            avg_size = sum(c.char_count for c in chunks) / len(chunks)
            logger.info(
                f"Chunking complete: {len(chunks)} chunks, "
                f"avg={avg_size:.0f} chars, "
                f"min={min(c.char_count for c in chunks)}, "
                f"max={max(c.char_count for c in chunks)}"
            )

            return chunks

        except PDFExtractionError:
            raise
        except Exception as e:
            logger.error(f"Chunking failed: {e}")
            raise PDFExtractionError(
                detail=f"Failed to chunk text: {e}"
            ) from e

    @staticmethod
    def _find_chunk_page(
        chunk: str, full_text: str, page_data: List[Dict]
    ) -> int:
        """Determine which page a chunk belongs to based on character position."""
        try:
            chunk_pos = full_text.find(chunk)

            # Fallback: try with first 100 chars
            if chunk_pos == -1:
                chunk_pos = full_text.find(chunk[:100])

            if chunk_pos == -1:
                logger.debug("Could not locate chunk position, defaulting to page 1")
                return 1

            for page_info in page_data:
                page_start = page_info["start_char"]
                page_end = page_start + page_info["text_length"]

                if page_start <= chunk_pos < page_end:
                    return page_info["page_number"]

            # If past all pages, return last page
            return page_data[-1]["page_number"] if page_data else 1

        except Exception as e:
            logger.debug(f"Error finding chunk page: {e}")
            return 1
