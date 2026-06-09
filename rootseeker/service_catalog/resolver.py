from __future__ import annotations

from rootseeker.contracts.service_catalog import ServiceCatalogEntry
from rootseeker.service_catalog.store import ServiceCatalogStore

__all__ = ["resolve_service"]


def resolve_service(
    store: ServiceCatalogStore,
    *,
    tenant: str,
    environment: str,
    service_name: str,
) -> ServiceCatalogEntry | None:
    return store.get(tenant, environment, service_name)
