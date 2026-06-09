from rootseeker.contracts.service_catalog import ServiceCatalogEntry
from rootseeker.service_catalog import (
    ServiceCatalogStore,
    build_catalog_audit_event,
    load_entries_into_store,
    resolve_log_sources,
    resolve_repositories,
    resolve_service,
    resolve_trace_sources,
)


def test_catalog_store_loader_and_resolver() -> None:
    store = ServiceCatalogStore()
    entry = ServiceCatalogEntry(
        tenant="demo",
        environment="prod",
        service_name="svc",
        display_name="Svc",
        repositories=[{"name": "svc-repo"}],
        log_sources=[{"source_id": "ls-1"}],
        trace_sources=[{"source_id": "tr-1"}],
    )
    load_entries_into_store([entry], store)
    got = resolve_service(store, tenant="demo", environment="prod", service_name="svc")
    assert got is not None
    assert resolve_log_sources(got)[0]["source_id"] == "ls-1"
    assert resolve_trace_sources(got)[0]["source_id"] == "tr-1"
    assert resolve_repositories(got)[0].name == "svc-repo"


def test_catalog_audit_event_shape() -> None:
    evt = build_catalog_audit_event(
        case_id="c1",
        actor="flow",
        service_name="svc",
        tenant="demo",
        environment="prod",
    )
    assert evt.action == "catalog.resolve_service"
    assert evt.detail["case_id"] == "c1"
