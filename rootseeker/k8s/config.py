"""Kubernetes reader settings.

Log lookback defaults to ``ROOTSEEKER_K8S_LOG_WINDOW_MINUTES`` (5 minutes).
In-cluster credentials are read from the ServiceAccount mount when present.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

__all__ = ["K8sConfig"]

_SA_DIR = Path("/var/run/secrets/kubernetes.io/serviceaccount")
_SA_TOKEN = _SA_DIR / "token"
_SA_CA = _SA_DIR / "ca.crt"
_SA_NAMESPACE = _SA_DIR / "namespace"
_IN_CLUSTER_API = "https://kubernetes.default.svc"


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _bool_env(name: str, default: bool) -> bool:
    raw = _env(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = _env(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


@dataclass(frozen=True)
class K8sConfig:
    enabled: bool = False
    api_server: str = ""
    token: str = ""
    ca_cert: str = ""
    namespace: str = ""
    verify_ssl: bool = True
    timeout_seconds: float = 15.0
    log_window_minutes: int = 5
    log_tail_lines: int = 500

    @classmethod
    def from_env(cls) -> K8sConfig:
        token = _env("ROOTSEEKER_K8S_TOKEN") or _read_text(_SA_TOKEN)
        ca_cert = _env("ROOTSEEKER_K8S_CA_CERT")
        if not ca_cert and _SA_CA.is_file():
            ca_cert = str(_SA_CA)
        namespace = _env("ROOTSEEKER_K8S_NAMESPACE") or _read_text(_SA_NAMESPACE)
        api_server = _env("ROOTSEEKER_K8S_API_SERVER").rstrip("/")
        if not api_server and token:
            api_server = _IN_CLUSTER_API
        window = _int_env("ROOTSEEKER_K8S_LOG_WINDOW_MINUTES", 5)
        return cls(
            enabled=_bool_env("ROOTSEEKER_K8S_ENABLED", False),
            api_server=api_server,
            token=token,
            ca_cert=ca_cert,
            namespace=namespace,
            verify_ssl=_bool_env("ROOTSEEKER_K8S_VERIFY_SSL", True),
            timeout_seconds=_float_env("ROOTSEEKER_K8S_TIMEOUT_SECONDS", 15.0),
            log_window_minutes=window if window > 0 else 5,
            log_tail_lines=max(1, _int_env("ROOTSEEKER_K8S_LOG_TAIL_LINES", 500)),
        )

    def is_ready(self) -> bool:
        return self.enabled and bool(self.api_server) and bool(self.token)

    def disabled_reason(self) -> str:
        if not self.enabled:
            return "ROOTSEEKER_K8S_ENABLED 未开启"
        if not self.token:
            return "缺少 Kubernetes token（ROOTSEEKER_K8S_TOKEN 或集群 ServiceAccount）"
        if not self.api_server:
            return "缺少 ROOTSEEKER_K8S_API_SERVER"
        return ""
