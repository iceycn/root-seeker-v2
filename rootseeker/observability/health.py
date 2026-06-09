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
        "cases": _count_component(lambda: len(runtime.case_store.list_all())),
        "audit": _count_component(lambda: runtime.audit_log.count()),
        "checkpoints": _count_component(
            lambda: len(runtime.flow_checkpoint_store.list_records(limit=10000))
        ),
    }
    status = "ok" if all(item["status"] == "ok" for item in components.values()) else "degraded"
    return {"status": status, "components": components}


def _count_component(counter) -> dict[str, Any]:
    try:
        return {"status": "ok", "count": int(counter())}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
