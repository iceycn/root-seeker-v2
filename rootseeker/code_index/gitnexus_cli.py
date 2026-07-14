"""Low-level GitNexus CLI / HTTP runner used by indexer and query adapter."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

__all__ = ["GitNexusCliConfig", "GitNexusCli", "GitNexusCommandResult"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GitNexusCommandResult:
    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    data: Any | None = None
    command: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "command": list(self.command),
        }
        if self.data is not None:
            payload["data"] = self.data
        return payload


@dataclass
class GitNexusCliConfig:
    """Runtime config for invoking GitNexus.

    Resolution order for command binary:
    1. ``command`` / ``ROOTSEEKER_GITNEXUS_COMMAND`` (space-separated, e.g. ``npx -y gitnexus@latest``)
    2. ``gitnexus`` on PATH
    3. ``npx -y gitnexus@latest`` (only when ROOTSEEKER_GITNEXUS_ALLOW_NPX=true)

    For Docker sidecar HTTP mode, set ``endpoint`` and optionally ``path_map`` so host
    clone paths are rewritten to the container mount (e.g. ``E:/repos:/data/repos``).
    """

    enabled: bool = True
    command: str | None = None
    endpoint: str | None = None
    path_map: str | None = None
    timeout_seconds: float = 600.0
    analyze_timeout_seconds: float = 1800.0
    skip_agents_md: bool = True
    skip_skills: bool = True
    force_analyze: bool = False
    embeddings: bool = False
    workers: int | None = None
    max_file_size_kb: int = 4096

    @classmethod
    def from_env(cls) -> GitNexusCliConfig:
        enabled_raw = (os.getenv("ROOTSEEKER_REPO_ENABLE_GITNEXUS") or "true").strip().lower()
        timeout_raw = (os.getenv("ROOTSEEKER_GITNEXUS_TIMEOUT_SECONDS") or "").strip()
        analyze_timeout_raw = (os.getenv("ROOTSEEKER_GITNEXUS_ANALYZE_TIMEOUT_SECONDS") or "").strip()
        workers_raw = (os.getenv("ROOTSEEKER_GITNEXUS_WORKERS") or "").strip()
        max_file_size_raw = (os.getenv("ROOTSEEKER_GITNEXUS_MAX_FILE_SIZE_KB") or "").strip()
        return cls(
            enabled=enabled_raw not in {"0", "false", "no", "off"},
            command=(os.getenv("ROOTSEEKER_GITNEXUS_COMMAND") or "").strip() or None,
            endpoint=(
                (os.getenv("ROOTSEEKER_GITNEXUS_ENDPOINT") or os.getenv("GITNEXUS_ENDPOINT") or "")
                .strip()
                or None
            ),
            path_map=(os.getenv("ROOTSEEKER_GITNEXUS_PATH_MAP") or "").strip() or None,
            timeout_seconds=float(timeout_raw) if timeout_raw else 600.0,
            analyze_timeout_seconds=float(analyze_timeout_raw) if analyze_timeout_raw else 1800.0,
            skip_agents_md=(os.getenv("ROOTSEEKER_GITNEXUS_SKIP_AGENTS_MD") or "true").lower()
            not in {"0", "false", "no"},
            skip_skills=(os.getenv("ROOTSEEKER_GITNEXUS_SKIP_SKILLS") or "true").lower()
            not in {"0", "false", "no"},
            force_analyze=(os.getenv("ROOTSEEKER_GITNEXUS_FORCE") or "false").lower()
            in {"1", "true", "yes"},
            embeddings=(os.getenv("ROOTSEEKER_GITNEXUS_EMBEDDINGS") or "false").lower()
            in {"1", "true", "yes"},
            workers=int(workers_raw) if workers_raw else None,
            max_file_size_kb=int(max_file_size_raw) if max_file_size_raw else 4096,
        )


class GitNexusCli:
    """Invoke GitNexus via local CLI or optional HTTP sidecar."""

    def __init__(self, config: GitNexusCliConfig | None = None) -> None:
        self.config = config or GitNexusCliConfig.from_env()
        self._argv = self._resolve_argv(self.config.command)

    @staticmethod
    def _resolve_argv(command: str | None) -> list[str]:
        if command:
            return [part for part in command.split() if part]
        gitnexus = shutil.which("gitnexus")
        if gitnexus:
            return [gitnexus]
        allow_npx = (os.getenv("ROOTSEEKER_GITNEXUS_ALLOW_NPX") or "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if allow_npx:
            npx = shutil.which("npx")
            if npx:
                return [npx, "-y", "gitnexus@latest"]
            return ["npx", "-y", "gitnexus@latest"]
        return []

    @property
    def available(self) -> bool:
        if not self.config.enabled:
            return False
        if self.config.endpoint:
            return True
        return bool(self._argv)

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | str | None = None,
        timeout_seconds: float | None = None,
        prefer_json: bool = True,
    ) -> GitNexusCommandResult:
        if not self.config.enabled:
            return GitNexusCommandResult(
                ok=False,
                exit_code=1,
                stdout="",
                stderr="gitnexus disabled",
                command=[],
            )
        if self.config.endpoint:
            return self._run_http(args, cwd=cwd, timeout_seconds=timeout_seconds)
        return self._run_cli(args, cwd=cwd, timeout_seconds=timeout_seconds, prefer_json=prefer_json)

    def analyze(
        self,
        local_path: Path | str,
        *,
        force: bool | None = None,
        embeddings: bool | None = None,
    ) -> GitNexusCommandResult:
        path = Path(local_path)
        args = ["analyze", str(path)]
        if self.config.skip_agents_md:
            args.append("--skip-agents-md")
        if self.config.skip_skills:
            args.append("--skip-skills")
        args.extend(["--index-only", "--max-file-size", str(max(1, int(self.config.max_file_size_kb)))])
        use_force = self.config.force_analyze if force is None else force
        if use_force:
            args.append("--force")
        use_embeddings = self.config.embeddings if embeddings is None else embeddings
        if use_embeddings:
            args.append("--embeddings")
        if self.config.workers is not None and self.config.workers > 0:
            args.extend(["--workers", str(self.config.workers)])
        return self.run(
            args,
            cwd=path.parent if path.is_dir() else path.parent,
            timeout_seconds=self.config.analyze_timeout_seconds,
            prefer_json=False,
        )

    def list_repos(self, *, limit: int | None = None, offset: int | None = None) -> GitNexusCommandResult:
        args = ["list"]
        if limit is not None:
            args.extend(["--limit", str(limit)])
        if offset is not None:
            args.extend(["--offset", str(offset)])
        return self.run(args)

    def status(self, *, cwd: Path | str | None = None, repo: str | None = None) -> GitNexusCommandResult:
        args = ["status"]
        if repo:
            args.extend(["--repo", repo])
        return self.run(args, cwd=cwd)

    def query(
        self,
        search_query: str,
        *,
        repo: str | None = None,
        cwd: Path | str | None = None,
    ) -> GitNexusCommandResult:
        args = ["query", search_query]
        if repo:
            args.extend(["--repo", repo])
        return self.run(args, cwd=cwd)

    def context(
        self,
        symbol: str,
        *,
        repo: str | None = None,
        file: str | None = None,
        uid: str | None = None,
        cwd: Path | str | None = None,
    ) -> GitNexusCommandResult:
        args = ["context", symbol]
        if uid:
            args.extend(["--uid", uid])
        if file:
            args.extend(["--file", file])
        if repo:
            args.extend(["--repo", repo])
        return self.run(args, cwd=cwd)

    def impact(
        self,
        symbol: str,
        *,
        direction: str = "upstream",
        repo: str | None = None,
        file: str | None = None,
        uid: str | None = None,
        kind: str | None = None,
        cwd: Path | str | None = None,
    ) -> GitNexusCommandResult:
        args = ["impact", symbol, "--direction", direction]
        if uid:
            args.extend(["--uid", uid])
        if file:
            args.extend(["--file", file])
        if kind:
            args.extend(["--kind", kind])
        if repo:
            args.extend(["--repo", repo])
        return self.run(args, cwd=cwd)

    def trace(
        self,
        source: str,
        target: str,
        *,
        repo: str | None = None,
        cwd: Path | str | None = None,
    ) -> GitNexusCommandResult:
        args = ["trace", source, target]
        if repo:
            args.extend(["--repo", repo])
        return self.run(args, cwd=cwd)

    def cypher(
        self,
        query: str,
        *,
        repo: str | None = None,
        cwd: Path | str | None = None,
    ) -> GitNexusCommandResult:
        args = ["cypher", query]
        if repo:
            args.extend(["--repo", repo])
        return self.run(args, cwd=cwd)

    def detect_changes(
        self,
        *,
        repo: str | None = None,
        cwd: Path | str | None = None,
    ) -> GitNexusCommandResult:
        args = ["detect-changes"]
        if repo:
            args.extend(["--repo", repo])
        return self.run(args, cwd=cwd)

    def _run_cli(
        self,
        args: list[str],
        *,
        cwd: Path | str | None,
        timeout_seconds: float | None,
        prefer_json: bool,
    ) -> GitNexusCommandResult:
        cmd = list(self._argv) + list(args)
        if prefer_json and "--json" not in cmd and "-j" not in cmd:
            # Prefer machine-readable output when the CLI understands --json.
            # Older builds ignore unknown flags; we still parse plain text as fallback.
            trial = list(cmd) + ["--json"]
        else:
            trial = list(cmd)
        timeout = self.config.timeout_seconds if timeout_seconds is None else timeout_seconds
        try:
            completed = subprocess.run(
                trial,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=os.environ.copy(),
            )
            # If --json is rejected, retry without it.
            if completed.returncode != 0 and prefer_json and "--json" in trial:
                stderr = (completed.stderr or "").lower()
                if "unknown" in stderr or "unexpected" in stderr or "unrecognized" in stderr:
                    completed = subprocess.run(
                        cmd,
                        cwd=str(cwd) if cwd else None,
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        check=False,
                        env=os.environ.copy(),
                    )
                    trial = list(cmd)
        except FileNotFoundError as exc:
            return GitNexusCommandResult(
                ok=False,
                exit_code=127,
                stdout="",
                stderr=f"gitnexus CLI not found: {exc}",
                command=trial,
            )
        except subprocess.TimeoutExpired as exc:
            return GitNexusCommandResult(
                ok=False,
                exit_code=124,
                stdout=str(exc.stdout or ""),
                stderr=f"gitnexus timed out after {timeout}s",
                command=trial,
            )

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        data = _parse_cli_payload(stdout)
        ok = completed.returncode == 0
        if not ok:
            logger.warning("gitnexus command failed (%s): %s", completed.returncode, stderr[:500])
        return GitNexusCommandResult(
            ok=ok,
            exit_code=completed.returncode,
            stdout=stdout,
            stderr=stderr,
            data=data,
            command=trial,
        )

    def _run_http(
        self,
        args: list[str],
        *,
        cwd: Path | str | None,
        timeout_seconds: float | None,
    ) -> GitNexusCommandResult:
        base = str(self.config.endpoint or "").rstrip("/")
        timeout = self.config.timeout_seconds if timeout_seconds is None else timeout_seconds
        mapped_args = [_rewrite_path_for_sidecar(arg, self.config.path_map) for arg in args]
        mapped_cwd = _rewrite_path_for_sidecar(str(cwd), self.config.path_map) if cwd else None
        payload = {
            "args": mapped_args,
            "cwd": mapped_cwd,
            "timeout_seconds": timeout,
        }
        try:
            with httpx.Client(timeout=timeout + 5.0) as client:
                response = client.post(f"{base}/v1/exec", json=payload)
                response.raise_for_status()
                body = response.json()
        except Exception as exc:  # noqa: BLE001 — surface as command failure
            return GitNexusCommandResult(
                ok=False,
                exit_code=1,
                stdout="",
                stderr=f"gitnexus HTTP error: {exc}",
                command=["http", *mapped_args],
            )
        if not isinstance(body, dict):
            return GitNexusCommandResult(
                ok=False,
                exit_code=1,
                stdout="",
                stderr="gitnexus HTTP returned non-object",
                command=["http", *mapped_args],
            )
        stdout = str(body.get("stdout") or "")
        stderr = str(body.get("stderr") or "")
        exit_code = int(body.get("exit_code") or (0 if body.get("ok") else 1))
        data = body.get("data")
        if data is None:
            data = _parse_cli_payload(stdout)
        return GitNexusCommandResult(
            ok=bool(body.get("ok", exit_code == 0)),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            data=data,
            command=["http", *mapped_args],
        )


def _rewrite_path_for_sidecar(value: str, path_map: str | None) -> str:
    """Rewrite host paths to container mount paths for the GitNexus sidecar.

    ``path_map`` format: ``host_prefix:container_prefix``
    Example: ``E:/CodeProjects/root-seeker-v2/repos:/data/repos``
    """
    text = str(value or "")
    mapping = (path_map or "").strip()
    if not text or not mapping or ":" not in mapping:
        return text
    # Split on the last colon that separates host/container prefixes on Windows-safe basis:
    # host may contain drive letters like E:/..., so split from the right once after finding
    # the container side which always starts with /.
    if ":/" in mapping:
        # Prefer splitting at ":/" that begins the container prefix.
        idx = mapping.rfind(":/")
        host_prefix = mapping[:idx]
        container_prefix = mapping[idx + 1 :]  # keep leading /
    else:
        host_prefix, container_prefix = mapping.split(":", 1)
    host_norm = host_prefix.replace("\\", "/").rstrip("/")
    container_norm = container_prefix.replace("\\", "/").rstrip("/") or "/"
    value_norm = text.replace("\\", "/")
    # Also try resolving relative host prefixes against CWD when needed.
    try:
        value_abs = Path(text).resolve().as_posix()
    except OSError:
        value_abs = value_norm
    for candidate in (value_norm, value_abs):
        if candidate == host_norm or candidate.startswith(host_norm + "/"):
            suffix = candidate[len(host_norm) :]
            return (container_norm + suffix).replace("//", "/") or container_norm
    return text


def _parse_cli_payload(stdout: str) -> Any | None:
    text = (stdout or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Some CLIs emit a trailing JSON object after progress logs.
    for start in (text.rfind("{"), text.rfind("[")):
        if start < 0:
            continue
        snippet = text[start:]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            continue
    return {"text": text}
