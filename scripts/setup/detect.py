from __future__ import annotations

import platform
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EnvInfo:
    os_name: str
    python_version: str
    python_ok: bool
    docker_cli: bool
    docker_daemon: bool
    ports_in_use: dict[int, bool] = field(default_factory=dict)


def _port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def detect_docker_daemon() -> tuple[bool, bool]:
    cli = shutil.which("docker") is not None
    if not cli:
        return False, False
    try:
        proc = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return True, proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return True, False


def detect_environment(repo_root: Path) -> EnvInfo:
    _ = repo_root
    docker_cli, docker_daemon = detect_docker_daemon()
    ports = {p: _port_in_use(p) for p in (8000, 8010, 3306, 3307, 6070, 6071, 6333, 7474)}
    return EnvInfo(
        os_name=platform.system().lower(),
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        python_ok=sys.version_info >= (3, 11),
        docker_cli=docker_cli,
        docker_daemon=docker_daemon,
        ports_in_use=ports,
    )
