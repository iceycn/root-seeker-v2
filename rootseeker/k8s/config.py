"""Kubernetes reader settings.

Log lookback defaults to ``ROOTSEEKER_K8S_LOG_WINDOW_MINUTES`` (5 minutes).
Credentials are resolved in this order: explicit ``ROOTSEEKER_K8S_*`` values,
the in-cluster ServiceAccount mount, then a kubeconfig file (``ROOTSEEKER_K8S_KUBECONFIG``,
``KUBECONFIG``, or ``~/.kube/config``). kubeconfig may use a bearer token or
client certificates. ``ROOTSEEKER_K8S_ENABLED=false`` remains an explicit off switch.
"""

from __future__ import annotations

import base64
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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


def _env_flag(name: str) -> bool | None:
    raw = _env(name).lower()
    if not raw:
        return None
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return None


@dataclass(frozen=True)
class K8sConfig:
    enabled: bool = False
    explicitly_disabled: bool = False
    api_server: str = ""
    token: str = ""
    ca_cert: str = ""
    client_cert: str = ""
    client_key: str = ""
    namespace: str = ""
    verify_ssl: bool = True
    timeout_seconds: float = 15.0
    log_window_minutes: int = 5
    log_tail_lines: int = 500
    auth_source: str = ""
    _temp_files: tuple[str, ...] = field(default=(), repr=False, compare=False)

    @classmethod
    def from_env(cls) -> K8sConfig:
        temps: list[str] = []
        token = _env("ROOTSEEKER_K8S_TOKEN") or _read_text(_SA_TOKEN)
        auth_source = ""
        if _env("ROOTSEEKER_K8S_TOKEN"):
            auth_source = "env"
        elif token:
            auth_source = "serviceaccount"

        ca_cert = _env("ROOTSEEKER_K8S_CA_CERT")
        if not ca_cert and _SA_CA.is_file():
            ca_cert = str(_SA_CA)
        namespace = _env("ROOTSEEKER_K8S_NAMESPACE") or _read_text(_SA_NAMESPACE)
        api_server = _env("ROOTSEEKER_K8S_API_SERVER").rstrip("/")
        if not api_server and token:
            api_server = _IN_CLUSTER_API

        client_cert = _env("ROOTSEEKER_K8S_CLIENT_CERT")
        client_key = _env("ROOTSEEKER_K8S_CLIENT_KEY")
        verify_ssl = _bool_env("ROOTSEEKER_K8S_VERIFY_SSL", True)

        if not api_server or not (token or (client_cert and client_key)):
            kube = _from_kubeconfig(
                context=_env("ROOTSEEKER_K8S_CONTEXT"),
                temps=temps,
            )
            if kube:
                api_server = api_server or kube.get("api_server", "")
                token = token or kube.get("token", "")
                if not client_cert:
                    client_cert = kube.get("client_cert", "")
                if not client_key:
                    client_key = kube.get("client_key", "")
                if not ca_cert:
                    ca_cert = kube.get("ca_cert", "")
                if not namespace:
                    namespace = kube.get("namespace", "")
                if kube.get("insecure"):
                    verify_ssl = False
                if not auth_source and (token or (client_cert and client_key)):
                    auth_source = "kubeconfig"

        window = _int_env("ROOTSEEKER_K8S_LOG_WINDOW_MINUTES", 5)
        enabled_flag = _env_flag("ROOTSEEKER_K8S_ENABLED")
        explicitly_disabled = enabled_flag is False
        has_creds = bool(api_server) and bool(token or (client_cert and client_key))
        if enabled_flag is False:
            enabled = False
        elif enabled_flag is True:
            enabled = True
        else:
            enabled = has_creds

        return cls(
            enabled=enabled,
            explicitly_disabled=explicitly_disabled,
            api_server=api_server,
            token=token,
            ca_cert=ca_cert,
            client_cert=client_cert,
            client_key=client_key,
            namespace=namespace,
            verify_ssl=verify_ssl,
            timeout_seconds=_float_env("ROOTSEEKER_K8S_TIMEOUT_SECONDS", 15.0),
            log_window_minutes=window if window > 0 else 5,
            log_tail_lines=max(1, _int_env("ROOTSEEKER_K8S_LOG_TAIL_LINES", 500)),
            auth_source=auth_source,
            _temp_files=tuple(temps),
        )

    def is_ready(self) -> bool:
        if self.explicitly_disabled or not self.enabled:
            return False
        return bool(self.api_server) and self._has_auth()

    def _has_auth(self) -> bool:
        return bool(self.token or (self.client_cert and self.client_key))

    def disabled_reason(self) -> str:
        if self.explicitly_disabled or not self.enabled:
            if self.explicitly_disabled:
                return "ROOTSEEKER_K8S_ENABLED 未开启"
            if not self._has_auth() or not self.api_server:
                return "缺少 Kubernetes 连接信息（kubeconfig / token / client certificate / ServiceAccount）"
            return "ROOTSEEKER_K8S_ENABLED 未开启"
        if not self._has_auth():
            return "缺少 Kubernetes 认证信息（ROOTSEEKER_K8S_TOKEN、client certificate 或集群 ServiceAccount）"
        if not self.api_server:
            return "缺少 ROOTSEEKER_K8S_API_SERVER 或 kubeconfig 中的 cluster.server"
        return ""

    def cleanup(self) -> None:
        for path in self._temp_files:
            try:
                os.unlink(path)
            except OSError:
                pass


def _from_kubeconfig(*, context: str, temps: list[str]) -> dict[str, str] | None:
    paths = _kubeconfig_paths()
    for path in paths:
        loaded = _parse_kubeconfig(path, context=context, temps=temps)
        if loaded:
            return loaded
    return None


def _kubeconfig_paths() -> list[Path]:
    raw = _env("ROOTSEEKER_K8S_KUBECONFIG") or _env("KUBECONFIG")
    if raw:
        return [Path(part.strip()) for part in raw.split(os.pathsep) if part.strip()]
    default = Path.home() / ".kube" / "config"
    return [default] if default.is_file() else []


def _parse_kubeconfig(path: Path, *, context: str, temps: list[str]) -> dict[str, str] | None:
    try:
        import yaml
    except ImportError:
        return None
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    if not isinstance(payload, dict):
        return None
    context_name = context or str(payload.get("current-context") or "")
    ctx = _named(payload.get("contexts"), context_name)
    if not ctx:
        return None
    info = ctx.get("context") if isinstance(ctx.get("context"), dict) else {}
    cluster = _named(payload.get("clusters"), str(info.get("cluster") or ""))
    user = _named(payload.get("users"), str(info.get("user") or ""))
    cluster_info = cluster.get("cluster") if cluster and isinstance(cluster.get("cluster"), dict) else {}
    user_info = user.get("user") if user and isinstance(user.get("user"), dict) else {}
    if not cluster_info:
        return None

    result: dict[str, str] = {}
    server = str(cluster_info.get("server") or "").rstrip("/")
    if not server:
        return None
    result["api_server"] = server
    namespace = str(info.get("namespace") or "")
    if namespace:
        result["namespace"] = namespace
    if cluster_info.get("insecure-skip-tls-verify") is True:
        result["insecure"] = "1"

    ca_file = _resolve_ref(path, cluster_info.get("certificate-authority"))
    ca_data = cluster_info.get("certificate-authority-data")
    if isinstance(ca_data, str) and ca_data.strip():
        result["ca_cert"] = _materialize(ca_data, ".ca.crt", temps)
    elif ca_file:
        result["ca_cert"] = ca_file

    token = str(user_info.get("token") or "")
    token_file = _resolve_ref(path, user_info.get("tokenFile") or user_info.get("token-file"))
    if not token and token_file:
        token = _read_text(Path(token_file))
    if token:
        result["token"] = token

    cert_file = _resolve_ref(path, user_info.get("client-certificate"))
    key_file = _resolve_ref(path, user_info.get("client-key"))
    cert_data = user_info.get("client-certificate-data")
    key_data = user_info.get("client-key-data")
    if isinstance(cert_data, str) and cert_data.strip():
        cert_file = _materialize(cert_data, ".client.crt", temps)
    if isinstance(key_data, str) and key_data.strip():
        key_file = _materialize(key_data, ".client.key", temps)
    if cert_file:
        result["client_cert"] = cert_file
    if key_file:
        result["client_key"] = key_file

    if not result.get("token") and not (result.get("client_cert") and result.get("client_key")):
        if isinstance(user_info.get("exec"), dict):
            result["token"] = ""  # exec auth is not supported yet
        return None
    return result


def _named(entries: Any, name: str) -> dict[str, Any] | None:
    if not name or not isinstance(entries, list):
        return None
    for item in entries:
        if isinstance(item, dict) and str(item.get("name") or "") == name:
            return item
    return None


def _resolve_ref(kubeconfig: Path, value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    path = Path(raw)
    if not path.is_absolute():
        path = (kubeconfig.parent / path).resolve()
    return str(path) if path.is_file() else ""


def _materialize(data: str, suffix: str, temps: list[str]) -> str:
    raw = base64.b64decode(data)
    handle, name = tempfile.mkstemp(prefix="rootseeker-k8s-", suffix=suffix)
    with os.fdopen(handle, "wb") as fh:
        fh.write(raw)
    temps.append(name)
    return name
