"""Jaeger Trace adapter for production trace chain queries.

This adapter provides real HTTP integration with Jaeger trace backend.
It supports querying trace chains by trace ID and extracting span information.

Environment variables:
- JAEGER_ENDPOINT: Jaeger API endpoint (e.g., http://jaeger:16686)
- JAEGER_TIMEOUT_SECONDS: Request timeout (default: 10.0)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

__all__ = ["JaegerTraceAdapter", "JaegerConfig"]


@dataclass
class JaegerConfig:
    """Configuration for Jaeger adapter."""

    endpoint: str = ""
    timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> JaegerConfig:
        """Load configuration from environment variables."""
        return cls(
            endpoint=os.getenv("JAEGER_ENDPOINT", ""),
            timeout_seconds=float(os.getenv("JAEGER_TIMEOUT_SECONDS", "10.0")),
        )

    def is_configured(self) -> bool:
        """Check if endpoint is explicitly configured."""
        return bool(self.endpoint)


@dataclass
class JaegerTraceAdapter:
    """Production adapter for Jaeger trace queries.

    Implements trace chain retrieval from Jaeger backend.
    """

    config: JaegerConfig = field(default_factory=JaegerConfig.from_env)
    _client: httpx.Client | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.config.is_configured():
            self._client = httpx.Client(timeout=self.config.timeout_seconds)

    def get_trace_chain(self, trace_id: str) -> dict[str, Any]:
        """Fetch trace chain from Jaeger.

        Args:
            trace_id: Jaeger trace ID (hex string)

        Returns:
            Trace chain data with spans
        """
        if not self._client:
            return self._not_configured_trace_chain(trace_id)

        # Jaeger API: /api/traces/{trace_id}
        url = f"{self.config.endpoint.rstrip('/')}/api/traces/{trace_id}"

        try:
            response = self._client.get(url)
            response.raise_for_status()
            data = response.json()

            # Transform Jaeger response to our format
            return self._transform_jaeger_response(trace_id, data)
        except Exception as e:
            return {
                "trace_id": trace_id,
                "spans": [],
                "error": str(e),
            }

    def _transform_jaeger_response(self, trace_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Transform Jaeger API response to internal format."""
        spans = []
        trace_data = data.get("data", [])

        if trace_data:
            for trace in trace_data:
                for span in trace.get("spans", []):
                    spans.append(
                        {
                            "span_id": span.get("spanID", ""),
                            "parent_span_id": span.get("parentSpanID", ""),
                            "operation_name": span.get("operationName", ""),
                            "service_name": span.get("process", {}).get("serviceName", ""),
                            "start_ms": span.get("startTime", 0) // 1000,  # Convert to milliseconds
                            "duration_ms": span.get("duration", 0) // 1000,
                            "tags": span.get("tags", []),
                            "logs": span.get("logs", []),
                        }
                    )

        return {
            "trace_id": trace_id,
            "spans": spans,
            "total_spans": len(spans),
        }

    def _not_configured_trace_chain(self, trace_id: str) -> dict[str, Any]:
        """No synthetic spans when JAEGER_ENDPOINT is unset."""
        return {
            "trace_id": trace_id,
            "spans": [],
            "total_spans": 0,
            "configured": False,
            "error": "Jaeger is not configured: set JAEGER_ENDPOINT",
        }

    def search_traces(
        self,
        service_name: str,
        operation: str | None = None,
        limit: int = 20,
        lookback_minutes: int = 60,
    ) -> dict[str, Any]:
        """Search for traces by service and operation.

        Args:
            service_name: Service name to search
            operation: Optional operation name filter
            limit: Maximum number of traces to return
            lookback_minutes: Time range to search

        Returns:
            List of matching traces
        """
        if not self._client:
            return self._not_configured_search_traces()

        url = f"{self.config.endpoint.rstrip('/')}/api/traces"
        params = {
            "service": service_name,
            "limit": limit,
            "lookback": f"{lookback_minutes}m",
        }
        if operation:
            params["operation"] = operation

        try:
            response = self._client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            traces = []
            for trace in data.get("data", []):
                trace_id = trace.get("traceID", "")
                traces.append(
                    {
                        "trace_id": trace_id,
                        "span_count": len(trace.get("spans", [])),
                        "duration_ms": max(s.get("duration", 0) for s in trace.get("spans", []))
                        // 1000,
                    }
                )

            return {
                "traces": traces,
                "total": len(traces),
            }
        except Exception as e:
            return {
                "traces": [],
                "total": 0,
                "error": str(e),
            }

    def _not_configured_search_traces(self) -> dict[str, Any]:
        return {
            "traces": [],
            "total": 0,
            "configured": False,
            "error": "Jaeger is not configured: set JAEGER_ENDPOINT",
        }

    def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            self._client.close()
            self._client = None
