from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from rootseeker.contracts.common import RootSeekerModel, utc_now

__all__ = [
    "LogQueryByTemplateRequest",
    "LogQueryByTraceIdRequest",
    "LogQueryTemplate",
    "LogRecord",
    "LogQueryResult",
]


class LogQueryTemplate(RootSeekerModel):
    """Registered template: validated parameters render to provider-specific query."""

    template_id: str = Field(min_length=1)
    version: str = Field(default="1.0.0", min_length=1)
    parameter_schema: dict[str, Any] = Field(default_factory=dict)
    render_kind: str = Field(min_length=1, description="e.g. sls_sql, lucene")
    template_body: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class LogQueryByTraceIdRequest(RootSeekerModel):
    trace_id: str = Field(min_length=1)
    service_name: str | None = None
    time_from: datetime | None = None
    time_to: datetime | None = None
    limit: int = Field(default=200, ge=1, le=5000)


class LogQueryByTemplateRequest(RootSeekerModel):
    template_id: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    time_from: datetime | None = None
    time_to: datetime | None = None
    limit: int = Field(default=200, ge=1, le=5000)


class LogRecord(RootSeekerModel):
    """Single normalized log row (store-specific fields in raw)."""

    timestamp: datetime = Field(default_factory=utc_now)
    message: str = ""
    level: str | None = None
    trace_id: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class LogQueryResult(RootSeekerModel):
    query_key: str = Field(min_length=1, description="Stable id for audit: trace/template/sql hash")
    records: list[LogRecord] = Field(default_factory=list)
    truncated: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
