from __future__ import annotations

import os
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["RootSeekerSettings"]


class RootSeekerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ROOTSEEKER_", extra="ignore")

    workspace_root: str = "."
    skills_builtin_subpath: str = "skills/builtin"
    plugins_builtin_subpath: str = "plugins/builtin"
    internal_adapter_kind: Literal["composite", "http"] = "composite"
    internal_http_base_url: str | None = None
    internal_http_timeout_seconds: float = 5.0

    # Storage backend. SQLite is opt-in so development smoke tests keep isolated memory stores.
    storage_backend: Literal["memory", "sqlite"] = "memory"
    sqlite_db_path: str = "data/rootseeker.db"
    cron_state_path: str = "data/cron/scheduler-state.json"

    # LLM report enhancement — OpenAI-compatible chat completions endpoint.
    llm_enabled: bool = True
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_provider_name: str = "openai_compatible"
    llm_timeout_seconds: float = 180.0
    llm_temperature: float = 0.2
    llm_max_evidence_items: int = 8

    # Agent LLM tool planning uses the same OpenAI-compatible provider, but keeps
    # tool execution inside McpGateway after validating model-produced calls.
    agent_llm_tool_planning_enabled: bool = True
    agent_llm_max_tool_calls: int = 6
    agent_llm_allow_write_tools: bool = False
    agent_tool_call_max_concurrency: int = 4
    agent_max_attempts: int = 2

    # Skill-driven flow: LLM reads tool skill docs to generate per-step arguments.
    skill_llm_argument_planning_enabled: bool = True
    skill_llm_argument_fallback_enabled: bool = True
    skill_context_max_chars: int = 12000
    skill_composer_default_flow: str = "flows/default-log-triage"

    # Approval policy orchestration. Off by default to keep local demo flows frictionless.
    approval_required_for_write_tools: bool = False
    approval_webhook_url: str | None = None
    approval_webhook_timeout_seconds: float = 5.0

    # Code Index — align with root_seek/config.yaml: zoekt.api_base_url, qdrant.url, qdrant.collection
    zoekt_endpoint: str | None = None
    zoekt_timeout_seconds: float = 30.0
    qdrant_endpoint: str | None = None
    qdrant_timeout_seconds: float = 30.0
    qdrant_api_key: str | None = None
    qdrant_collection_name: str = "code_chunks"

    # Repo Sync Configuration
    repo_base_path: str = "repos"
    repo_enable_zoekt: bool = True
    repo_enable_qdrant: bool = True
    repo_enable_gitnexus: bool = True

    # GitNexus knowledge graph (CLI or HTTP sidecar)
    gitnexus_endpoint: str | None = None
    gitnexus_command: str | None = None
    gitnexus_path_map: str | None = None
    gitnexus_timeout_seconds: float = 600.0
    gitnexus_analyze_timeout_seconds: float = 1800.0
    gitnexus_skip_agents_md: bool = True
    gitnexus_skip_skills: bool = True
    gitnexus_force: bool = False
    gitnexus_embeddings: bool = False

    @model_validator(mode="after")
    def apply_non_prefixed_code_index_env(self) -> RootSeekerSettings:
        """Honor root_seek-compatible env names on the app settings path too."""
        if self.zoekt_endpoint is None:
            self.zoekt_endpoint = (os.getenv("ZOEKT_ENDPOINT") or "").strip() or None
        if self.qdrant_endpoint is None:
            self.qdrant_endpoint = (os.getenv("QDRANT_ENDPOINT") or "").strip() or None
        if not self.qdrant_api_key:
            self.qdrant_api_key = (os.getenv("QDRANT_API_KEY") or "").strip() or None
        if self.gitnexus_endpoint is None:
            self.gitnexus_endpoint = (os.getenv("GITNEXUS_ENDPOINT") or "").strip() or None

        zoekt_timeout = (os.getenv("ZOEKT_TIMEOUT_SECONDS") or "").strip()
        if zoekt_timeout and "ROOTSEEKER_ZOEKT_TIMEOUT_SECONDS" not in os.environ:
            self.zoekt_timeout_seconds = float(zoekt_timeout)

        qdrant_timeout = (os.getenv("QDRANT_TIMEOUT_SECONDS") or "").strip()
        if qdrant_timeout and "ROOTSEEKER_QDRANT_TIMEOUT_SECONDS" not in os.environ:
            self.qdrant_timeout_seconds = float(qdrant_timeout)

        collection = (os.getenv("QDRANT_COLLECTION_NAME") or "").strip()
        if collection and "ROOTSEEKER_QDRANT_COLLECTION_NAME" not in os.environ:
            self.qdrant_collection_name = collection
        return self

    @field_validator("internal_adapter_kind", mode="before")
    @classmethod
    def reject_legacy_mock_adapter_kind(cls, v: object) -> object:
        if isinstance(v, str) and v.strip().lower() == "mock":
            raise ValueError(
                "ROOTSEEKER_INTERNAL_ADAPTER_KIND=mock is no longer supported. "
                "Use composite (default) for SLS/Jaeger/Zoekt, or http with ROOTSEEKER_INTERNAL_HTTP_BASE_URL."
            )
        return v
