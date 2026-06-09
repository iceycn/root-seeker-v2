from __future__ import annotations

from typing import Any

from pydantic import Field

from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.contracts.common import RootSeekerModel, utc_now

__all__ = ["ReplayCaseSpec", "ReplayRunSnapshot"]


class ReplayCaseSpec(RootSeekerModel):
    """Fixture for regression: alert payload + normalized case input + expected hints."""

    replay_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    alert_payload: dict[str, Any] = Field(default_factory=dict)
    case_request: CaseCreateRequest
    log_samples: list[dict[str, Any]] = Field(default_factory=list)
    trace_samples: list[dict[str, Any]] = Field(default_factory=list)
    code_revision_hint: str | None = None
    human_root_cause: str = ""
    expected_report_bullets: list[str] = Field(default_factory=list)
    redacted: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplayRunSnapshot(RootSeekerModel):
    replay_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    skill_name: str = Field(min_length=1)
    flow_plugin_id: str = Field(min_length=1)
    passed: bool = False
    metrics: dict[str, float] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: utc_now().isoformat())
