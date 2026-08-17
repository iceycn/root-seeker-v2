from pathlib import Path

from rootseeker.skill_system.draft_builder import SkillDraft
from rootseeker.skill_system.publisher import SkillPublisher
from rootseeker.skill_system.registry import SkillRegistry
from rootseeker.skill_system.review import ReviewStatus, SkillReview


def test_skill_publisher_upserts_into_registry(tmp_path: Path) -> None:
    registry = SkillRegistry()
    publisher = SkillPublisher(target_dir=tmp_path / "generated", registry=registry)
    draft = SkillDraft(
        slug="tools/generated-test",
        version="1.0.0",
        name="Generated Test",
        description="test skill",
        triggers=[],
        required_tools=["notify.send"],
        steps=[],
        source_case_id="case-1",
    )
    review = SkillReview(
        review_id="rev-1",
        draft_slug=draft.slug,
        status=ReviewStatus.APPROVED,
        reviewer="tester",
        comments=["ok"],
    )

    published = publisher.publish(draft, review)
    assert published is not None
    assert registry.get(draft.slug) is not None
    assert registry.get(draft.slug).name == "Generated Test"
