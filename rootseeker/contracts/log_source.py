from __future__ import annotations

from typing import Any

from pydantic import Field

from rootseeker.contracts.common import RootSeekerModel

__all__ = ["LogSource"]


class LogSource(RootSeekerModel):
    """Resolved log store locator; usually comes from ServiceCatalogEntry.log_sources[]."""

    type: str = Field(min_length=1, description="e.g. sls, elasticsearch, loki")
    source_id: str = Field(min_length=1)
    display_name: str = ""
    endpoint: str | None = None
    region: str | None = None
    project: str | None = None
    store: str | None = None
    topic: str | None = None
    default_query_language: str | None = None
    secret_ref: str | None = Field(default=None, description="SecretRef key, never inline secret")
    tags: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
