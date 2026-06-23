"""Skill publisher for publishing approved drafts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from rootseeker.contracts.common import utc_now
from rootseeker.skill_system.draft_builder import SkillDraft
from rootseeker.skill_system.parser import ROOTSEEKER_SKILL_SPEC_FILENAME
from rootseeker.skill_system.review import ReviewStatus, SkillReview

__all__ = ["PublishedSkill", "SkillPublisher", "PublishStatus"]


class PublishStatus(StrEnum):
    """Status of skill publishing."""

    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


@dataclass
class PublishedSkill:
    """A published skill with version history."""

    slug: str
    version: str
    status: PublishStatus
    skill_path: Path
    published_at: datetime = field(default_factory=utc_now)
    published_by: str = "auto-publisher"
    source_review_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SkillPublisher:
    """Publish approved skill drafts.

    Publishing workflow:
    1. Check review is approved
    2. Write SKILL.md to target directory
    3. Register in skill registry
    4. Track version history
    """

    def __init__(
        self,
        *,
        target_dir: Path | None = None,
        registry_path: Path | None = None,
    ) -> None:
        self._target_dir = target_dir or Path("skills/generated")
        self._registry_path = registry_path
        self._published: dict[str, PublishedSkill] = {}

    def publish(
        self,
        draft: SkillDraft,
        review: SkillReview,
        *,
        publisher: str = "auto-publisher",
    ) -> PublishedSkill | None:
        """Publish an approved skill draft."""
        # Check review is approved
        if review.status != ReviewStatus.APPROVED:
            return None

        # Check review matches draft
        if review.draft_slug != draft.slug:
            return None

        # Write SKILL.md
        skill_path = self._write_skill_file(draft)

        # Create published record
        published = PublishedSkill(
            slug=draft.slug,
            version=draft.version,
            status=PublishStatus.PUBLISHED,
            skill_path=skill_path,
            published_by=publisher,
            source_review_id=review.review_id,
            metadata={
                "source_case_id": draft.source_case_id,
                "original_confidence": draft.metadata.get("confidence", 0.0),
            },
        )

        self._published[draft.slug] = published
        return published

    def deprecate(self, slug: str, reason: str) -> PublishedSkill | None:
        """Deprecate a published skill."""
        published = self._published.get(slug)
        if published is None:
            return None

        published.status = PublishStatus.DEPRECATED
        published.metadata["deprecation_reason"] = reason
        published.metadata["deprecated_at"] = utc_now().isoformat()

        return published

    def archive(self, slug: str) -> PublishedSkill | None:
        """Archive a deprecated skill."""
        published = self._published.get(slug)
        if published is None:
            return None

        published.status = PublishStatus.ARCHIVED
        published.metadata["archived_at"] = utc_now().isoformat()

        return published

    def _write_skill_file(self, draft: SkillDraft) -> Path:
        """Write SKILL.md file."""
        skill_dir = self._target_dir / draft.slug.replace("/", "-")
        skill_dir.mkdir(parents=True, exist_ok=True)

        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(draft.to_skill_md(), encoding="utf-8")
        (skill_dir / ROOTSEEKER_SKILL_SPEC_FILENAME).write_text(
            draft.to_rootseeker_spec_yaml(),
            encoding="utf-8",
        )

        return skill_path

    def get_published(self, slug: str) -> PublishedSkill | None:
        """Get a published skill by slug."""
        return self._published.get(slug)

    def list_published(self) -> list[PublishedSkill]:
        """List all published skills."""
        return [p for p in self._published.values() if p.status == PublishStatus.PUBLISHED]

    def list_deprecated(self) -> list[PublishedSkill]:
        """List all deprecated skills."""
        return [p for p in self._published.values() if p.status == PublishStatus.DEPRECATED]
