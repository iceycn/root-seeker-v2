from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rootseeker.contracts.skill import SkillSpec, SkillStepDefinition
from rootseeker.infra_core.settings import RootSeekerSettings
from rootseeker.skill_system.parser import ROOTSEEKER_SKILL_SPEC_FILENAME, load_skill_body

__all__ = ["SkillContentLoader", "SkillStepContext"]


@dataclass
class SkillStepContext:
    flow_skill_slug: str
    step_id: str
    action: str
    tool_skill_slug: str
    flow_step_description: str = ""
    tool_skill_name: str = ""
    tool_skill_description: str = ""
    skill_body: str = ""
    reference_text: str = ""
    reference_paths: list[str] = field(default_factory=list)
    truncated: bool = False

    def to_prompt_text(self) -> str:
        sections = [
            f"# Flow step: {self.step_id} ({self.action})",
            self.flow_step_description,
            f"# Tool skill: {self.tool_skill_slug}",
            f"Name: {self.tool_skill_name}",
            f"Description: {self.tool_skill_description}",
            "## SKILL.md",
            self.skill_body,
        ]
        if self.reference_text:
            sections.extend(["## References", self.reference_text])
        return "\n\n".join(part for part in sections if part).strip()


class SkillContentLoader:
    def __init__(self, *, settings: RootSeekerSettings | None = None) -> None:
        self.settings = settings or RootSeekerSettings()

    def load_step_context(
        self,
        *,
        flow_skill: SkillSpec,
        step: SkillStepDefinition,
        tool_skill: SkillSpec,
        include_references: list[str] | None = None,
    ) -> SkillStepContext:
        skill_dir = self._skill_dir(tool_skill)
        skill_md = skill_dir / "SKILL.md"
        body = load_skill_body(skill_md) if skill_md.is_file() else ""
        ref_paths = include_references or self._default_reference_paths(tool_skill, step)
        reference_chunks: list[str] = []
        loaded_paths: list[str] = []
        for rel in ref_paths:
            ref_path = skill_dir / rel
            if not ref_path.is_file():
                continue
            loaded_paths.append(rel)
            reference_chunks.append(f"### {rel}\n{ref_path.read_text(encoding='utf-8').strip()}")

        context = SkillStepContext(
            flow_skill_slug=flow_skill.slug,
            step_id=step.step_id,
            action=step.action,
            tool_skill_slug=tool_skill.slug,
            flow_step_description=step.description,
            tool_skill_name=tool_skill.name,
            tool_skill_description=tool_skill.description,
            skill_body=body,
            reference_text="\n\n".join(reference_chunks).strip(),
            reference_paths=loaded_paths,
        )
        return self._apply_budget(context)

    def _skill_dir(self, tool_skill: SkillSpec) -> Path:
        skill_dir = tool_skill.metadata.get("skill_dir")
        if isinstance(skill_dir, str) and skill_dir:
            return Path(skill_dir)
        raise ValueError(f"Tool skill {tool_skill.slug!r} missing metadata.skill_dir")

    def _default_reference_paths(
        self,
        tool_skill: SkillSpec,
        step: SkillStepDefinition,
    ) -> list[str]:
        paths: list[str] = []
        for key in ("reference", "references"):
            value = tool_skill.metadata.get(key) or step.metadata.get(key)
            if isinstance(value, str) and value.strip():
                paths.append(value.strip())
            elif isinstance(value, list):
                paths.extend(str(item).strip() for item in value if str(item).strip())
        refs_dir = self._skill_dir(tool_skill) / "references"
        if refs_dir.is_dir() and not paths:
            paths.extend(
                f"references/{path.name}"
                for path in sorted(refs_dir.glob("*.md"))
            )
        return paths

    def _apply_budget(self, context: SkillStepContext) -> SkillStepContext:
        budget = max(1000, int(self.settings.skill_context_max_chars))
        text = context.to_prompt_text()
        if len(text) <= budget:
            return context
        # Keep SKILL body, trim references first
        trimmed_refs = context.reference_text
        while trimmed_refs and len(context.skill_body) + len(trimmed_refs) + 500 > budget:
            lines = trimmed_refs.splitlines()
            trimmed_refs = "\n".join(lines[: max(1, len(lines) // 2)]).strip()
        context.reference_text = trimmed_refs
        context.truncated = True
        if len(context.to_prompt_text()) <= budget:
            return context
        context.skill_body = context.skill_body[: max(0, budget - 500)]
        context.truncated = True
        return context
