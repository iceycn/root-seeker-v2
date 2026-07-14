from __future__ import annotations

import hashlib
import math
import os
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from rootseeker.infra_core.openai_compat import build_openai_compat_headers

__all__ = [
    "EmbeddingProvider",
    "HashEmbeddingProvider",
    "HttpEmbeddingProvider",
    "build_embedding_provider_from_env",
]


class EmbeddingProvider(Protocol):
    dimension: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...


@dataclass
class HashEmbeddingProvider:
    """Deterministic local embedding for offline indexing and repeatable tests.

    Tokenization splits camelCase / snake_case so identifier queries remain
    useful when a real embedding model is unavailable.
    """

    dimension: int = 384

    def _tokens(self, text: str) -> list[str]:
        from rootseeker.code_index.search_query import tokenize_code_text

        tokens = sorted(tokenize_code_text(text))
        return tokens or [text.lower().strip() or ""]

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        tokens = self._tokens(text)
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8", errors="ignore"), digest_size=16).digest()
            for idx in range(0, len(digest), 2):
                bucket = int.from_bytes(digest[idx : idx + 2], "big") % self.dimension
                sign = 1.0 if digest[idx] % 2 == 0 else -1.0
                vec[bucket] += sign
            # Character trigrams help short exact identifiers survive hashing collisions.
            compact = re.sub(r"[^a-z0-9]", "", token.lower())
            for i in range(max(0, len(compact) - 2)):
                gram = compact[i : i + 3]
                digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
                bucket = int.from_bytes(digest[:2], "big") % self.dimension
                sign = 1.0 if digest[2] % 2 == 0 else -1.0
                vec[bucket] += 0.35 * sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm <= 0:
            return vec
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


@dataclass
class HttpEmbeddingProvider:
    """OpenAI-compatible embedding provider."""

    base_url: str
    api_key: str | None = None
    model: str = "text-embedding-3-small"
    dimension: int = 1536
    timeout_seconds: float = 30.0

    def _headers(self) -> dict[str, str]:
        return build_openai_compat_headers(self.api_key or "")

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        url = f"{self.base_url.rstrip('/')}/embeddings"
        payload = {"model": self.model, "input": texts}
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(url, json=payload, headers=self._headers())
            response.raise_for_status()
            data = response.json()
        embeddings = [item["embedding"] for item in sorted(data.get("data", []), key=lambda item: item.get("index", 0))]
        if embeddings:
            self.dimension = len(embeddings[0])
        return embeddings

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._embed_batch(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed_batch([text])[0]


def build_embedding_provider_from_env() -> EmbeddingProvider:
    provider = (os.getenv("ROOTSEEKER_EMBEDDING_PROVIDER") or "hash").strip().lower()
    dimension = int(os.getenv("ROOTSEEKER_EMBEDDING_DIMENSION") or "384")
    if provider in {"hash", "local", "deterministic"}:
        return HashEmbeddingProvider(dimension=dimension)
    if provider in {"http", "openai", "openai_compatible"}:
        base_url = (os.getenv("ROOTSEEKER_EMBEDDING_BASE_URL") or "").strip()
        if not base_url:
            raise ValueError("ROOTSEEKER_EMBEDDING_BASE_URL is required for HTTP embeddings")
        return HttpEmbeddingProvider(
            base_url=base_url,
            api_key=(os.getenv("ROOTSEEKER_EMBEDDING_API_KEY") or "").strip() or None,
            model=(os.getenv("ROOTSEEKER_EMBEDDING_MODEL") or "text-embedding-3-small").strip(),
            dimension=dimension,
            timeout_seconds=float(os.getenv("ROOTSEEKER_EMBEDDING_TIMEOUT_SECONDS") or "30"),
        )
    raise ValueError(f"unsupported ROOTSEEKER_EMBEDDING_PROVIDER: {provider}")
