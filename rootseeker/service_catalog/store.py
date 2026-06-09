from __future__ import annotations

from rootseeker.contracts.service_catalog import ServiceCatalogEntry

__all__ = ["ServiceCatalogStore"]


class ServiceCatalogStore:
    """Versionless in-memory store used by the service catalog resolver."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str, str], ServiceCatalogEntry] = {}

    @staticmethod
    def _key(tenant: str, environment: str, service_name: str) -> tuple[str, str, str]:
        return (tenant.lower().strip(), environment.lower().strip(), service_name.lower().strip())

    def upsert(self, entry: ServiceCatalogEntry) -> None:
        self._items[self._key(entry.tenant, entry.environment, entry.service_name)] = entry

    def get(self, tenant: str, environment: str, service_name: str) -> ServiceCatalogEntry | None:
        return self._items.get(self._key(tenant, environment, service_name))

    def list_all(self) -> list[ServiceCatalogEntry]:
        return list(self._items.values())
