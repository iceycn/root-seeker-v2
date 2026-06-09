from rootseeker.contracts.service_catalog import ServiceCatalogEntry
from rootseeker.service_catalog import MemoryServiceCatalog


def test_resolve_seeded_services() -> None:
    cat = MemoryServiceCatalog.seeded_default()
    e = cat.resolve("demo", "prod", "order-service")
    assert e is not None
    assert e.service_name == "order-service"


def test_upsert_overrides() -> None:
    cat = MemoryServiceCatalog()
    cat.upsert(
        ServiceCatalogEntry(
            tenant="t",
            environment="e",
            service_name="svc",
            display_name="S",
        )
    )
    assert cat.resolve("t", "e", "svc") is not None
