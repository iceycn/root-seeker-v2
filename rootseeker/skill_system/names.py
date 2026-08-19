import re

from rootseeker.skill_system.errors import SkillError

_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def normalize_skill_name(value: str) -> str:
    text = (value or "").strip().strip("/")
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    return text


def validate_skill_name(name: str) -> None:
    if not name or len(name) > 64 or not _NAME_RE.fullmatch(name):
        raise SkillError("SKILL_INVALID_PACKAGE", f"invalid skill name: {name!r}")
