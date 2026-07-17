"""Skill draft builder for automatic skill synthesis from case reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from rootseeker.contracts.common import utc_now
from rootseeker.contracts.report import CaseReport
from rootseeker.skill_system.parser import ROOTSEEKER_SKILL_SPEC_FILENAME

__all__ = ["SkillDraft", "SkillDraftBuilder"]


@dataclass
class SkillDraft:
    """A draft skill generated from case analysis."""

    slug: str
    name: str
    version: str
    description: str
    triggers: list[dict[str, Any]]
    required_tools: list[str]
    steps: list[dict[str, Any]]
    source_case_id: str
    created_at: datetime = field(default_factory=utc_now)
    status: str = "draft"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_skill_md(self) -> str:
        """Convert draft to SKILL.md format."""
        frontmatter = {
            "name": self.name,
            "description": self.description,
        }

        return f"""---
{yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)}---

# {self.name}

{self.description}

## RootSeeker Runtime

Runtime metadata is stored in `{ROOTSEEKER_SKILL_SPEC_FILENAME}`.

## Source

Generated from case: `{self.source_case_id}`
"""

    def to_rootseeker_spec_yaml(self) -> str:
        """Convert runtime metadata to RootSeeker sidecar YAML."""
        skill_spec = {
            "slug": self.slug,
            "version": self.version,
            "tags": self.metadata.get("tags", []),
            "triggers": self.triggers,
            "required_tools": self.required_tools,
            "source_kind": "generated",
            "metadata": self.metadata,
            "steps": self.steps,
        }
        return yaml.dump(skill_spec, default_flow_style=False, allow_unicode=True)


class SkillDraftBuilder:
    """Build skill drafts from case reports.

    The builder analyzes successful case resolutions and extracts
    patterns that can be reused as skills.
    """

    def __init__(
        self,
        *,
        output_dir: Path | None = None,
        min_evidence_count: int = 3,
        min_confidence: float = 0.6,
    ) -> None:
        self._output_dir = output_dir
        self._min_evidence = min_evidence_count
        self._min_confidence = min_confidence

    def build_from_report(self, report: CaseReport) -> SkillDraft | None:
        """Build a skill draft from a case report.

        Returns None if the report doesn't meet quality thresholds.
        """
        # Check quality thresholds
        if not self._meets_thresholds(report):
            return None

        # Extract patterns from report
        slug = self._generate_slug(report)
        name = self._generate_name(report)
        description = self._generate_description(report)
        triggers = self._extract_triggers(report)
        required_tools = self._extract_tools(report)
        steps = self._extract_steps(report)

        return SkillDraft(
            slug=slug,
            name=name,
            version="0.1.0-draft",
            description=description,
            triggers=triggers,
            required_tools=required_tools,
            steps=steps,
            source_case_id=report.case_id,
            metadata={
                "tags": self._extract_tags(report),
                "confidence": report.root_cause.confidence if report.root_cause else 0.0,
            },
        )

    def save_draft(self, draft: SkillDraft, output_dir: Path | None = None) -> Path:
        """Save draft to SKILL.md file."""
        target_dir = output_dir or self._output_dir or Path("skills/generated")
        skill_dir = target_dir / draft.slug.replace("/", "-")
        skill_dir.mkdir(parents=True, exist_ok=True)

        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(draft.to_skill_md(), encoding="utf-8")
        (skill_dir / ROOTSEEKER_SKILL_SPEC_FILENAME).write_text(
            draft.to_rootseeker_spec_yaml(),
            encoding="utf-8",
        )

        return skill_path

    def _meets_thresholds(self, report: CaseReport) -> bool:
        """Check if report meets quality thresholds."""
        if len(report.evidence_item_ids) < self._min_evidence:
            return False

        if report.root_cause and report.root_cause.confidence < self._min_confidence:
            return False

        return True

    def _generate_slug(self, report: CaseReport) -> str:
        """Generate skill slug from report."""
        # Use service name and symptom keywords
        service = report.root_cause.title if report.root_cause else "unknown"
        # Clean up for slug
        slug_base = service.lower().replace(" ", "-").replace("/", "-")[:30]
        return f"generated/{slug_base}"

    def _generate_name(self, report: CaseReport) -> str:
        """Generate skill name from report."""
        if report.root_cause and report.root_cause.title:
            return f"Auto: {report.root_cause.title[:50]}"
        return "Auto-generated Skill"

    def _generate_description(self, report: CaseReport) -> str:
        """Generate skill description from report."""
        if report.root_cause and report.root_cause.narrative:
            return report.root_cause.narrative[:200]
        return f"Automatically generated from case {report.case_id}"

    def _extract_triggers(self, report: CaseReport) -> list[dict[str, Any]]:
        """Extract trigger patterns from report."""
        # Default trigger based on service name
        triggers: list[dict[str, Any]] = []

        # Extract from contributing factors
        if report.root_cause and report.root_cause.contributing_factors:
            for factor in report.root_cause.contributing_factors[:3]:
                triggers.append(
                    {
                        "type": "keyword",
                        "pattern": factor,
                        "source": "auto_extracted",
                    }
                )

        if not triggers:
            triggers.append(
                {
                    "type": "manual",
                    "description": "Manually configure triggers",
                }
            )

        return triggers

    def _extract_tools(self, report: CaseReport) -> list[str]:
        """Extract required tools from evidence."""
        # Default tools for troubleshooting
        return [
            "catalog.resolve_service",
            "log.query_by_trace_id",
            "trace.get_chain",
            "code.search",
            "notify.send",
        ]

    def _extract_steps(self, report: CaseReport) -> list[dict[str, Any]]:
        """Extract skill steps from evidence pattern."""
        # Default step pattern
        return [
            {
                "step_id": "resolve-service",
                "name": "Resolve service",
                "action": "catalog.resolve_service",
                "description": "Get service catalog entry",
            },
            {
                "step_id": "query-logs",
                "name": "Query logs",
                "action": "log.query_by_trace_id",
                "description": "Query logs by trace ID",
            },
            {
                "step_id": "get-trace",
                "name": "Get trace chain",
                "action": "trace.get_chain",
                "description": "Fetch trace chain",
            },
            {
                "step_id": "search-code",
                "name": "Search code",
                "action": "code.search",
                "description": "Search code for related patterns",
            },
            {
                "step_id": "notify",
                "name": "Send notification",
                "action": "notify.send",
                "description": "Send result notification",
            },
        ]

    def _extract_tags(self, report: CaseReport) -> list[str]:
        """Extract tags from report."""
        tags = ["auto-generated"]

        if report.root_cause and report.root_cause.contributing_factors:
            tags.extend(report.root_cause.contributing_factors[:3])

        return tags
