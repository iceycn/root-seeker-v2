from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from scripts.setup import ui
from scripts.setup.state import SetupState


def setup_indexers(
    repo_root: Path,
    state: SetupState,
    *,
    noninteractive: bool,
) -> dict[str, str]:
    _ = noninteractive
    result = {
        "zoekt": _setup_zoekt(repo_root),
        "qdrant": _setup_qdrant(repo_root),
        "gitnexus": _setup_gitnexus(repo_root),
    }
    state.set_meta("indexers", result)
    return result


def _setup_zoekt(repo_root: Path) -> str:
    index_bin = repo_root / "docker" / "bin" / "zoekt-index"
    web_bin = repo_root / "docker" / "bin" / "zoekt-webserver"
    if not index_bin.exists() or not web_bin.exists():
        if os.name == "nt":
            script = repo_root / "docker" / "prepare-zoekt.ps1"
            if script.exists():
                subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        str(script),
                    ],
                    cwd=str(repo_root),
                    check=False,
                )
        else:
            script = repo_root / "docker" / "prepare-zoekt.sh"
            if script.exists():
                subprocess.run(["bash", str(script)], cwd=str(repo_root), check=False)
    if index_bin.exists() and web_bin.exists():
        # Best-effort start is environment-specific; presence counts as prepared.
        return "ok:二进制已就绪（可用 Docker/hybrid 启动服务）"
    return "skipped:未能准备 Zoekt 二进制"


def _setup_qdrant(repo_root: Path) -> str:
    qdir = repo_root / ".tools" / "qdrant"
    # Prefer already-downloaded binary layout used by some local scripts.
    legacy = repo_root / "tools" / "qdrant"
    if legacy.exists():
        return "ok:检测到 tools/qdrant"
    if qdir.exists() and any(qdir.iterdir()):
        return "ok:检测到 .tools/qdrant"
    ui.warn("Qdrant 本机自动下载未内置完整镜像矩阵；请使用 Docker 或自行安装后跳过")
    return "skipped:请使用 Docker 启动 qdrant 或手动安装"


def _setup_gitnexus(repo_root: Path) -> str:
    _ = repo_root
    if shutil.which("node") is None:
        return "skipped:未检测到 Node.js，建议用 Docker 启动 gitnexus"
    return "ok:已检测到 Node.js（可用 Docker/npx 启动 GitNexus sidecar）"
