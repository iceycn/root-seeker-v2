"""JSON Schema definitions for internal MCP tools used by skill-driven argument planning."""

from __future__ import annotations

from typing import Any

__all__ = ["INTERNAL_TOOL_PARAMETER_SCHEMAS", "parameter_schema_for"]


INTERNAL_TOOL_PARAMETER_SCHEMAS: dict[str, dict[str, Any]] = {
    "incident.normalize": {
        "type": "object",
        "properties": {
            "payload": {
                "type": "object",
                "description": "Raw alert payload with title, service_name, message/symptom, source, metadata fields",
            }
        },
        "required": ["payload"],
    },
    "catalog.resolve_service": {
        "type": "object",
        "properties": {
            "tenant": {"type": "string"},
            "environment": {"type": "string"},
            "service_name": {"type": "string"},
        },
        "required": ["tenant", "environment", "service_name"],
    },
    "catalog.get_log_sources": {
        "type": "object",
        "properties": {
            "tenant": {"type": "string"},
            "environment": {"type": "string"},
            "service_name": {"type": "string"},
        },
        "required": ["tenant", "environment", "service_name"],
    },
    "log.query_by_trace_id": {
        "type": "object",
        "properties": {
            "trace_id": {"type": "string"},
            "service_name": {"type": "string"},
        },
        "required": ["trace_id"],
    },
    "log.query_by_template": {
        "type": "object",
        "properties": {
            "template_id": {"type": "string"},
            "service_name": {"type": "string"},
        },
        "required": ["template_id"],
    },
    "trace.get_chain": {
        "type": "object",
        "properties": {"trace_id": {"type": "string"}},
        "required": ["trace_id"],
    },
    "code.search": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    "code.read": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "repo": {"type": "string"},
            "line": {"type": "integer", "description": "Fault line from the stack frame"},
            "methods": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Call-chain method names to extract from this file",
            },
            "start_line": {"type": "integer"},
            "end_line": {"type": "integer"},
        },
        "required": ["path"],
    },
    "code.find_callers": {
        "type": "object",
        "properties": {
            "call_chain": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Runtime call-chain frames from incident.normalize",
            },
            "class_name": {"type": "string"},
            "method_name": {"type": "string"},
            "file_path": {"type": "string"},
            "line": {"type": "integer"},
            "repo": {"type": "string"},
            "service_name": {"type": "string"},
            "max_depth": {"type": "integer"},
            "limit": {"type": "integer"},
            "prefer_graph": {
                "type": "boolean",
                "description": "Prefer GitNexus knowledge graph before Zoekt fallback",
            },
        },
    },
    "graph.impact": {
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "direction": {"type": "string", "description": "upstream|downstream"},
            "repo": {"type": "string"},
            "file": {"type": "string"},
            "uid": {"type": "string"},
            "kind": {"type": "string"},
        },
        "required": ["symbol"],
    },
    "graph.context": {
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "repo": {"type": "string"},
            "file": {"type": "string"},
            "uid": {"type": "string"},
        },
        "required": ["symbol"],
    },
    "graph.query": {
        "type": "object",
        "properties": {
            "search_query": {"type": "string"},
            "query": {"type": "string"},
            "repo": {"type": "string"},
        },
    },
    "graph.cypher": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "repo": {"type": "string"},
        },
        "required": ["query"],
    },
    "graph.trace": {
        "type": "object",
        "properties": {
            "source": {"type": "string"},
            "target": {"type": "string"},
            "repo": {"type": "string"},
        },
        "required": ["source", "target"],
    },
    "graph.list_repos": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
            "offset": {"type": "integer"},
        },
    },
    "graph.detect_changes": {
        "type": "object",
        "properties": {"repo": {"type": "string"}},
    },
    "index.get_status": {"type": "object", "properties": {}},
    "repo.list": {"type": "object", "properties": {}},
    "notify.send": {
        "type": "object",
        "properties": {
            "channel": {"type": "string"},
            "message": {"type": "string"},
        },
        "required": ["channel", "message"],
    },
}


def _k8s_query_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "namespace": {
                "type": "string",
                "description": "Kubernetes namespace. Empty uses ROOTSEEKER_K8S_NAMESPACE, then all namespaces.",
            },
            "pod": {"type": "string", "description": "Pod name"},
            "service_name": {
                "type": "string",
                "description": "Match app or app.kubernetes.io/name label, or pod name prefix",
            },
            "container": {"type": "string"},
            "label_selector": {"type": "string"},
            "since_minutes": {
                "type": "integer",
                "description": "Log window override in minutes. Default ROOTSEEKER_K8S_LOG_WINDOW_MINUTES (5).",
            },
            "tail_lines": {"type": "integer", "description": "Max log lines per container"},
        },
    }


INTERNAL_TOOL_PARAMETER_SCHEMAS["k8s.status"] = {"type": "object", "properties": {}}

for _k8s_tool_name in (
    "k8s.read_cpu",
    "k8s.read_memory",
    "k8s.read_disk",
    "k8s.read_logs",
    "k8s.collect_snapshot",
):
    INTERNAL_TOOL_PARAMETER_SCHEMAS[_k8s_tool_name] = _k8s_query_schema()


def parameter_schema_for(tool_name: str) -> dict[str, Any]:
    return dict(
        INTERNAL_TOOL_PARAMETER_SCHEMAS.get(tool_name, {"type": "object", "properties": {}})
    )
