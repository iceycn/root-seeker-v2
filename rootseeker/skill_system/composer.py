from __future__ import annotations

from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.contracts.skill import SkillExecutionPlan, SkillKind, SkillSpec
from rootseeker.infra_core.settings import RootSeekerSettings
from rootseeker.skill_system.registry import DEFAULT_FLOW_SKILL_SLUG, SkillRegistry

__all__ = ["SkillComposer"]


class SkillComposer:
    def __init__(
        self,
        registry: SkillRegistry,
        *,
        settings: RootSeekerSettings | None = None,
        registered_tool_names: set[str] | frozenset[str] | None = None,
    ) -> None:
        self.registry = registry
        self.settings = settings or RootSeekerSettings()
        self.registered_tool_names = set(registered_tool_names or ())

    def compose(self, case_request: CaseCreateRequest) -> SkillExecutionPlan:
        preferred = self._preferred_flow_slug(case_request)
        if preferred:
            spec = self.registry.get(preferred)
            if spec is not None and spec.skill_kind == SkillKind.FLOW:
                return SkillExecutionPlan(skill_slug=spec.slug, steps=list(spec.steps))

        trigger = self._case_trigger(case_request)
        candidates = self._flow_candidates(trigger)
        if candidates:
            return SkillExecutionPlan(
                skill_slug=candidates[0].slug,
                steps=list(candidates[0].steps),
            )

        fallback_slug = self.settings.skill_composer_default_flow
        spec = self.registry.get(fallback_slug)
        if spec is None:
            raise ValueError(f"Default flow skill not found: {fallback_slug}")
        return SkillExecutionPlan(skill_slug=spec.slug, steps=list(spec.steps))

    def _preferred_flow_slug(self, case_request: CaseCreateRequest) -> str | None:
        metadata = case_request.metadata or {}
        preferred = metadata.get("preferred_skill") or metadata.get("skill_slug")
        if isinstance(preferred, str) and preferred.strip():
            return preferred.strip()
        selected = metadata.get("selected_skills")
        if isinstance(selected, list) and selected:
            first = selected[0]
            if isinstance(first, str) and first.strip():
                return first.strip()
        return None

    def _case_trigger(self, case_request: CaseCreateRequest) -> str:
        source = (case_request.source or "").strip().lower()
        if source in {"replay", "case-replay"}:
            return "replay"
        if source in {"error-chat", "error_chat", "admin-error-chat"}:
            return "error_chat"
        if "webhook" in source or source in {"aliyun-webhook", "prometheus", "alertmanager"}:
            return "webhook_alarm"
        return "webhook_alarm"

    def _flow_candidates(self, trigger: str) -> list[SkillSpec]:
        flows = self.registry.list_by_kind(SkillKind.FLOW)
        matched = [flow for flow in flows if trigger in flow.triggers or not flow.triggers]
        if not matched:
            matched = flows

        def sort_key(spec: SkillSpec) -> tuple[int, str]:
            trigger_hit = 0 if trigger in spec.triggers else 1
            return (trigger_hit, spec.slug)

        matched.sort(key=sort_key)
        if not self.registered_tool_names:
            return matched
        ready: list[SkillSpec] = []
        for spec in matched:
            required = set(spec.required_tools)
            if required and not required.issubset(self.registered_tool_names):
                continue
            ready.append(spec)
        return ready or matched
