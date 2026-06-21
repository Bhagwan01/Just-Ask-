"""
LLM service using Groq for fast cloud inference.

Groq provides extremely fast inference (100+ tokens/sec) with free tier.
Uses the Groq REST API directly via httpx (no SDK dependency).

Features:
- Async HTTP client to Groq API
- Retry with exponential backoff
- Streaming support (SSE)
- Structured RAG prompt templates
- Prompt injection sanitization
- Health check / model availability
- Timeout handling
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import AsyncGenerator, Dict, List, Optional

import httpx

from app.core.exceptions import (
    LLMConnectionError,
    LLMResponseError,
    LLMTimeoutError,
)
from app.core.logging import get_logger
from app.core.settings import AppSettings

logger = get_logger(__name__)

# ── Prompt templates ─────────────────────────────────────────────────────

RAG_SYSTEM_PROMPT = """You are "Just Ask", an AI document assistant. Your job is to answer questions based ONLY on the provided context extracted from uploaded PDF documents.

Rules:
1. Answer ONLY from the provided context. Do not use your own knowledge.
2. If the answer is not in the context, say: "I don't have enough information in the uploaded documents to answer this question."
3. Always cite the source page numbers using the format [Page X] or [Pages X-Y].
4. Be concise but thorough. Use bullet points for lists.
5. If multiple documents are referenced, mention which document the information comes from.
6. Do not make up information or hallucinate sources."""

RAG_USER_TEMPLATE = """Context from uploaded documents:
---
{context}
---

Question: {question}

Provide a clear, accurate answer with page citations."""

SUMMARY_SYSTEM_PROMPT = """You are a document summarization assistant. Provide a concise, structured summary of the following document content. Include:
1. Main topics covered
2. Key points and findings
3. Important details and data

Be thorough but concise. Use bullet points."""


@dataclass
class LLMConfig:
    """Groq LLM service configuration."""

    api_key: str = ""
    base_url: str = "https://api.groq.com/openai/v1"
    model: str = "llama-3.3-70b-versatile"
    timeout: int = 120
    temperature: float = 0.1
    max_tokens: int = 2048
    max_retries: int = 3

    @classmethod
    def from_settings(cls, settings: AppSettings) -> "LLMConfig":
        return cls(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
            model=settings.groq_model,
            timeout=settings.llm_timeout,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            max_retries=settings.llm_max_retries,
        )


class LLMService:
    """
    Async LLM service backed by Groq.

    Uses Groq's OpenAI-compatible API for blazing-fast inference.
    Provides:
    - generate(): Full response generation
    - generate_stream(): Token-by-token streaming
    - health_check(): API connectivity check
    """

    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        self.config = config or LLMConfig()

        if not self.config.api_key:
            logger.warning(
                "GROQ_API_KEY not set! LLM features will not work. "
                "Get a free key at https://console.groq.com"
            )

        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(
                connect=10.0,
                read=float(self.config.timeout),
                write=30.0,
                pool=10.0,
            ),
        )
        logger.info(
            f"LLM service initialized: Groq ({self.config.model})"
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
        logger.info("LLM HTTP client closed")

    # ── Generation ───────────────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Generate a full response from Groq.

        Args:
            prompt: User prompt.
            system_prompt: System prompt (optional).
            temperature: Override default temperature.
            max_tokens: Override default max tokens.

        Returns:
            Generated text string.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": self._sanitize_prompt(prompt)})

        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature or self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
            "stream": False,
        }

        response_data = await self._request_with_retry(
            "/chat/completions", payload
        )

        # Extract the response text
        choices = response_data.get("choices", [])
        if not choices:
            raise LLMResponseError(
                detail="Groq returned no choices",
                user_message="The AI model returned an empty response. Please try again.",
            )

        response_text = choices[0].get("message", {}).get("content", "")
        if not response_text.strip():
            raise LLMResponseError(
                detail="Groq returned empty content",
                user_message="The AI model returned an empty response. Please try again.",
            )

        usage = response_data.get("usage", {})
        logger.info(
            f"Groq generated {len(response_text)} chars "
            f"(model={response_data.get('model', 'unknown')}, "
            f"tokens_in={usage.get('prompt_tokens', '?')}, "
            f"tokens_out={usage.get('completion_tokens', '?')})"
        )
        return response_text

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream tokens from Groq one at a time.

        Yields individual token strings as they arrive via SSE.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": self._sanitize_prompt(prompt)})

        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature or self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
            "stream": True,
        }

        try:
            async with self._client.stream(
                "POST", "/chat/completions", json=payload
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue

                    data_str = line[6:]  # Remove "data: " prefix

                    if data_str == "[DONE]":
                        break

                    try:
                        data = json.loads(data_str)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        token = delta.get("content", "")
                        if token:
                            yield token
                    except (json.JSONDecodeError, IndexError, KeyError):
                        continue

        except httpx.ConnectError as e:
            raise LLMConnectionError(detail=f"Cannot connect to Groq API: {e}") from e
        except httpx.ReadTimeout as e:
            raise LLMTimeoutError(detail=f"Groq API timed out: {e}") from e
        except httpx.HTTPStatusError as e:
            error_body = ""
            try:
                error_body = e.response.text[:300]
            except Exception:
                pass
            raise LLMResponseError(
                detail=f"Groq returned HTTP {e.response.status_code}: {error_body}"
            ) from e

    # ── RAG-specific methods ─────────────────────────────────────────

    async def generate_rag_response(
        self,
        question: str,
        context_chunks: List[Dict],
    ) -> str:
        """
        Generate a RAG response with context from retrieved chunks.

        Args:
            question: User's question.
            context_chunks: List of dicts with 'content', 'page_number', 'document_name'.

        Returns:
            Answer text with page citations.
        """
        # Format context with page numbers
        context_parts = []
        for i, chunk in enumerate(context_chunks, 1):
            doc_name = chunk.get("document_name", "Document")
            page = chunk.get("page_number", "?")
            content = chunk.get("content", "")
            context_parts.append(
                f"[Source {i} - {doc_name}, Page {page}]\n{content}"
            )

        context = "\n\n".join(context_parts)

        prompt = RAG_USER_TEMPLATE.format(
            context=context,
            question=question,
        )

        return await self.generate(
            prompt=prompt,
            system_prompt=RAG_SYSTEM_PROMPT,
        )

    async def generate_rag_stream(
        self,
        question: str,
        context_chunks: List[Dict],
    ) -> AsyncGenerator[str, None]:
        """Stream a RAG response token by token."""
        context_parts = []
        for i, chunk in enumerate(context_chunks, 1):
            doc_name = chunk.get("document_name", "Document")
            page = chunk.get("page_number", "?")
            content = chunk.get("content", "")
            context_parts.append(
                f"[Source {i} - {doc_name}, Page {page}]\n{content}"
            )

        context = "\n\n".join(context_parts)

        prompt = RAG_USER_TEMPLATE.format(
            context=context,
            question=question,
        )

        async for token in self.generate_stream(
            prompt=prompt,
            system_prompt=RAG_SYSTEM_PROMPT,
        ):
            yield token

    async def generate_summary(self, text: str, max_tokens: int = 1024) -> str:
        """Generate a summary of document text."""
        prompt = f"Please summarize the following document content:\n\n{text[:8000]}"
        return await self.generate(
            prompt=prompt,
            system_prompt=SUMMARY_SYSTEM_PROMPT,
            max_tokens=max_tokens,
        )

    # ── Health & utility ─────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Check if Groq API is reachable and the API key is valid."""
        if not self.config.api_key:
            logger.warning("Groq API key not configured")
            return False

        try:
            response = await self._client.get("/models", timeout=10.0)
            if response.status_code == 200:
                return True
            elif response.status_code == 401:
                logger.error("Groq API key is invalid (401 Unauthorized)")
                return False
            else:
                logger.warning(f"Groq health check returned {response.status_code}")
                return False

        except Exception as e:
            logger.warning(f"Groq health check failed: {e}")
            return False

    async def list_models(self) -> List[str]:
        """List available models from Groq."""
        try:
            response = await self._client.get("/models", timeout=10.0)
            response.raise_for_status()
            data = response.json()
            return [m.get("id", "") for m in data.get("data", [])]
        except Exception as e:
            logger.warning(f"Failed to list Groq models: {e}")
            return []

    # ── Private helpers ──────────────────────────────────────────────

    async def _request_with_retry(
        self, endpoint: str, payload: Dict
    ) -> Dict:
        """
        Make an HTTP request to Groq with exponential backoff retry.

        Retries on: connection errors, 5xx responses, 429 rate limits, timeouts.
        Does NOT retry on: 4xx responses (client errors) except 429.
        """
        last_exception: Optional[Exception] = None

        for attempt in range(self.config.max_retries + 1):
            try:
                response = await self._client.post(endpoint, json=payload)
                response.raise_for_status()
                return response.json()

            except httpx.ConnectError as e:
                last_exception = e
                if attempt < self.config.max_retries:
                    wait = 2 ** attempt
                    logger.warning(
                        f"Groq connection failed (attempt {attempt + 1}/"
                        f"{self.config.max_retries + 1}), retrying in {wait}s: {e}"
                    )
                    await asyncio.sleep(wait)
                else:
                    raise LLMConnectionError(
                        detail=f"Cannot connect to Groq after {self.config.max_retries + 1} attempts: {e}"
                    ) from e

            except httpx.ReadTimeout as e:
                last_exception = e
                if attempt < self.config.max_retries:
                    wait = 2 ** attempt
                    logger.warning(
                        f"Groq timeout (attempt {attempt + 1}/"
                        f"{self.config.max_retries + 1}), retrying in {wait}s"
                    )
                    await asyncio.sleep(wait)
                else:
                    raise LLMTimeoutError(
                        detail=f"Groq timed out after {self.config.timeout}s"
                    ) from e

            except httpx.HTTPStatusError as e:
                status = e.response.status_code

                # Rate limit — always retry with backoff
                if status == 429:
                    last_exception = e
                    # Try to get retry-after header
                    retry_after = e.response.headers.get("retry-after")
                    wait = float(retry_after) if retry_after else (2 ** attempt)
                    logger.warning(
                        f"Groq rate limited (429), waiting {wait}s "
                        f"(attempt {attempt + 1})"
                    )
                    await asyncio.sleep(wait)
                    continue

                # Server errors — retry
                if status >= 500:
                    last_exception = e
                    if attempt < self.config.max_retries:
                        wait = 2 ** attempt
                        logger.warning(
                            f"Groq server error {status} "
                            f"(attempt {attempt + 1}), retrying in {wait}s"
                        )
                        await asyncio.sleep(wait)
                        continue

                # Client errors (400, 401, 403, etc.) — don't retry
                error_body = ""
                try:
                    error_data = e.response.json()
                    error_body = error_data.get("error", {}).get("message", str(e))
                except Exception:
                    error_body = e.response.text[:300]

                if status == 401:
                    raise LLMConnectionError(
                        detail="Groq API key is invalid or expired",
                        user_message="The AI service is not configured correctly. Please check your API key.",
                    ) from e

                raise LLMResponseError(
                    detail=f"Groq returned HTTP {status}: {error_body}"
                ) from e

        # Should not reach here, but safety net
        raise LLMConnectionError(
            detail=f"All retry attempts exhausted: {last_exception}"
        )

    @staticmethod
    def _sanitize_prompt(prompt: str) -> str:
        """
        Sanitize user input to mitigate prompt injection.

        Strips patterns that attempt to inject system/assistant instructions.
        """
        injection_patterns = [
            r"<<SYS>>.*?<</SYS>>",
            r"\[INST\].*?\[/INST\]",
            r"system:\s*",
            r"assistant:\s*",
            r"</s>",
            r"<\|im_start\|>.*?<\|im_end\|>",
        ]

        cleaned = prompt
        for pattern in injection_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.DOTALL | re.IGNORECASE)

        return cleaned.strip()
