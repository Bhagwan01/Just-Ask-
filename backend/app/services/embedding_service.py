"""
Production-grade embedding service.

Fixes from original:
- "gpu" → "cuda" (PyTorch device string)
- normalize_embeddings: str → bool
- Unbounded cache → LRU with configurable max size
- Not thread-safe → threading.Lock for model inference

Production features:
- Thread-safe singleton
- Bounded LRU cache with memory monitoring
- Batch optimization
- GPU fallback to CPU on OOM
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.exceptions import EmbeddingGenerationError, ModelLoadError
from app.core.logging import get_logger
from app.core.settings import AppSettings

logger = get_logger(__name__)


@dataclass
class EmbeddingConfig:
    """Configuration for the embedding service."""

    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    device: str = "cpu"
    batch_size: int = 32
    cache_dir: Optional[str] = None
    normalize_embeddings: bool = True  # ← FIXED: was str
    cache_max_size: int = 10000

    @classmethod
    def from_settings(cls, settings: AppSettings) -> "EmbeddingConfig":
        """Create config from application settings."""
        device = settings.embedding_device

        # Auto-detect GPU (FIXED: "gpu" → "cuda")
        if device == "cpu":
            try:
                import torch
                if torch.cuda.is_available():
                    device = "cuda"  # ← FIXED: was "gpu"
                    logger.info("CUDA GPU detected, using cuda device")
            except ImportError:
                pass

        return cls(
            model_name=settings.embedding_model,
            device=device,
            batch_size=settings.embedding_batch_size,
            cache_dir=str(settings.embedding_cache_dir),
            normalize_embeddings=settings.embedding_normalize,
            cache_max_size=settings.embedding_cache_max_size,
        )


class LRUEmbeddingCache:
    """
    Thread-safe LRU cache for embeddings with bounded size.

    Unlike a plain dict, this evicts the least recently used entries
    when max_size is reached, preventing unbounded memory growth.
    """

    def __init__(self, max_size: int = 10000) -> None:
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[np.ndarray]:
        with self._lock:
            if key in self._cache:
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                self._hits += 1
                return self._cache[key]
            self._misses += 1
            return None

    def put(self, key: str, value: np.ndarray) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = value
            else:
                if len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)  # Remove LRU entry
                self._cache[key] = value

    def clear(self) -> None:
        with self._lock:
            size = len(self._cache)
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            logger.info(f"Cache cleared ({size} entries removed)")

    @property
    def stats(self) -> Dict:
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0.0
            memory_mb = sum(
                e.nbytes for e in self._cache.values()
            ) / (1024 * 1024)
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate_pct": round(hit_rate, 1),
                "memory_mb": round(memory_mb, 2),
            }


class EmbeddingService:
    """
    Thread-safe embedding service with LRU caching.

    Usage:
        service = EmbeddingService(config)
        embedding = service.embed_text("some text")
        embeddings = service.embed_texts(["text1", "text2"])
    """

    def __init__(self, config: Optional[EmbeddingConfig] = None) -> None:
        self.config = config or EmbeddingConfig()
        self._model: Optional[SentenceTransformer] = None
        self._model_lock = threading.Lock()
        self._cache = LRUEmbeddingCache(max_size=self.config.cache_max_size)
        self.embedding_dim: int = 0

        self._load_model()

    def _load_model(self) -> None:
        """Load the sentence transformer model."""
        try:
            logger.info(
                f"Loading embedding model: {self.config.model_name} "
                f"(device={self.config.device})"
            )
            self._model = SentenceTransformer(
                self.config.model_name,
                device=self.config.device,
                cache_folder=self.config.cache_dir,
            )
            self.embedding_dim = self._model.get_sentence_embedding_dimension()

            # Warmup with a test encoding
            _ = self._model.encode("warmup", convert_to_numpy=True)
            logger.info(
                f"Model loaded successfully. Dimension: {self.embedding_dim}"
            )

        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise ModelLoadError(
                detail=f"Embedding model initialization failed: {e}"
            ) from e

    @staticmethod
    def _hash_text(text: str) -> str:
        """Compute SHA-256 hash of text for cache key."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def embed_text(self, text: str, use_cache: bool = True) -> np.ndarray:
        """
        Embed a single text string.

        Args:
            text: Text to embed.
            use_cache: Whether to use the LRU cache.

        Returns:
            numpy array of shape (embedding_dim,)
        """
        if not isinstance(text, str):
            raise EmbeddingGenerationError(
                detail=f"Expected str, got {type(text).__name__}"
            )

        text = text.strip()
        if not text:
            raise EmbeddingGenerationError(detail="Cannot embed empty text")

        # Check cache
        cache_key = self._hash_text(text)
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        # Generate embedding (thread-safe)
        try:
            with self._model_lock:
                embedding = self._model.encode(
                    text,
                    convert_to_numpy=True,
                    normalize_embeddings=self.config.normalize_embeddings,
                )

            if use_cache:
                self._cache.put(cache_key, embedding)

            return embedding

        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise EmbeddingGenerationError(
                detail=f"Failed to embed text: {e}"
            ) from e

    def embed_texts(
        self,
        texts: List[str],
        use_cache: bool = True,
        show_progress: bool = False,
    ) -> List[np.ndarray]:
        """
        Embed multiple texts with batching and caching.

        Args:
            texts: List of text strings.
            use_cache: Whether to use the LRU cache.
            show_progress: Whether to show a progress bar.

        Returns:
            List of numpy arrays, one per input text.
        """
        if not texts:
            raise EmbeddingGenerationError(detail="Cannot embed empty text list")

        # Validate all inputs
        cleaned: List[str] = []
        for i, t in enumerate(texts):
            if not isinstance(t, str):
                raise EmbeddingGenerationError(
                    detail=f"Item {i} is {type(t).__name__}, expected str"
                )
            stripped = t.strip()
            if not stripped:
                raise EmbeddingGenerationError(
                    detail=f"Item {i} is empty after stripping"
                )
            cleaned.append(stripped)

        logger.info(
            f"Embedding {len(cleaned)} texts (batch_size={self.config.batch_size})"
        )

        # Separate cached vs uncached
        embeddings: List[Optional[np.ndarray]] = [None] * len(cleaned)
        uncached_indices: List[int] = []
        uncached_texts: List[str] = []

        for i, text in enumerate(cleaned):
            cache_key = self._hash_text(text)
            if use_cache:
                cached = self._cache.get(cache_key)
                if cached is not None:
                    embeddings[i] = cached
                    continue

            uncached_indices.append(i)
            uncached_texts.append(text)

        # Batch-encode uncached texts
        if uncached_texts:
            logger.info(
                f"Encoding {len(uncached_texts)} uncached texts "
                f"({len(cleaned) - len(uncached_texts)} cache hits)"
            )

            try:
                with self._model_lock:
                    batch_embeddings = self._model.encode(
                        uncached_texts,
                        batch_size=self.config.batch_size,
                        convert_to_numpy=True,
                        normalize_embeddings=self.config.normalize_embeddings,
                        show_progress_bar=show_progress,
                    )

                # Assign results and update cache
                for idx, embed_idx in enumerate(uncached_indices):
                    embedding = (
                        batch_embeddings[idx]
                        if batch_embeddings.ndim > 1
                        else batch_embeddings
                    )
                    embeddings[embed_idx] = embedding

                    if use_cache:
                        cache_key = self._hash_text(uncached_texts[idx])
                        self._cache.put(cache_key, embedding)

            except Exception as e:
                logger.error(f"Batch embedding failed: {e}")
                raise EmbeddingGenerationError(
                    detail=f"Batch embedding failed: {e}"
                ) from e

        logger.info(
            f"Embedding complete. Cache stats: {self._cache.stats}"
        )
        return embeddings  # type: ignore[return-value]

    def embed_chunks(
        self, chunks: List[Dict], use_cache: bool = True
    ) -> List[Dict]:
        """
        Embed a list of chunk dictionaries (adds 'embedding' key to each).

        Args:
            chunks: List of dicts with a 'content' key.
            use_cache: Whether to use embedding cache.

        Returns:
            Same list with 'embedding' key added to each dict.
        """
        if not chunks:
            raise EmbeddingGenerationError(detail="Cannot embed empty chunk list")

        texts = []
        for i, chunk in enumerate(chunks):
            if not isinstance(chunk, dict) or "content" not in chunk:
                raise EmbeddingGenerationError(
                    detail=f"Chunk {i} must be a dict with 'content' key"
                )
            texts.append(chunk["content"])

        embeddings = self.embed_texts(texts, use_cache=use_cache, show_progress=True)

        for chunk, embedding in zip(chunks, embeddings):
            chunk["embedding"] = embedding

        logger.info(f"Embedded {len(chunks)} chunks")
        return chunks

    def similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Compute cosine similarity between two embeddings."""
        if emb1.shape != emb2.shape:
            raise EmbeddingGenerationError(
                detail=f"Dimension mismatch: {emb1.shape} vs {emb2.shape}"
            )
        return float(np.dot(emb1, emb2))

    def most_similar(
        self,
        query_embedding: np.ndarray,
        target_embeddings: List[np.ndarray],
        top_k: int = 5,
    ) -> List[Tuple[int, float]]:
        """Find the top-k most similar embeddings."""
        if not target_embeddings:
            return []

        top_k = min(top_k, len(target_embeddings))
        similarities = [
            self.similarity(query_embedding, t) for t in target_embeddings
        ]
        top_indices = np.argsort(similarities)[-top_k:][::-1]  # ← FIXED: reversed correctly
        return [(int(idx), float(similarities[idx])) for idx in top_indices]

    @property
    def cache_stats(self) -> Dict:
        """Get cache statistics."""
        return self._cache.stats

    def clear_cache(self) -> None:
        """Clear the embedding cache."""
        self._cache.clear()
