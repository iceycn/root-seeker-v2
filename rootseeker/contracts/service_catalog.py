from __future__ import annotations

from typing import Any

from pydantic import Field

from rootseeker.contracts.common import RootSeekerModel

__all__ = ["ServiceCatalogEntry"]


class ServiceCatalogEntry(RootSeekerModel):
    """Resolved service row: tenant + environment + service_name -> data plane mapping."""

    tenant: str = Field(min_length=1)
    environment: str = Field(min_length=1)
    service_name: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    owner_team: str = ""
    runtime: str = ""
    language: str = ""
    repositories: list[dict[str, Any]] = Field(default_factory=list)
    log_sources: list[dict[str, Any]] = Field(default_factory=list)
    trace_sources: list[dict[str, Any]] = Field(default_factory=list)
    metric_sources: list[dict[str, Any]] = Field(default_factory=list)
    dependency_group: str = ""
    notification_targets: list[dict[str, Any]] = Field(default_factory=list)
    enabled_skills: list[str] = Field(default_factory=list)
    enabled_tools: list[str] = Field(default_factory=list)
    declared_by_plugin: str = ""
    allowed_mcp_tools: list[str] = Field(default_factory=list)
    catalog_version: str = ""
    audit_policy: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
