from __future__ import annotations

import logging
import os
import uuid

import httpx

from rootseeker.code_index.chunker import CodeChunk
from rootseeker.code_index.embedding import EmbeddingProvider, build_embedding_provider_from_env
from rootseeker.contracts.common import utc_now
from rootseeker.contracts.indexing import IndexKind, IndexStatus

__all__ = ["QdrantIndexer", "get_qdrant_status"]

logger = logging.getLogger(__name__)


def _get_default_endpoint() -> str:
    """与 root_seek `qdrant.url` 对齐；支持 QDRANT_* 与 ROOTSEEKER_QDRANT_*。"""
    return (
        (os.getenv("QDRANT_ENDPOINT") or "").strip()
        or (os.getenv("ROOTSEEKER_QDRANT_ENDPOINT") or "").strip()
        or "http://127.0.0.1:6333"
    )


def _get_default_timeout() -> float:
    raw = os.getenv("QDRANT_TIMEOUT_SECONDS") or os.getenv("ROOTSEEKER_QDRANT_TIMEOUT_SECONDS")
    return float(raw) if raw else 30.0


def _get_default_collection_name() -> str:
    """与 root_seek `qdrant.collection` 一致，默认 code_chunks。"""
    return (
        (os.getenv("QDRANT_COLLECTION_NAME") or "").strip()
        or (os.getenv("ROOTSEEKER_QDRANT_COLLECTION_NAME") or "").strip()
        or "code_chunks"
    )


def _get_default_api_key() -> str | None:
    raw = (os.getenv("QDRANT_API_KEY") or os.getenv("ROOTSEEKER_QDRANT_API_KEY") or "").strip()
    return raw or None


class QdrantIndexer:
    """Qdrant 向量搜索引擎索引器"""

    def __init__(
        self,
        endpoint: str | None = None,
        collection_name: str | None = None,
        timeout_seconds: float | None = None,
        api_key: str | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.endpoint = (endpoint or _get_default_endpoint()).rstrip("/")
        self.collection_name = collection_name or _get_default_collection_name()
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else _get_default_timeout()
        self._api_key = api_key if api_key is not None else _get_default_api_key()
        self.embedding_provider = embedding_provider or build_embedding_provider_from_env()

    def _headers(self) -> dict[str, str]:
        if self._api_key:
            return {"api-key": self._api_key}
        return {}

    def ensure_collection(self) -> bool:
        """确保集合存在"""
        try:
            with httpx.Client(timeout=self.timeout_seconds, trust_env=False) as client:
                # 检查集合是否存在
                response = client.get(
                    f"{self.endpoint}/collections/{self.collection_name}",
                    headers=self._headers(),
                )
                if response.status_code == 200:
                    data = response.json()
                    existing = (
                        data.get("result", {})
                        .get("config", {})
                        .get("params", {})
                        .get("vectors", {})
                    )
                    existing_size = existing.get("size") if isinstance(existing, dict) else None
                    if existing_size == self.embedding_provider.dimension:
                        return True
                    logger.warning(
                        "Qdrant collection %s dimension mismatch: existing=%s expected=%s; recreating",
                        self.collection_name,
                        existing_size,
                        self.embedding_provider.dimension,
                    )
                    delete_response = client.delete(
                        f"{self.endpoint}/collections/{self.collection_name}",
                        headers=self._headers(),
                    )
                    delete_response.raise_for_status()
                elif response.status_code not in {404}:
                    response.raise_for_status()

                create_payload = {
                    "vectors": {
                        "size": self.embedding_provider.dimension,
                        "distance": "Cosine",
                    }
                }
                response = client.put(
                    f"{self.endpoint}/collections/{self.collection_name}",
                    json=create_payload,
                    headers=self._headers(),
                )
                response.raise_for_status()
                return True
        except httpx.HTTPError as e:
            logger.error(f"Qdrant collection setup failed: {e}")
            return False

    def _point_id(self, chunk: CodeChunk) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk.stable_key))

    def delete_repo(self, repo_name: str) -> bool:
        """Delete all points for a repo before re-indexing."""
        try:
            if not self.ensure_collection():
                return False
            payload = {
                "filter": {
                    "must": [
                        {"key": "repo", "match": {"value": repo_name}},
                    ]
                }
            }
            with httpx.Client(timeout=self.timeout_seconds, trust_env=False) as client:
                response = client.post(
                    f"{self.endpoint}/collections/{self.collection_name}/points/delete",
                    json=payload,
                    headers=self._headers(),
                )
                response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error(f"Qdrant delete failed for {repo_name}: {e}")
            return False

    def index_chunks(self, repo_name: str, chunks: list[CodeChunk]) -> IndexStatus:
        """Index source chunks into Qdrant using the configured embedding provider."""
        started = utc_now()
        try:
            if not self.ensure_collection():
                return IndexStatus(
                    index_name=repo_name,
                    kind=IndexKind.QDRANT,
                    ready=False,
                    detail={"error": "Failed to ensure collection"},
                )

            if not chunks:
                self.delete_repo(repo_name)
                return IndexStatus(
                    index_name=repo_name,
                    kind=IndexKind.QDRANT,
                    ready=True,
                    last_full_sync_at=started,
                    detail={"chunks_indexed": 0, "message": "no indexable chunks"},
                )

            embeddings = self.embedding_provider.embed_documents(
                [self._embed_text(chunk.path, chunk.content) for chunk in chunks]
            )
            if len(embeddings) != len(chunks):
                raise RuntimeError(
                    f"embedding count mismatch: chunks={len(chunks)} embeddings={len(embeddings)}"
                )

            self.delete_repo(repo_name)

            points = []
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                points.append({
                    "id": self._point_id(chunk),
                    "vector": embedding,
                    "payload": {
                        "repo": repo_name,
                        "path": chunk.path,
                        "language": chunk.language,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "sha256": chunk.sha256,
                        "content_preview": chunk.content[:500],
                    },
                })

            batch_size = 128
            with httpx.Client(timeout=self.timeout_seconds, trust_env=False) as client:
                for start in range(0, len(points), batch_size):
                    response = client.put(
                        f"{self.endpoint}/collections/{self.collection_name}/points",
                        json={"points": points[start : start + batch_size]},
                        headers=self._headers(),
                    )
                    response.raise_for_status()

            return IndexStatus(
                index_name=repo_name,
                kind=IndexKind.QDRANT,
                ready=True,
                last_full_sync_at=started,
                detail={
                    "collection": self.collection_name,
                    "chunks_indexed": len(points),
                    "embedding_dimension": self.embedding_provider.dimension,
                },
            )
        except Exception as e:
            logger.error(f"Qdrant chunk index failed for {repo_name}: {e}")
            return IndexStatus(
                index_name=repo_name,
                kind=IndexKind.QDRANT,
                ready=False,
                detail={"error": str(e)},
            )

    def index_code_files(
        self,
        repo_name: str,
        files: list[dict],
        embeddings: list[list[float]],
    ) -> IndexStatus:
        """
        索引代码文件向量

        Args:
            repo_name: 仓库名称
            files: 文件列表 [{"path": "...", "content": "...", "language": "..."}]
            embeddings: 对应的 embedding 向量列表

        Returns:
            IndexStatus: 索引状态
        """
        try:
            if not self.ensure_collection():
                return IndexStatus(
                    index_name=repo_name,
                    kind=IndexKind.QDRANT,
                    ready=False,
                    detail={"error": "Failed to ensure collection"},
                )

            points = []
            for i, (file_info, embedding) in enumerate(zip(files, embeddings, strict=True)):
                stable_key = (
                    f"{repo_name}:{file_info.get('path')}:{file_info.get('sha256', '')}:{i}"
                )
                points.append({
                    "id": str(uuid.uuid5(uuid.NAMESPACE_URL, stable_key)),
                    "vector": embedding,
                    "payload": {
                        "repo": repo_name,
                        "path": file_info.get("path"),
                        "language": file_info.get("language", "unknown"),
                        "content_preview": file_info.get("content", "")[:500],
                    },
                })

            with httpx.Client(timeout=self.timeout_seconds, trust_env=False) as client:
                response = client.put(
                    f"{self.endpoint}/collections/{self.collection_name}/points",
                    json={"points": points},
                    headers=self._headers(),
                )
                response.raise_for_status()

            return IndexStatus(
                index_name=repo_name,
                kind=IndexKind.QDRANT,
                ready=True,
                last_full_sync_at=utc_now(),
                detail={"files_indexed": len(points)},
            )
        except httpx.HTTPError as e:
            logger.error(f"Qdrant index failed for {repo_name}: {e}")
            return IndexStatus(
                index_name=repo_name,
                kind=IndexKind.QDRANT,
                ready=False,
                detail={"error": str(e)},
            )

    def search_similar(
        self,
        query_vector: list[float],
        repo_name: str | None = None,
        limit: int = 10,
    ) -> dict:
        """
        向量相似度搜索

        Args:
            query_vector: 查询向量
            repo_name: 限定仓库名（可选）
            limit: 结果数量限制

        Returns:
            搜索结果字典
        """
        try:
            payload = {
                "vector": query_vector,
                "limit": limit,
            }

            if repo_name:
                payload["filter"] = {
                    "must": [
                        {"key": "repo", "match": {"value": repo_name}}
                    ]
                }
            payload["with_payload"] = True

            with httpx.Client(timeout=self.timeout_seconds, trust_env=False) as client:
                response = client.post(
                    f"{self.endpoint}/collections/{self.collection_name}/points/search",
                    json=payload,
                    headers=self._headers(),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Qdrant search failed: {e}")
            return {"error": str(e), "result": []}

    def search_similar_text(
        self,
        query: str,
        repo_name: str | None = None,
        limit: int = 10,
        *,
        min_score: float = 0.12,
        candidate_multiplier: int = 5,
    ) -> dict:
        """Embed a text query and search indexed code chunks.

        Vector hits are re-ranked with lexical overlap against path/preview so
        weak hash embeddings do not surface unrelated corpora.
        """
        from rootseeker.code_index.search_query import extract_code_identifiers, lexical_overlap_score

        fetch_limit = max(limit, min(100, max(limit, 1) * max(1, candidate_multiplier)))
        vector = self.embedding_provider.embed_query(query)
        raw = self.search_similar(vector, repo_name=repo_name, limit=fetch_limit)
        if "error" in raw:
            return raw

        points = raw.get("result") or []
        if not isinstance(points, list):
            return raw

        ranked: list[dict] = []
        noise_markers = (
            "fuzzdb/",
            "zaphomefiles/",
            "/static/",
            "webjars/",
            "node_modules/",
            ".min.js",
            ".min.css",
            "messages_",
            "chunk-",
        )
        for point in points:
            if not isinstance(point, dict):
                continue
            payload = point.get("payload") or {}
            if not isinstance(payload, dict):
                payload = {}
            vector_score = float(point.get("score") or 0.0)
            path = str(payload.get("path") or "")
            path_norm = path.replace("\\", "/").lower()
            if any(marker in path_norm for marker in noise_markers):
                continue
            preview = str(payload.get("content_preview") or payload.get("content") or "")
            lexical = lexical_overlap_score(query, path, preview)
            combined = (0.45 * vector_score) + (0.55 * lexical)
            # Drop weak vector-only noise when the query looks like a code symbol.
            if lexical <= 0.0 and extract_code_identifiers(query):
                continue
            if lexical <= 0.0 and vector_score < max(min_score, 0.25):
                continue
            if combined < min_score and lexical < 0.34:
                continue
            enriched = dict(point)
            enriched["score"] = combined
            enriched["vector_score"] = vector_score
            enriched["lexical_score"] = lexical
            ranked.append(enriched)

        ranked.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
        return {
            **raw,
            "result": ranked[:limit],
            "candidates": len(points),
            "reranked": True,
        }

    @staticmethod
    def _embed_text(path: str, content: str) -> str:
        return f"{path}\n{content}"

    def get_status(self, repo_name: str | None = None) -> IndexStatus:
        """获取索引状态"""
        try:
            with httpx.Client(timeout=self.timeout_seconds, trust_env=False) as client:
                response = client.get(
                    f"{self.endpoint}/collections/{self.collection_name}",
                    headers=self._headers(),
                )
                response.raise_for_status()
                data = response.json()

            result = data.get("result", {})
            return IndexStatus(
                index_name=repo_name or self.collection_name,
                kind=IndexKind.QDRANT,
                ready=result.get("status") == "green",
                detail=data,
            )
        except httpx.HTTPError as e:
            logger.error(f"Qdrant status check failed: {e}")
            return IndexStatus(
                index_name=repo_name or "qdrant-default",
                kind=IndexKind.QDRANT,
                ready=False,
                detail={"error": str(e)},
            )


def get_qdrant_status(index_name: str = "qdrant-default") -> IndexStatus:
    """向后兼容的状态查询函数"""
    indexer = QdrantIndexer()
    return indexer.get_status(index_name)
