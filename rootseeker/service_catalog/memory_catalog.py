from __future__ import annotations

from rootseeker.contracts.service_catalog import ServiceCatalogEntry

__all__ = ["MemoryServiceCatalog"]


class MemoryServiceCatalog:
    """In-memory service directory for development; production may back this with a persistent store."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str, str], ServiceCatalogEntry] = {}

    @staticmethod
    def _key(tenant: str, environment: str, service_name: str) -> tuple[str, str, str]:
        return (
            tenant.lower().strip(),
            environment.lower().strip(),
            service_name.lower().strip(),
        )

    def upsert(self, entry: ServiceCatalogEntry) -> None:
        self._by_key[self._key(entry.tenant, entry.environment, entry.service_name)] = entry

    def resolve(
        self, tenant: str, environment: str, service_name: str
    ) -> ServiceCatalogEntry | None:
        return self._by_key.get(self._key(tenant, environment, service_name))

    def list_entries(self) -> list[ServiceCatalogEntry]:
        return list(self._by_key.values())

    def remove(self, tenant: str, environment: str, service_name: str) -> bool:
        return self._by_key.pop(self._key(tenant, environment, service_name), None) is not None

    @classmethod
    def seeded_default(cls) -> MemoryServiceCatalog:
        m = cls()
        m.upsert(
            ServiceCatalogEntry(
                tenant="demo",
                environment="prod",
                service_name="api-gateway",
                display_name="API Gateway",
                log_sources=[
                    {"type": "sls", "source_id": "lg-api", "project": "demo", "store": "ingress"}
                ],
                trace_sources=[{"type": "jaeger", "source_id": "tr-api"}],
            )
        )
        m.upsert(
            ServiceCatalogEntry(
                tenant="demo",
                environment="prod",
                service_name="order-service",
                display_name="Order Service",
                log_sources=[{"type": "sls", "source_id": "lg-order"}],
            )
        )
        return m
