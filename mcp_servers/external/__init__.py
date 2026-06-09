"""External MCP adapters for production data sources."""

from __future__ import annotations

from mcp_servers.external.composite_adapter import CompositeProductionAdapter, ProductionConfig
from mcp_servers.external.jaeger_adapter import JaegerConfig, JaegerTraceAdapter
from mcp_servers.external.sls_adapter import SlsConfig, SlsLogAdapter
from mcp_servers.external.zoekt_adapter import ZoektCodeAdapter, ZoektConfig

__all__ = [
    "CompositeProductionAdapter",
    "JaegerConfig",
    "JaegerTraceAdapter",
    "ProductionConfig",
    "SlsConfig",
    "SlsLogAdapter",
    "ZoektCodeAdapter",
    "ZoektConfig",
]
