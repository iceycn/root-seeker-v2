from __future__ import annotations

import os
from urllib.parse import quote, urlparse, urlunparse

__all__ = ["GitCredentials", "build_authenticated_git_url", "mask_git_url"]


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


def build_authenticated_git_url(url: str, *, provider: str, username: str, token: str) -> str:
    """Embed HTTPS credentials for non-interactive git clone/pull in containers."""
    if not url or not token:
        return url
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return url

    provider = (provider or "").lower()
    if provider == "codeup":
        provider = "yunxiao"

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
