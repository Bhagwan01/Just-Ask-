"""
Production ChromaDB vector database service.

Complete rewrite — the original used deprecated APIs and swallowed all errors.

Uses modern ChromaDB PersistentClient API with:
- Proper collection management
- Batch upsert with size limits
- Hybrid metadata filtering
- Health checks
- Error recovery
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import chromadb
import numpy as np

from app.core.exceptions import (
    CollectionNotFoundError,
    VectorDBError,
    VectorInsertError,
)
from app.core.logging import get_logger
from app.core.settings import AppSettings

logger = get_logger(__name__)

# ChromaDB has a max batch size of ~41,666 for add operations
CHROMA_MAX_BATCH_SIZE = 5000


@dataclass
class VectorDBConfig:
    """ChromaDB configuration."""

    persist_dir: str = "./data/chroma_db"
    collection_name: str = "documents"
    distance_metric: str = "cosine"

    @classmethod
    def from_settings(cls, settings: AppSettings) -> "VectorDBConfig":
        return cls(
            persist_dir=str(settings.vector_db_persist_dir),
            collection_name=settings.vector_db_collection_name,
            distance_metric=settings.vector_db_distance_metric,
        )


@dataclass
class SearchResult:
    """A single vector search result."""

    chunk_id: str
    content: str
    metadata: Dict[str, Any]
    distance: float
    score: float  # Converted to similarity score (1 - distance for cosine)


class VectorDatabase:
    """
    Production ChromaDB vector database service.

    Provides: add, query, delete, count, health check.
    All operations use the modern PersistentClient API.
    """

    def __init__(self, config: Optional[VectorDBConfig] = None) -> None:
        self.config = config or VectorDBConfig()
        self._client: Optional[chromadb.ClientAPI] = None
        self._collection: Optional[chromadb.Collection] = None

        self._initialize()

    def _initialize(self) -> None:
        """Initialize ChromaDB client and collection."""
        try:
            from pathlib import Path
            Path(self.config.persist_dir).mkdir(parents=True, exist_ok=True)

            logger.info(f"Initializing ChromaDB at: {self.config.persist_dir}")

            # ← FIXED: Use modern PersistentClient (not deprecated Client + Settings)
            self._client = chromadb.PersistentClient(
                path=self.config.persist_dir,
                settings=chromadb.Settings(
                    anonymized_telemetry=False,
                ),
            )

            # Get or create collection
            self._collection = self._client.get_or_create_collection(
                name=self.config.collection_name,
                metadata={"hnsw:space": self.config.distance_metric},
            )

            count = self._collection.count()
            logger.info(
                f"ChromaDB initialized. Collection '{self.config.collection_name}' "
                f"has {count} documents"
            )

        except Exception as e:
            # ← FIXED: No more bare except:pass — errors are logged and raised
            logger.error(f"ChromaDB initialization failed: {e}")
            raise VectorDBError(
                detail=f"Failed to initialize ChromaDB: {e}"
            ) from e

    # ── Add operations ───────────────────────────────────────────────

    def add_documents(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[Dict[str, Any]],
    ) -> int:
        """
        Add documents to the collection in batches.

        Args:
            ids: Unique IDs for each document.
            embeddings: Embedding vectors.
            documents: Original text content.
            metadatas: Metadata dicts (must contain only str/int/float/bool values).

        Returns:
            Number of documents added.
        """
        if not ids:
            raise VectorInsertError(detail="Cannot add empty document list")

        lengths = {len(ids), len(embeddings), len(documents), len(metadatas)}
        if len(lengths) != 1:
            raise VectorInsertError(
                detail=f"All input lists must have the same length, got {lengths}"
            )

        # Sanitize metadata (ChromaDB only accepts str, int, float, bool)
        clean_metadatas = [self._sanitize_metadata(m) for m in metadatas]

        # Convert numpy arrays to lists
        clean_embeddings = [
            emb.tolist() if isinstance(emb, np.ndarray) else emb
            for emb in embeddings
        ]

        total_added = 0
        try:
            for i in range(0, len(ids), CHROMA_MAX_BATCH_SIZE):
                batch_end = min(i + CHROMA_MAX_BATCH_SIZE, len(ids))
                self._collection.add(
                    ids=ids[i:batch_end],
                    embeddings=clean_embeddings[i:batch_end],
                    documents=documents[i:batch_end],
                    metadatas=clean_metadatas[i:batch_end],
                )
                batch_size = batch_end - i
                total_added += batch_size
                logger.debug(f"Added batch {i // CHROMA_MAX_BATCH_SIZE + 1}: {batch_size} documents")

            logger.info(f"Added {total_added} documents to collection '{self.config.collection_name}'")
            return total_added

        except Exception as e:
            logger.error(f"Failed to add documents to ChromaDB: {e}")
            raise VectorInsertError(
                detail=f"Failed to store embeddings: {e}"
            ) from e

    def add_chunks(
        self,
        chunks: List[Dict[str, Any]],
        document_id: int,
        document_name: str,
    ) -> List[str]:
        """
        Add processed chunks (with embeddings) to the collection.

        Each chunk dict must have: content, embedding, page_number, chunk_index.

        Args:
            chunks: List of chunk dicts with embeddings.
            document_id: Source document ID.
            document_name: Source document filename.

        Returns:
            List of generated ChromaDB IDs.
        """
        ids = []
        embeddings = []
        documents = []
        metadatas = []

        for chunk in chunks:
            chunk_id = f"doc{document_id}_chunk{chunk['chunk_index']}_{uuid.uuid4().hex[:8]}"
            ids.append(chunk_id)
            embeddings.append(chunk["embedding"])
            documents.append(chunk["content"])
            metadatas.append({
                "document_id": document_id,
                "document_name": document_name,
                "page_number": chunk["page_number"],
                "chunk_index": chunk["chunk_index"],
                "word_count": chunk.get("word_count", 0),
                "char_count": chunk.get("char_count", 0),
            })

        self.add_documents(ids, embeddings, documents, metadatas)
        return ids

    # ── Query operations ─────────────────────────────────────────────

    def query(
        self,
        query_embedding: List[float] | np.ndarray,
        top_k: int = 5,
        where: Optional[Dict] = None,
        where_document: Optional[Dict] = None,
    ) -> List[SearchResult]:
        """
        Query the collection with a vector embedding.

        Args:
            query_embedding: Query vector.
            top_k: Number of results to return.
            where: Metadata filter (e.g., {"document_id": 1}).
            where_document: Document content filter.

        Returns:
            List of SearchResult objects sorted by relevance.
        """
        try:
            if isinstance(query_embedding, np.ndarray):
                query_embedding = query_embedding.tolist()

            query_params = {
                "query_embeddings": [query_embedding],
                "n_results": min(top_k, self.count() or top_k),
                "include": ["documents", "metadatas", "distances"],
            }

            if where:
                query_params["where"] = where
            if where_document:
                query_params["where_document"] = where_document

            if self.count() == 0:
                return []

            results = self._collection.query(**query_params)

            search_results: List[SearchResult] = []

            if results and results["ids"] and results["ids"][0]:
                for i, chunk_id in enumerate(results["ids"][0]):
                    distance = results["distances"][0][i] if results["distances"] else 0.0
                    # Convert distance to similarity score
                    score = max(0.0, 1.0 - distance)

                    search_results.append(SearchResult(
                        chunk_id=chunk_id,
                        content=results["documents"][0][i] if results["documents"] else "",
                        metadata=results["metadatas"][0][i] if results["metadatas"] else {},
                        distance=distance,
                        score=score,
                    ))

            logger.info(f"Query returned {len(search_results)} results")
            return search_results

        except Exception as e:
            logger.error(f"ChromaDB query failed: {e}")
            raise VectorDBError(detail=f"Vector search failed: {e}") from e

    # ── Delete operations ────────────────────────────────────────────

    def delete_by_document_id(self, document_id: int) -> int:
        """Delete all chunks belonging to a document."""
        try:
            # Get IDs first
            results = self._collection.get(
                where={"document_id": document_id},
                include=[],
            )

            if not results["ids"]:
                logger.info(f"No chunks found for document_id={document_id}")
                return 0

            self._collection.delete(ids=results["ids"])
            count = len(results["ids"])
            logger.info(f"Deleted {count} chunks for document_id={document_id}")
            return count

        except Exception as e:
            logger.error(f"Failed to delete chunks for document {document_id}: {e}")
            raise VectorDBError(
                detail=f"Failed to delete document chunks: {e}"
            ) from e

    def delete_by_ids(self, ids: List[str]) -> None:
        """Delete specific chunks by their IDs."""
        try:
            self._collection.delete(ids=ids)
            logger.info(f"Deleted {len(ids)} chunks by ID")
        except Exception as e:
            logger.error(f"Failed to delete by IDs: {e}")
            raise VectorDBError(detail=f"Failed to delete chunks: {e}") from e

    # ── Utility operations ───────────────────────────────────────────

    def count(self) -> int:
        """Get total number of documents in the collection."""
        try:
            return self._collection.count()
        except Exception:
            return 0

    def health_check(self) -> bool:
        """Verify the vector database is operational."""
        try:
            _ = self._collection.count()
            return True
        except Exception as e:
            logger.error(f"ChromaDB health check failed: {e}")
            return False

    def reset_collection(self) -> None:
        """Delete and recreate the collection (destructive!)."""
        try:
            self._client.delete_collection(self.config.collection_name)
            self._collection = self._client.create_collection(
                name=self.config.collection_name,
                metadata={"hnsw:space": self.config.distance_metric},
            )
            logger.warning(f"Collection '{self.config.collection_name}' reset")
        except Exception as e:
            logger.error(f"Failed to reset collection: {e}")
            raise VectorDBError(detail=f"Failed to reset collection: {e}") from e

    @staticmethod
    def _sanitize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ensure all metadata values are ChromaDB-compatible types.

        ChromaDB only accepts: str, int, float, bool.
        Other types are converted to str.
        """
        sanitized = {}
        for key, value in metadata.items():
            if isinstance(value, (str, int, float, bool)):
                sanitized[key] = value
            elif value is None:
                sanitized[key] = ""
            else:
                sanitized[key] = str(value)
        return sanitized
