"""
RAG Orchestration Service — ties together the entire pipeline.

Document Ingestion: upload → validate → parse → chunk → embed → store
Query Pipeline: query → embed → hybrid search → rerank → LLM generate → format

Features:
- Hybrid search (vector + BM25 keyword matching)
- Result deduplication
- Citation generation with page numbers
- Performance metrics per pipeline stage
- Background document processing
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from rank_bm25 import BM25Okapi
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    DuplicatePDFError,
    NoDocumentsUploadedError,
    NoRelevantDocumentsError,
    RAGError,
)
from app.core.logging import get_logger
from app.core.settings import AppSettings
from app.models.database import Document, DocumentChunk, DocumentStatus, QueryHistory
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService
from app.services.pdf_parser import PDFProcessor, ChunkResult
from app.services.vector_db import VectorDatabase

logger = get_logger(__name__)


class RAGService:
    """
    Orchestrates the full RAG pipeline.

    Coordinates: PDFProcessor → EmbeddingService → VectorDatabase → LLMService.
    """

    def __init__(
        self,
        pdf_processor: PDFProcessor,
        embedding_service: EmbeddingService,
        vector_db: VectorDatabase,
        llm_service: LLMService,
        settings: AppSettings,
    ) -> None:
        self.pdf_processor = pdf_processor
        self.embedding_service = embedding_service
        self.vector_db = vector_db
        self.llm_service = llm_service
        self.settings = settings

        logger.info("RAG service initialized")

        logger.info("RAG service initialized")

    # ══════════════════════════════════════════════════════════════════
    # DOCUMENT INGESTION PIPELINE
    # ══════════════════════════════════════════════════════════════════

    async def ingest_document(
        self,
        document_id: int,
        file_path: str,
        original_filename: str,
        db_session: AsyncSession,
    ) -> Document:
        """
        Full document ingestion pipeline (runs in background).

        Steps:
        1. Fetch database record created by API
        2. Parse PDF → chunks
        3. Generate embeddings
        4. Store in ChromaDB
        5. Store chunk records in SQL DB
        6. Update document status to COMPLETED

        Args:
            document_id: ID of the document record.
            file_path: Path to the uploaded PDF file.
            original_filename: Original filename from upload.
            db_session: Database session.

        Returns:
            Document ORM object.
        """
        t_start = time.perf_counter()
        doc_record: Optional[Document] = None

        try:
            # ── Step 1: Get DB record ───────────────────────────────
            doc_record = await db_session.get(Document, document_id)
            if not doc_record:
                raise RAGError(detail=f"Document {document_id} not found", user_message="Document not found")
            
            doc_id = doc_record.id

            logger.info(f"Starting processing for document: id={doc_id}, file={original_filename}")

            # ── Step 3: Parse PDF ────────────────────────────────────
            t_parse = time.perf_counter()
            chunks: List[ChunkResult] = await self.pdf_processor.process_pdf(file_path)
            parse_ms = (time.perf_counter() - t_parse) * 1000
            logger.info(f"PDF parsed: {len(chunks)} chunks in {parse_ms:.0f}ms")

            # ── Step 4: Generate embeddings ──────────────────────────
            t_embed = time.perf_counter()
            texts = [c.content for c in chunks]
            embeddings = await asyncio.to_thread(
                self.embedding_service.embed_texts,
                texts,
                True,
                True,
            )
            embed_ms = (time.perf_counter() - t_embed) * 1000
            logger.info(f"Embeddings generated: {len(embeddings)} in {embed_ms:.0f}ms")

            # ── Step 5: Store in ChromaDB ────────────────────────────
            t_store = time.perf_counter()
            chunk_dicts = []
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                chunk_dicts.append({
                    "content": chunk.content,
                    "embedding": embedding,
                    "page_number": chunk.page_number,
                    "chunk_index": i,
                    "word_count": chunk.word_count,
                    "char_count": chunk.char_count,
                })

            chroma_ids = await asyncio.to_thread(
                self.vector_db.add_chunks,
                chunk_dicts,
                doc_id,
                original_filename,
            )
            store_ms = (time.perf_counter() - t_store) * 1000
            logger.info(f"Stored in ChromaDB: {len(chroma_ids)} chunks in {store_ms:.0f}ms")

            # ── Step 6: Store chunk records in SQL ───────────────────
            for i, (chunk, chroma_id) in enumerate(zip(chunks, chroma_ids)):
                db_chunk = DocumentChunk(
                    document_id=doc_id,
                    chunk_index=i,
                    content=chunk.content,
                    page_number=chunk.page_number,
                    word_count=chunk.word_count,
                    char_count=chunk.char_count,
                    embedding_id=chroma_id,
                )
                db_session.add(db_chunk)

            # ── Step 7: Update document status ───────────────────────
            doc_record.status = DocumentStatus.COMPLETED
            doc_record.total_pages = max(c.page_number for c in chunks)
            doc_record.total_chunks = len(chunks)

            await db_session.commit()

            # BM25 index is now dynamically computed per query.

            # ── Step 8: Delete raw PDF if configured ─────────────────
            if self.settings.pdf_delete_after_processing:
                try:
                    file_path_obj = Path(file_path)
                    if file_path_obj.exists():
                        file_path_obj.unlink()
                        logger.info(f"Deleted raw PDF file to save space: {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete raw PDF file {file_path}: {e}")

            total_ms = (time.perf_counter() - t_start) * 1000
            logger.info(
                f"Document ingestion complete: id={doc_id}, "
                f"'{original_filename}', {len(chunks)} chunks, "
                f"{total_ms:.0f}ms total "
                f"(parse={parse_ms:.0f}ms, embed={embed_ms:.0f}ms, store={store_ms:.0f}ms)"
            )

            return doc_record

        except DuplicatePDFError:
            raise
        except Exception as e:
            logger.error(f"Document ingestion failed: {e}")
            if doc_record is not None:
                doc_record.status = DocumentStatus.FAILED
                doc_record.error_message = str(e)[:500]
                try:
                    await db_session.commit()
                except Exception:
                    await db_session.rollback()

            raise RAGError(
                detail=f"Document ingestion failed: {e}",
                user_message="Failed to process the document. Please try again.",
            ) from e

    # ══════════════════════════════════════════════════════════════════
    # QUERY PIPELINE
    # ══════════════════════════════════════════════════════════════════

    async def query(
        self,
        question: str,
        db_session: AsyncSession,
        top_k: int = 5,
        document_ids: Optional[List[int]] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Full RAG query pipeline.

        Steps:
        1. Validate there are documents to search
        2. Embed the query
        3. Vector search in ChromaDB
        4. BM25 keyword search
        5. Hybrid scoring (combine vector + BM25)
        6. Generate answer with LLM
        7. Format response with citations
        8. Record in query history

        Args:
            question: Natural language question.
            db_session: Database session.
            top_k: Number of source chunks to retrieve.
            document_ids: Optional filter to specific documents.

        Returns:
            Dict with answer, sources, latency, model info.
        """
        t_start = time.perf_counter()
        query_record = QueryHistory(query_text=question)

        try:
            # ── Step 1: Validate ─────────────────────────────────────
            doc_count = await db_session.execute(
                select(func.count(Document.id)).where(
                    Document.status == DocumentStatus.COMPLETED
                )
            )
            if doc_count.scalar() == 0:
                raise NoDocumentsUploadedError()

            # ── Step 2: Embed query ──────────────────────────────────
            t_embed = time.perf_counter()
            query_embedding = await asyncio.to_thread(
                self.embedding_service.embed_text, question
            )
            embed_ms = (time.perf_counter() - t_embed) * 1000

            # ── Step 3: Vector search ────────────────────────────────
            t_search = time.perf_counter()

            where_filter = None
            if document_ids:
                if len(document_ids) == 1:
                    where_filter = {"document_id": document_ids[0]}
                else:
                    where_filter = {
                        "$or": [{"document_id": did} for did in document_ids]
                    }

            vector_results = await asyncio.to_thread(
                self.vector_db.query,
                query_embedding,
                top_k * 2,  # Fetch more for hybrid reranking
                where_filter,
            )
            search_ms = (time.perf_counter() - t_search) * 1000

            if not vector_results:
                raise NoRelevantDocumentsError()

            # ── Step 4: BM25 scoring ─────────────────────────────────
            hybrid_results = self._hybrid_rank(
                question, vector_results, top_k
            )

            # ── Step 5: Generate answer ──────────────────────────────
            t_llm = time.perf_counter()

            context_chunks = [
                {
                    "content": r["content"],
                    "page_number": r["metadata"].get("page_number", 0),
                    "document_name": r["metadata"].get("document_name", "Document"),
                }
                for r in hybrid_results
            ]

            answer = await self.llm_service.generate_rag_response(
                question=question,
                context_chunks=context_chunks,
                history=history,
            )
            llm_ms = (time.perf_counter() - t_llm) * 1000

            # ── Step 6: Format sources ───────────────────────────────
            sources = []
            for r in hybrid_results:
                sources.append({
                    "document_name": r["metadata"].get("document_name", "Document"),
                    "document_id": r["metadata"].get("document_id", 0),
                    "page_number": r["metadata"].get("page_number", 0),
                    "snippet": r["content"][:300],
                    "relevance_score": round(r["score"], 3),
                })

            total_ms = (time.perf_counter() - t_start) * 1000

            # ── Step 7: Record query history ─────────────────────────
            query_record.answer_text = answer
            query_record.sources_json = json.dumps(sources)
            query_record.num_sources = len(sources)
            query_record.latency_ms = total_ms
            query_record.was_successful = True
            query_record.model_used = self.llm_service.config.model
            db_session.add(query_record)

            logger.info(
                f"Query complete: '{question[:80]}...' → {len(sources)} sources, "
                f"{total_ms:.0f}ms total "
                f"(embed={embed_ms:.0f}ms, search={search_ms:.0f}ms, llm={llm_ms:.0f}ms)"
            )

            return {
                "answer": answer,
                "sources": sources,
                "query": question,
                "model_used": self.llm_service.config.model,
                "latency_ms": round(total_ms, 1),
                "num_sources": len(sources),
            }

        except (NoDocumentsUploadedError, NoRelevantDocumentsError):
            raise
        except Exception as e:
            total_ms = (time.perf_counter() - t_start) * 1000
            logger.error(f"Query failed ({total_ms:.0f}ms): {e}")

            query_record.was_successful = False
            query_record.error_message = str(e)[:500]
            query_record.latency_ms = total_ms
            db_session.add(query_record)

            raise RAGError(
                detail=f"Query pipeline failed: {e}"
            ) from e

    async def query_stream(
        self,
        question: str,
        db_session: AsyncSession,
        top_k: int = 5,
        document_ids: Optional[List[int]] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Streaming query pipeline — yields tokens as they arrive.

        Yields dicts with:
        - {"token": "...", "done": False} for each token
        - {"token": "", "done": True, "sources": [...]} for final chunk
        """
        t_start = time.perf_counter()

        # Steps 1-4 same as non-streaming
        doc_count = await db_session.execute(
            select(func.count(Document.id)).where(
                Document.status == DocumentStatus.COMPLETED
            )
        )
        if doc_count.scalar() == 0:
            raise NoDocumentsUploadedError()

        query_embedding = await asyncio.to_thread(
            self.embedding_service.embed_text, question
        )

        where_filter = None
        if document_ids:
            if len(document_ids) == 1:
                where_filter = {"document_id": document_ids[0]}
            else:
                where_filter = {
                    "$or": [{"document_id": did} for did in document_ids]
                }

        vector_results = await asyncio.to_thread(
            self.vector_db.query, query_embedding, top_k * 2, where_filter
        )

        if not vector_results:
            raise NoRelevantDocumentsError()

        hybrid_results = self._hybrid_rank(question, vector_results, top_k)

        context_chunks = [
            {
                "content": r["content"],
                "page_number": r["metadata"].get("page_number", 0),
                "document_name": r["metadata"].get("document_name", "Document"),
            }
            for r in hybrid_results
        ]

        # Stream LLM response
        full_answer = ""
        async for token in self.llm_service.generate_rag_stream(
            question=question, context_chunks=context_chunks, history=history
        ):
            full_answer += token
            yield {"token": token, "done": False}

        # Final chunk with sources
        sources = []
        for r in hybrid_results:
            sources.append({
                "document_name": r["metadata"].get("document_name", "Document"),
                "document_id": r["metadata"].get("document_id", 0),
                "page_number": r["metadata"].get("page_number", 0),
                "snippet": r["content"][:300],
                "relevance_score": round(r["score"], 3),
            })

        total_ms = (time.perf_counter() - t_start) * 1000

        # Record query
        query_record = QueryHistory(
            query_text=question,
            answer_text=full_answer,
            sources_json=json.dumps(sources),
            num_sources=len(sources),
            latency_ms=total_ms,
            was_successful=True,
            model_used=self.llm_service.config.model,
        )
        db_session.add(query_record)
        await db_session.commit()

        yield {
            "token": "",
            "done": True,
            "sources": sources,
            "latency_ms": round(total_ms, 1),
        }

    # ══════════════════════════════════════════════════════════════════
    # DOCUMENT MANAGEMENT
    # ══════════════════════════════════════════════════════════════════

    async def delete_document(
        self, document_id: int, db_session: AsyncSession
    ) -> bool:
        """Delete a document and all its chunks from both DBs."""
        try:
            # Delete from ChromaDB
            await asyncio.to_thread(
                self.vector_db.delete_by_document_id, document_id
            )

            # Delete from SQL (cascade deletes chunks)
            result = await db_session.execute(
                select(Document).where(Document.id == document_id)
            )
            doc = result.scalar_one_or_none()
            if doc:
                await db_session.delete(doc)
                await db_session.commit()

                # BM25 index is now dynamically computed per query.

                logger.info(f"Document {document_id} deleted successfully")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to delete document {document_id}: {e}")
            raise RAGError(detail=f"Failed to delete document: {e}") from e

    # ══════════════════════════════════════════════════════════════════
    # HYBRID SEARCH
    # ══════════════════════════════════════════════════════════════════

    def _hybrid_rank(
        self,
        query: str,
        vector_results: list,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """
        Combine vector similarity scores with BM25 keyword scores.

        Uses dynamic BM25 rescoring on the retrieved vector chunks.
        """
        vector_weight = self.settings.hybrid_search_vector_weight

        # 1. Build local BM25 index for the retrieved chunks
        tokenized_corpus = [r.content.lower().split() for r in vector_results]
        local_bm25 = BM25Okapi(tokenized_corpus) if tokenized_corpus else None
        tokenized_query = query.lower().split()
        
        bm25_scores = []
        max_bm25 = 1.0
        if local_bm25:
            bm25_scores = local_bm25.get_scores(tokenized_query)
            max_bm25 = max(bm25_scores) if len(bm25_scores) > 0 and max(bm25_scores) > 0 else 1.0

        # Build scored results
        scored: List[Dict[str, Any]] = []

        for i, result in enumerate(vector_results):
            vector_score = result.score

            # Normalize BM25 score
            bm25_score = (bm25_scores[i] / max_bm25) if local_bm25 and i < len(bm25_scores) else 0.0

            # Combined score
            hybrid_score = (vector_weight * vector_score) + (
                (1 - vector_weight) * bm25_score
            )

            scored.append({
                "content": result.content,
                "metadata": result.metadata,
                "vector_score": vector_score,
                "bm25_score": bm25_score,
                "score": hybrid_score,
                "chunk_id": result.chunk_id,
            })

        # Sort by combined score descending
        scored.sort(key=lambda x: x["score"], reverse=True)

        # Deduplicate (same content from overlapping chunks)
        seen_content = set()
        deduped: List[Dict[str, Any]] = []
        for item in scored:
            content_hash = hashlib.md5(
                item["content"][:200].encode()
            ).hexdigest()
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                deduped.append(item)

        return deduped[:top_k]
