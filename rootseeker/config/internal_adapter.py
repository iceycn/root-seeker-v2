from __future__ import annotations

from mcp_servers.external.composite_adapter import CompositeProductionAdapter
from mcp_servers.internal.adapters import HttpInternalToolAdapter, InternalToolAdapter
from rootseeker.code_index.repo_sync import RepoSyncService
from rootseeker.infra_core import RootSeekerSettings
from rootseeker.service_catalog import MemoryServiceCatalog

__all__ = ["build_internal_adapter_from_settings"]


def _repo_sync_from_settings(
    settings: RootSeekerSettings,
    repo_sync_service: RepoSyncService | None,
) -> RepoSyncService:
    return repo_sync_service or RepoSyncService(
        base_path=settings.repo_base_path,
        zoekt_endpoint=settings.zoekt_endpoint,
        qdrant_endpoint=settings.qdrant_endpoint,
        qdrant_collection_name=settings.qdrant_collection_name,
        qdrant_api_key=settings.qdrant_api_key,
        zoekt_timeout_seconds=settings.zoekt_timeout_seconds,
        qdrant_timeout_seconds=settings.qdrant_timeout_seconds,
        enable_zoekt=settings.repo_enable_zoekt,
        enable_qdrant=settings.repo_enable_qdrant,
    )


def build_internal_adapter_from_settings(
    settings: RootSeekerSettings,
    *,
    catalog: MemoryServiceCatalog | None = None,
    repo_sync_service: RepoSyncService | None = None,
) -> InternalToolAdapter:
    if settings.internal_adapter_kind == "http":
        if not settings.internal_http_base_url:
            raise ValueError(
                "ROOTSEEKER_INTERNAL_HTTP_BASE_URL is required when internal_adapter_kind=http"
            )
        return HttpInternalToolAdapter(
            base_url=settings.internal_http_base_url,
            timeout_seconds=settings.internal_http_timeout_seconds,
        )
    return CompositeProductionAdapter.from_env(
        catalog=catalog or MemoryServiceCatalog.seeded_default(),
        repo_sync_service=_repo_sync_from_settings(settings, repo_sync_service),
    )
