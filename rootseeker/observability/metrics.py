from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from rootseeker.observability.health import build_runtime_health

if TYPE_CHECKING:
    from rootseeker.bootstrap import DevRuntime

__all__ = ["render_prometheus_metrics"]


def render_prometheus_metrics(runtime: DevRuntime) -> str:
    health = build_runtime_health(runtime)
    components = health.get("components", {})
    lines = [
        "# HELP rootseeker_up Runtime health status: 1 for ok, 0 for degraded.",
        "# TYPE rootseeker_up gauge",
        f"rootseeker_up {_bool_value(health.get('status') == 'ok')}",
        "# HELP rootseeker_component_up Component health status.",
        "# TYPE rootseeker_component_up gauge",
    ]
    for name, payload in sorted(components.items()):
        if not isinstance(payload, dict):
            continue
        status = str(payload.get("status", "unknown"))
        count = payload.get("count")
        if isinstance(count, (int, float)):
            lines.extend(
                [
                    f"# HELP rootseeker_{name}_total RootSeeker {name} total.",
                    f"# TYPE rootseeker_{name}_total gauge",
                    f'rootseeker_{name}_total {count}',
                ]
            )
        lines.extend(
            [
                f'rootseeker_component_up{{component="{_escape_label(name)}",status="{_escape_label(status)}"}} {_bool_value(status == "ok")}',
            ]
        )
    lines.extend(_render_runtime_activity_metrics(runtime))
    return "\n".join(lines) + "\n"


def _bool_value(value: bool) -> int:
    return 1 if value else 0


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _render_runtime_activity_metrics(runtime: DevRuntime) -> list[str]:
    lines: list[str] = []
    events = runtime.audit_log.list_events(limit=-1)

    action_counts = Counter(event.action for event in events)
    lines.extend(
        [
            "# HELP rootseeker_audit_events_total Audit events by action.",
            "# TYPE rootseeker_audit_events_total counter",
        ]
    )
    for action, count in sorted(action_counts.items()):
        lines.append(f'rootseeker_audit_events_total{{action="{_escape_label(action)}"}} {count}')

    tool_counts: Counter[tuple[str, str, str]] = Counter()
    for event in events:
        if event.action not in {"agent.tool.trace", "agent.tool.error", "mcp.invoke"}:
            continue
        tool_name = str(event.detail.get("tool_name", "unknown"))
        ok = str(bool(event.detail.get("ok", event.action == "agent.tool.trace"))).lower()
        error_code = str(event.detail.get("error_code") or "")
        if not error_code and isinstance(event.detail.get("error"), dict):
            error_code = str(event.detail["error"].get("code") or "")
        tool_counts[(tool_name, ok, error_code)] += 1
    lines.extend(
        [
            "# HELP rootseeker_agent_tool_events_total Agent and MCP tool events by tool, status and error.",
            "# TYPE rootseeker_agent_tool_events_total counter",
        ]
    )
    for (tool_name, ok, error_code), count in sorted(tool_counts.items()):
        lines.append(
            "rootseeker_agent_tool_events_total"
            f'{{tool_name="{_escape_label(tool_name)}",ok="{ok}",error_code="{_escape_label(error_code)}"}} {count}'
        )

    approval_counts = Counter(item.status.value for item in runtime.approval_store.list(limit=100000))
    lines.extend(
        [
            "# HELP rootseeker_approvals_total Approval requests by status.",
            "# TYPE rootseeker_approvals_total gauge",
        ]
    )
    for status in ("pending", "approved", "rejected"):
        lines.append(f'rootseeker_approvals_total{{status="{status}"}} {approval_counts.get(status, 0)}')
    return lines
