"""Alibaba Cloud SLS (Log Service) adapter for production log queries.

This adapter provides real HTTP integration with Alibaba Cloud SLS API.
It supports querying logs by trace ID, template, and custom queries.

Environment variables:
- SLS_ACCESS_KEY_ID: Alibaba Cloud AccessKey ID
- SLS_ACCESS_KEY_SECRET: Alibaba Cloud AccessKey Secret
- SLS_ENDPOINT: SLS endpoint (e.g., cn-hangzhou.log.aliyuncs.com)
- SLS_PROJECT: Default SLS project name
- SLS_LOGSTORE: Default logstore name
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from rootseeker.contracts.common import utc_now

__all__ = ["SlsLogAdapter", "SlsConfig"]


@dataclass
class SlsConfig:
    """Configuration for SLS adapter."""

    access_key_id: str = ""
    access_key_secret: str = ""
    endpoint: str = ""
    project: str = ""
    logstore: str = ""
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> SlsConfig:
        """Load configuration from environment variables."""
        return cls(
            access_key_id=os.getenv("SLS_ACCESS_KEY_ID", ""),
            access_key_secret=os.getenv("SLS_ACCESS_KEY_SECRET", ""),
            endpoint=os.getenv("SLS_ENDPOINT", "cn-hangzhou.log.aliyuncs.com"),
            project=os.getenv("SLS_PROJECT", ""),
            logstore=os.getenv("SLS_LOGSTORE", ""),
        )

    def is_configured(self) -> bool:
        """Check if all required fields are set."""
        return bool(
            self.access_key_id
            and self.access_key_secret
            and self.endpoint
            and self.project
            and self.logstore
        )


@dataclass
class SlsLogAdapter:
    """Production adapter for Alibaba Cloud SLS log queries.

    Implements the InternalToolAdapter protocol for log query methods.
    Uses SLS GetLogs API for querying log data.
    """

    config: SlsConfig = field(default_factory=SlsConfig.from_env)
    _client: httpx.Client | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.config.is_configured():
            self._client = httpx.Client(timeout=self.config.timeout_seconds)

    def _sign_request(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        body: str = "",
    ) -> str:
        """Generate SLS signature for API request."""
        # Build canonicalized string
        content_md5 = hashlib.md5(body.encode()).hexdigest()
        date = headers.get("Date", "")
        canonicalized_resource = path

        # Build string to sign
        string_to_sign = f"{method}\n{content_md5}\n{headers.get('Content-Type', '')}\n{date}\n"
        for key, value in sorted(headers.items()):
            if key.startswith("x-log-") or key.startswith("x-acs-"):
                string_to_sign += f"{key}:{value}\n"
        string_to_sign += canonicalized_resource

        # Calculate signature
        signature = hmac.new(
            self.config.access_key_secret.encode(),
            string_to_sign.encode(),
            hashlib.sha1,
        ).digest()
        return base64.b64encode(signature).decode()

    def _build_headers(
        self,
        method: str,
        path: str,
        body: str = "",
    ) -> dict[str, str]:
        """Build request headers with authentication."""
        now = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S GMT")
        headers = {
            "Date": now,
            "Content-Type": "application/json",
            "x-log-apiversion": "0.6.0",
            "x-log-signaturemethod": "hmac-sha1",
        }
        signature = self._sign_request(method, path, headers, body)
        headers["Authorization"] = f"LOG {self.config.access_key_id}:{signature}"
        return headers

    def _log_result_dict(
        self,
        query_key: str,
        *,
        records: list[Any],
        truncated: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Shape compatible with rootseeker.contracts.log_query.LogQueryResult."""
        return {
            "query_key": query_key,
            "records": records,
            "truncated": truncated,
            "metadata": dict(metadata or {}),
        }

    def _normalize_record(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            return {"message": str(raw), "raw": {"value": raw}}

        message = (
            raw.get("message")
            or raw.get("msg")
            or raw.get("content")
            or raw.get("__topic__")
            or json.dumps(raw, ensure_ascii=False, sort_keys=True)
        )
        level = raw.get("level") or raw.get("severity") or raw.get("log_level")
        trace_id = raw.get("trace_id") or raw.get("traceId") or raw.get("traceID")
        timestamp_raw = raw.get("timestamp") or raw.get("__time__") or raw.get("time")
        record: dict[str, Any] = {
            "message": str(message),
            "level": str(level) if level is not None else None,
            "trace_id": str(trace_id) if trace_id is not None else None,
            "raw": raw,
        }
        if timestamp_raw is not None:
            try:
                if isinstance(timestamp_raw, int | float) or str(timestamp_raw).isdigit():
                    record["timestamp"] = datetime.fromtimestamp(float(timestamp_raw), UTC).isoformat()
                else:
                    record["timestamp"] = str(timestamp_raw)
            except Exception:
                record["timestamp"] = utc_now().isoformat()
        return record

    def _normalize_records(self, records: list[Any]) -> list[dict[str, Any]]:
        return [self._normalize_record(item) for item in records]

    def _query_logs(
        self,
        query: str,
        from_time: int,
        to_time: int,
        logstore: str | None = None,
    ) -> dict[str, Any]:
        """Execute log query against SLS.

        Args:
            query: SLS query string
            from_time: Start timestamp (Unix seconds)
            to_time: End timestamp (Unix seconds)
            logstore: Optional logstore override

        Returns:
            Query result with logs and metadata
        """
        if not self._client:
            return self._not_configured_response(query)

        store = logstore or self.config.logstore
        path = f"/logstores/{store}?type=log&from={from_time}&to={to_time}"
        body = json.dumps({"query": query})

        url = f"https://{self.config.project}.{self.config.endpoint}{path}"
        headers = self._build_headers("POST", path, body)

        try:
            response = self._client.post(url, headers=headers, content=body)
            response.raise_for_status()
            data = response.json()

            count = data.get("count", 0)
            return self._log_result_dict(
                f"sls:{hashlib.md5(query.encode()).hexdigest()[:8]}",
                records=self._normalize_records(data.get("logs", [])),
                truncated=count >= 100,
                metadata={"total": count, "query": query, "configured": True},
            )
        except Exception as e:
            return self._log_result_dict(
                f"sls:error:{hashlib.md5(query.encode()).hexdigest()[:8]}",
                records=[],
                truncated=False,
                metadata={"error": str(e), "query": query, "configured": True},
            )

    def _not_configured_response(self, query: str) -> dict[str, Any]:
        """Explicit error when credentials / project are missing (no synthetic log lines)."""
        return self._log_result_dict(
            f"sls:unconfigured:{hashlib.md5(query.encode()).hexdigest()[:8]}",
            records=[],
            truncated=False,
            metadata={
                "configured": False,
                "error": (
                    "SLS is not configured: set SLS_ACCESS_KEY_ID, SLS_ACCESS_KEY_SECRET, "
                    "SLS_ENDPOINT, SLS_PROJECT, SLS_LOGSTORE"
                ),
                "query": query,
            },
        )

    def query_logs_by_trace_id(
        self,
        trace_id: str,
        service_name: str | None = None,
        time_range_minutes: int = 30,
    ) -> dict[str, Any]:
        """Query logs by trace ID.

        Args:
            trace_id: Distributed trace ID
            service_name: Optional service filter
            time_range_minutes: Query time range in minutes

        Returns:
            Log query result
        """
        import time

        to_time = int(time.time())
        from_time = to_time - time_range_minutes * 60

        # Build SLS query
        query = f'trace_id: "{trace_id}"'
        if service_name:
            query += f' AND service_name: "{service_name}"'

        return self._query_logs(query, from_time, to_time)

    def query_logs_by_template(
        self,
        template_id: str,
        service_name: str | None = None,
        time_range_minutes: int = 30,
    ) -> dict[str, Any]:
        """Query logs by log template/pattern.

        Args:
            template_id: Log template ID
            service_name: Optional service filter
            time_range_minutes: Query time range in minutes

        Returns:
            Log query result
        """
        import time

        to_time = int(time.time())
        from_time = to_time - time_range_minutes * 60

        query = f'template_id: "{template_id}"'
        if service_name:
            query += f' AND service_name: "{service_name}"'

        return self._query_logs(query, from_time, to_time)

    def query_logs(
        self,
        query: str,
        from_time: int | None = None,
        to_time: int | None = None,
        time_range_minutes: int = 30,
    ) -> dict[str, Any]:
        """Execute custom log query.

        Args:
            query: SLS query string
            from_time: Start timestamp (Unix seconds)
            to_time: End timestamp (Unix seconds)
            time_range_minutes: Default time range if not specified

        Returns:
            Log query result
        """
        import time

        if to_time is None:
            to_time = int(time.time())
        if from_time is None:
            from_time = to_time - time_range_minutes * 60

        return self._query_logs(query, from_time, to_time)

    def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            self._client.close()
            self._client = None
