import subprocess
import zipfile
from pathlib import Path

import pytest

from rootseeker.skill_system.errors import SkillError
from rootseeker.skill_system.installer import (
    install_from_directory,
    install_from_git,
    install_from_zip,
)


def test_install_copies_to_external_and_skips_default(tmp_path: Path) -> None:
    src = Path(__file__).resolve().parents[2] / "fixtures" / "sample_skill"
    dest = tmp_path / "external"
    names = install_from_directory(src, external_root=dest, builtin_names={"default-log-triage"}, existing_names=set())
    assert names == ["hello-triage"]
    assert (dest / "hello-triage" / "SKILL.md").is_file()


def test_install_rejects_builtin_name(tmp_path: Path) -> None:
    src = tmp_path / "src" / "default-log-triage"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text("---\nname: default-log-triage\ndescription: x\n---\n# x\n", encoding="utf-8")
    with pytest.raises(SkillError) as exc:
        install_from_directory(src.parent, external_root=tmp_path / "external", builtin_names={"default-log-triage"}, existing_names=set())
    assert exc.value.code == "SKILL_NAME_CONFLICT"


def test_install_from_zip_rejects_path_traversal(tmp_path: Path) -> None:
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../evil-triage/SKILL.md", "---\nname: evil-triage\ndescription: x\n---\n# x\n")
    with pytest.raises(SkillError) as exc:
        install_from_zip(
            zip_path,
            external_root=tmp_path / "external",
            builtin_names=set(),
            existing_names=set(),
        )
    assert exc.value.code == "SKILL_INVALID_PACKAGE"
    assert not (tmp_path / "evil-triage").exists()


def test_install_from_git_clone_failure_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: object, **kwargs: object) -> object:
        raise subprocess.CalledProcessError(128, ["git", "clone"])

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(SkillError) as exc:
        install_from_git(
            "https://example.com/not-a-repo.git",
            external_root=tmp_path / "external",
            builtin_names=set(),
            existing_names=set(),
        )
    assert exc.value.code == "SKILL_INVALID_PACKAGE"
