from __future__ import annotations

from rootseeker.contracts.repository import RepositoryRef
from rootseeker.contracts.service_catalog import ServiceCatalogEntry

__all__ = ["resolve_log_sources", "resolve_repositories", "resolve_trace_sources"]


def resolve_log_sources(entry: ServiceCatalogEntry) -> list[dict]:
    return list(entry.log_sources)


def resolve_repositories(entry: ServiceCatalogEntry) -> list[RepositoryRef]:
    return [
        RepositoryRef.model_validate(repo) if isinstance(repo, dict) else repo
        for repo in entry.repositories
    ]


def resolve_trace_sources(entry: ServiceCatalogEntry) -> list[dict]:
    return list(entry.trace_sources)
