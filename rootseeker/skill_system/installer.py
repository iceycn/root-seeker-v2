from __future__ import annotations

import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from rootseeker.contracts.skill import SkillSourceKind
from rootseeker.skill_system.discovery import discover_skill_files
from rootseeker.skill_system.errors import SkillError
from rootseeker.skill_system.parser import load_skill_from_path

__all__ = [
    "install_from_directory",
    "install_from_git",
    "install_from_zip",
]


def install_from_directory(
    source: Path,
    *,
    external_root: Path,
    builtin_names: set[str],
    existing_names: set[str],
    overwrite: bool = False,
    only_name: str | None = None,
) -> list[str]:
    packages = _discover_packages(source, only_name=only_name)
    planned = _validate_packages(
        packages,
        builtin_names=builtin_names,
        existing_names=existing_names,
        overwrite=overwrite,
    )
    return _copy_packages(planned, external_root=external_root, overwrite=overwrite)


def install_from_zip(
    zip_path: Path,
    *,
    external_root: Path,
    builtin_names: set[str],
    existing_names: set[str],
    overwrite: bool = False,
    only_name: str | None = None,
) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _extract_zip(Path(zip_path), tmp_path)
        return install_from_directory(
            tmp_path,
            external_root=external_root,
            builtin_names=builtin_names,
            existing_names=existing_names,
            overwrite=overwrite,
            only_name=only_name,
        )


def install_from_git(
    url: str,
    *,
    external_root: Path,
    builtin_names: set[str],
    existing_names: set[str],
    overwrite: bool = False,
    only_name: str | None = None,
) -> list[str]:
    tmp = tempfile.mkdtemp()
    tmp_path = Path(tmp)
    try:
        try:
            subprocess.run(["git", "clone", "--depth", "1", url, tmp], check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise SkillError("SKILL_INVALID_PACKAGE", f"git clone failed: {url}") from exc
        return install_from_directory(
            tmp_path,
            external_root=external_root,
            builtin_names=builtin_names,
            existing_names=existing_names,
            overwrite=overwrite,
            only_name=only_name,
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _zip_entry_is_unsafe(name: str) -> bool:
    return any(part == ".." for part in name.replace("\\", "/").split("/"))


def _extract_zip(zip_path: Path, dest: Path) -> None:
    try:
        archive = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise SkillError("SKILL_INVALID_PACKAGE", f"invalid zip package: {zip_path}") from exc
    with archive:
        for name in archive.namelist():
            if _zip_entry_is_unsafe(name):
                raise SkillError("SKILL_INVALID_PACKAGE", f"unsafe zip path: {name}")
        archive.extractall(dest)


def _discover_packages(source: Path, *, only_name: str | None) -> list[Path]:
    skill_files = discover_skill_files(source)
    if only_name is not None:
        skill_files = [path for path in skill_files if path.parent.name == only_name]
    if not skill_files:
        raise SkillError("SKILL_INVALID_PACKAGE", f"no skill packages found in {source}")
    return skill_files


def _validate_packages(
    skill_files: list[Path],
    *,
    builtin_names: set[str],
    existing_names: set[str],
    overwrite: bool,
) -> list[tuple[str, Path]]:
    planned: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for skill_md in skill_files:
        spec = load_skill_from_path(skill_md, source_kind=SkillSourceKind.EXTERNAL)
        name = spec.name
        if name in seen:
            raise SkillError("SKILL_INVALID_PACKAGE", f"duplicate skill name in package: {name}")
        if name in builtin_names:
            raise SkillError("SKILL_NAME_CONFLICT", f"skill name conflicts with builtin: {name}")
        if name in existing_names and not overwrite:
            raise SkillError("SKILL_NAME_CONFLICT", f"skill name already exists: {name}")
        seen.add(name)
        planned.append((name, skill_md.parent))
    return planned


def _copy_packages(
    planned: list[tuple[str, Path]],
    *,
    external_root: Path,
    overwrite: bool,
) -> list[str]:
    external_root.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    try:
        for name, skill_dir in planned:
            dest = external_root / name
            if dest.exists():
                if not overwrite:
                    raise SkillError("SKILL_NAME_CONFLICT", f"skill name already exists: {name}")
                shutil.rmtree(dest)
            copied.append(dest)
            shutil.copytree(skill_dir, dest)
    except Exception:
        for dest in copied:
            shutil.rmtree(dest, ignore_errors=True)
        raise
    return [name for name, _ in planned]
