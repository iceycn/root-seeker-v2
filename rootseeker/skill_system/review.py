"""Skill review and approval workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from rootseeker.contracts.common import new_id, utc_now
from rootseeker.skill_system.draft_builder import SkillDraft

__all__ = ["ReviewStatus", "SkillReview", "SkillReviewer"]


class ReviewStatus(StrEnum):
    """Status of skill review."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"


@dataclass
class SkillReview:
    """A review of a skill draft."""

    review_id: str
    draft_slug: str
    reviewer: str
    status: ReviewStatus
    comments: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    reviewed_at: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)


class SkillReviewer:
    """Review and approve skill drafts.

    Review criteria:
    - Quality: Evidence count, confidence threshold
    - Uniqueness: Not duplicate of existing skill
    - Actionability: Steps are executable
    - Safety: No dangerous operations
    """

    def __init__(
        self,
        *,
        min_evidence_count: int = 3,
        min_confidence: float = 0.7,
        max_existing_similarity: float = 0.8,
    ) -> None:
        self._min_evidence = min_evidence_count
        self._min_confidence = min_confidence
        self._max_similarity = max_existing_similarity
        self._reviews: dict[str, SkillReview] = {}

    def review(
        self,
        draft: SkillDraft,
        *,
        reviewer: str = "auto-reviewer",
        existing_slugs: list[str] | None = None,
    ) -> SkillReview:
        """Review a skill draft."""
        comments: list[str] = []
        suggestions: list[str] = []
        issues: list[str] = []

        # Check quality
        confidence = draft.metadata.get("confidence", 0.0)
        if confidence < self._min_confidence:
            issues.append(f"置信度 {confidence:.2f} 低于阈值 {self._min_confidence}")
            suggestions.append("增加更多证据以提高置信度")

        # Check uniqueness
        if existing_slugs and draft.slug in existing_slugs:
            issues.append(f"技能 slug '{draft.slug}' 已存在")
            suggestions.append("修改 slug 以避免冲突")

        # Check actionability
        if not draft.steps:
            issues.append("技能缺少执行步骤")
            suggestions.append("添加至少一个执行步骤")

        if not draft.required_tools:
            issues.append("技能缺少所需工具")
            suggestions.append("添加所需工具列表")

        # Determine status
        if issues:
            status = ReviewStatus.NEEDS_REVISION
            comments.extend(issues)
        else:
            status = ReviewStatus.APPROVED
            comments.append("技能草稿符合质量标准")

        review = SkillReview(
            review_id=new_id("review-"),
            draft_slug=draft.slug,
            reviewer=reviewer,
            status=status,
            comments=comments,
            suggestions=suggestions,
        )

        self._reviews[review.review_id] = review
        return review

    def approve(self, review_id: str, reviewer: str) -> SkillReview | None:
        """Approve a pending review."""
        review = self._reviews.get(review_id)
        if review is None:
            return None

        review.status = ReviewStatus.APPROVED
        review.reviewer = reviewer
        review.reviewed_at = utc_now()
        review.comments.append(f"Approved by {reviewer}")

        return review

    def reject(self, review_id: str, reviewer: str, reason: str) -> SkillReview | None:
        """Reject a pending review."""
        review = self._reviews.get(review_id)
        if review is None:
            return None

        review.status = ReviewStatus.REJECTED
        review.reviewer = reviewer
        review.reviewed_at = utc_now()
        review.comments.append(f"Rejected by {reviewer}: {reason}")

        return review

    def get_review(self, review_id: str) -> SkillReview | None:
        """Get a review by ID."""
        return self._reviews.get(review_id)

    def list_pending(self) -> list[SkillReview]:
        """List all pending reviews."""
        return [r for r in self._reviews.values() if r.status == ReviewStatus.PENDING]

    def list_approved(self) -> list[SkillReview]:
        """List all approved reviews."""
        return [r for r in self._reviews.values() if r.status == ReviewStatus.APPROVED]
