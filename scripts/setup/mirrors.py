from __future__ import annotations

import os
import subprocess

from scripts.setup import ui

# DaoCloud / 1ms 等常用 Docker Hub 代理（国内）。
_CN_DOCKER_PROXIES = (
    "docker.m.daocloud.io",
    "docker.1ms.run",
)

_ENV_REGION = "ROOTSEEKER_SETUP_REGION"


def setup_region() -> str:
    """Return ``cn`` or ``global`` from env (set by setup-cn.* wrappers)."""
    raw = os.environ.get(_ENV_REGION, "global").strip().lower()
    if raw in {"cn", "china", "zh", "domestic", "china-mainland"}:
        return "cn"
    return "global"


def is_cn_region() -> bool:
    return setup_region() == "cn"


def _image_present(name: str) -> bool:
    probe = subprocess.run(
        ["docker", "image", "inspect", name],
        capture_output=True,
        check=False,
    )
    return probe.returncode == 0


def _docker_pull(ref: str) -> bool:
    ui.info(f"拉取镜像: {ref}")
    result = subprocess.run(["docker", "pull", ref], check=False)
    return result.returncode == 0


def _docker_tag(source: str, target: str) -> None:
    subprocess.run(["docker", "tag", source, target], check=False)


def mirror_hub_refs(repository: str, tag: str = "latest") -> list[str]:
    """Candidate refs for a Docker Hub repository (user/name)."""
    repo = repository.removeprefix("docker.io/")
    if is_cn_region():
        refs = [f"{proxy}/{repo}:{tag}" for proxy in _CN_DOCKER_PROXIES]
        refs.append(f"docker.io/{repo}:{tag}")
        return refs
    return [f"docker.io/{repo}:{tag}", f"{repo}:{tag}"]


def mysql_image_refs() -> list[str]:
    if is_cn_region():
        refs = [f"{proxy}/library/mysql:8.0" for proxy in _CN_DOCKER_PROXIES]
        refs.append("mysql:8.0")
        return refs
    return ["mysql:8.0"]


def ensure_local_image(local_name: str, candidates: list[str]) -> bool:
    """Pull first available candidate and tag as ``local_name`` if needed."""
    if _image_present(local_name):
        return True
    for ref in candidates:
        if _image_present(ref):
            if ref != local_name:
                _docker_tag(ref, local_name)
            return True
        if _docker_pull(ref):
            if ref != local_name:
                _docker_tag(ref, local_name)
            return True
    return False


def apply_cn_docker_env(env: dict[str, str]) -> dict[str, str]:
    """Mutate compose env for CN: ensure images exist and set MYSQL_IMAGE."""
    if not is_cn_region():
        return env

    ui.info("国内加速模式（ROOTSEEKER_SETUP_REGION=cn）")
    hub_user = env.get("DOCKERHUB_USER", "wuhun0301")
    tag = env.get("IMAGE_TAG", "latest")

    mysql_ok = ensure_local_image("mysql:8.0", mysql_image_refs())
    if mysql_ok:
        env["MYSQL_IMAGE"] = env.get("MYSQL_IMAGE") or "mysql:8.0"
        ui.ok("MySQL 镜像已就绪 (mysql:8.0)")
    else:
        ui.warn("未能通过国内源拉取 mysql:8.0，后续 compose 可能失败")

    for short in (
        f"{hub_user}/rootseeker-v2",
        f"{hub_user}/rootseeker-v2-zoekt",
        f"{hub_user}/rootseeker-v2-gitnexus",
    ):
        local = f"docker.io/{short}:{tag}"
        ensure_local_image(local, mirror_hub_refs(short, tag))
        # Also tag without docker.io/ prefix used by some compose resolvers.
        if _image_present(local) and not _image_present(f"{short}:{tag}"):
            _docker_tag(local, f"{short}:{tag}")

    return env


def rewrite_mysql_archive_url(official_url: str) -> str:
    """Prefer Tsinghua MySQL mirror when in CN region."""
    if not is_cn_region():
        return official_url
    marker = "/Downloads/"
    if marker not in official_url:
        return official_url
    suffix = official_url.split(marker, 1)[1]
    return f"https://mirrors.tuna.tsinghua.edu.cn/mysql/downloads/{suffix}"
