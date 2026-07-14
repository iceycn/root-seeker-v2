from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rootseeker.bootstrap import DevRuntime

__all__ = ["build_runtime_health"]


def build_runtime_health(runtime: DevRuntime) -> dict[str, Any]:
    components = {
        "skills": _count_component(lambda: len(runtime.skill_registry.list_skills())),
        "plugins": _count_component(lambda: len(runtime.plugin_registry.list_plugins())),
        "tools": _count_component(lambda: len(runtime.tool_registry.list_specs())),
        "cases": _count_component(lambda: _store_count(runtime.case_store)),
        "audit": _count_component(lambda: runtime.audit_log.count()),
        "checkpoints": _count_component(lambda: _store_count(runtime.flow_checkpoint_store)),
    }
    status = "ok" if all(item["status"] == "ok" for item in components.values()) else "degraded"
    return {"status": status, "components": components}


def _store_count(store: object) -> int:
    count = getattr(store, "count", None)
    if callable(count):
        return int(count())
    list_all = getattr(store, "list_all", None)
    if callable(list_all):
        return len(list_all())
    list_records = getattr(store, "list_records", None)
    if callable(list_records):
        return len(list_records(limit=-1))
    raise AttributeError(f"{type(store).__name__} has no count/list_all/list_records")


def _count_component(counter) -> dict[str, Any]:
    try:
        return {"status": "ok", "count": int(counter())}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
