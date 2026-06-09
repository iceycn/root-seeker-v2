from __future__ import annotations

from rootseeker.contracts.service_catalog import ServiceCatalogEntry
from rootseeker.service_catalog.store import ServiceCatalogStore

__all__ = ["load_entries_into_store"]


def load_entries_into_store(entries: list[ServiceCatalogEntry], store: ServiceCatalogStore) -> None:
    for entry in entries:
        store.upsert(entry)
