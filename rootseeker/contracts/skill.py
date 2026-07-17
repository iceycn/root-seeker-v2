from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SkillSourceKind(StrEnum):
    BUILTIN = "builtin"
    CUSTOM = "custom"
    GENERATED = "generated"


class SkillKind(StrEnum):
    FLOW = "flow"
    TOOL = "tool"
    TOOL_GROUP = "tool_group"


class SkillCondition(BaseModel):
    field: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    value: Any


class SkillStepDefinition(BaseModel):
    step_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    action: str = Field(min_length=1, description="Capability or MCP tool action name")
    description: str = ""
    tool_skill_slug: str = Field(default="", description="Tool skill to load for argument planning")
    defer_until: str | None = Field(
        default=None, description="Defer step until phase e.g. after_report"
    )
    requires_tools: list[str] = Field(default_factory=list)
    conditions: list[SkillCondition] = Field(default_factory=list)
    skip_if: list[SkillCondition] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SkillSpec(BaseModel):
    name: str = Field(min_length=1)
    slug: str = Field(min_length=1)
    description: str = ""
    skill_kind: SkillKind = SkillKind.FLOW
    bound_tools: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    steps: list[SkillStepDefinition] = Field(default_factory=list)
    source_kind: SkillSourceKind = SkillSourceKind.BUILTIN
    version: str = Field(default="0.1.0", min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SkillExecutionPlan(BaseModel):
    skill_slug: str = Field(min_length=1)
    steps: list[SkillStepDefinition] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GeneratedSkillDraft(BaseModel):
    draft_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    spec: SkillSpec
    source_case_ids: list[str] = Field(default_factory=list)
    generated_reason: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
