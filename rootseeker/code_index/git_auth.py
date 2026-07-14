from __future__ import annotations

import os
import re
from urllib.parse import quote, urlparse, urlunparse

__all__ = [
    "GitCredentials",
    "assert_git_url_allowed_for_provider",
    "build_authenticated_git_url",
    "git_url_host_allowed",
    "mask_git_url",
    "normalize_git_provider",
    "sanitize_git_error_message",
]

_PROVIDER_GIT_HOST_SUFFIXES: dict[str, tuple[str, ...]] = {
    "github": ("github.com",),
    "gitee": ("gitee.com",),
    "yunxiao": ("codeup.aliyun.com",),
}

_AUTH_URL_IN_TEXT_RE = re.compile(
    r"https?://[^/\s:@]+:[^/\s@]+@[^\s'\"]+",
    re.IGNORECASE,
)


class GitCredentials:
    __slots__ = ("username", "token", "provider")

    def __init__(self, *, username: str, token: str, provider: str = "") -> None:
        self.username = username.strip()
        self.token = token.strip()
        self.provider = provider.strip().lower()


def _default_git_username(provider: str) -> str:
    if provider == "github":
        return "x-access-token"
    if provider == "gitee":
        return "oauth2"
    if provider in {"yunxiao", "codeup"}:
        return os.getenv("ROOTSEEKER_CODEUP_GIT_USERNAME", "").strip()
    return ""


def normalize_git_provider(provider: str) -> str:
    value = (provider or "").strip().lower()
    if value == "codeup":
        return "yunxiao"
    return value or "custom"


def git_url_host_allowed(url: str, provider: str) -> bool:
    """Return True when an HTTPS git URL host matches the credential provider."""
    normalized = normalize_git_provider(provider)
    if normalized == "custom":
        return True
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    suffixes = _PROVIDER_GIT_HOST_SUFFIXES.get(normalized)
    if not suffixes:
        return True
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in suffixes)


def assert_git_url_allowed_for_provider(url: str, provider: str) -> None:
    normalized = normalize_git_provider(provider)
    if git_url_host_allowed(url, provider):
        return
    host = urlparse(url).hostname or ""
    raise ValueError(
        f"仓库 URL 域名「{host}」与远端源 provider「{normalized}」不匹配，已拒绝注入凭据"
    )


def build_authenticated_git_url(url: str, *, provider: str, username: str, token: str) -> str:
    """Embed HTTPS credentials for non-interactive git clone/pull in containers."""
    if not url or not token:
        return url
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return url

    provider = normalize_git_provider(provider)
    assert_git_url_allowed_for_provider(url, provider)

    user = username.strip() or _default_git_username(provider)
    if not user:
        raise ValueError(
            "云效 Codeup 缺少 HTTPS 克隆账号（git_username）。"
            "请任选其一："
            "① Admin → 仓库管理 → 远端源管理 → 编辑 codeup → 填写「HTTPS 克隆账号」"
            "（Codeup → 个人设置 → HTTPS 密码 → 克隆账号）；"
            "② 在 .env 中设置 ROOTSEEKER_CODEUP_GIT_USERNAME 后重启容器。"
            "注意：克隆账号不是 organizationId，也不是登录邮箱。"
        )

    safe_user = quote(user, safe="")
    safe_token = quote(token, safe="")
    host = parsed.hostname or ""
    netloc = f"{safe_user}:{safe_token}@{host}"
    if parsed.port:
        netloc = f"{safe_user}:{safe_token}@{host}:{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


def mask_git_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.username:
        return url
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunparse(parsed._replace(netloc=f"***:***@{host}"))


def sanitize_git_error_message(message: str) -> str:
    """Remove embedded git credentials from error text before persisting or returning."""
    if not message:
        return message
    sanitized = message
    for match in _AUTH_URL_IN_TEXT_RE.finditer(message):
        sanitized = sanitized.replace(match.group(0), mask_git_url(match.group(0)))
    sanitized = re.sub(
        r"(https?://)([^/\s:@]+):([^/\s@]+)@",
        r"\1***:***@",
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized
