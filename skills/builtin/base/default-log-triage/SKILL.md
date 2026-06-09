---
name: Default log triage
slug: base/default-log-triage
description: Builtin default on-call log-chain triage; triggers bundled default flow plugin.
tags:
  - builtin
  - triage
  - log-chain
triggers:
  - webhook_alarm
  - replay
required_tools:
  - catalog.resolve_service
  - catalog.get_log_sources
  - log.query_by_trace_id
  - log.query_by_template
  - trace.get_chain
  - code.search
  - code.read
  - index.get_status
  - notify.send
source_kind: builtin
version: 1.0.0
flow_plugin_id: builtin.default_log_triage_flow
steps:
  - step_id: resolve-service
    name: Resolve service catalog
    action: catalog.resolve_service
    description: Map service_name to ServiceCatalogEntry and log sources
  - step_id: resolve-log-sources
    name: Resolve log sources
    action: catalog.get_log_sources
    description: Resolve concrete log sources for follow-up queries
  - step_id: query-logs-trace
    name: Query logs by trace
    action: log.query_by_trace_id
    description: Pull logs around incident window by trace id
  - step_id: query-logs-template
    name: Query logs by template
    action: log.query_by_template
    description: Pull logs by default error template for fallback evidence
  - step_id: trace-chain
    name: Fetch distributed trace chain
    action: trace.get_chain
  - step_id: code-search
    name: Search indexed code
    action: code.search
  - step_id: code-read
    name: Read key code snippet
    action: code.read
  - step_id: index-status
    name: Check index status
    action: index.get_status
  - step_id: notify
    name: Send notification
    action: notify.send
    description: Send final notification after report is generated

---

# Default log triage

This builtin skill declares the default investigation steps for production log-chain incidents.
Execution is performed by the bundled flow plugin `builtin.default_log_triage_flow`; each step
must invoke capabilities only through registered MCP tools (see architecture constraints).