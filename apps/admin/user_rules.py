"""Username / password input rules for Admin users."""

from __future__ import annotations

import re

__all__ = ["USERNAME_RE", "password_error", "username_error"]

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,64}$")


def username_error(username: str) -> str | None:
    if not USERNAME_RE.fullmatch(username or ""):
        return "用户名须为 3–64 位字母、数字、点、下划线或连字符"
    return None


def password_error(password: str) -> str | None:
    text = password or ""
    byte_len = len(text.encode("utf-8"))
    if len(text) < 8 or byte_len > 72:
        return "密码须为至少 8 个字符，且 UTF-8 编码不超过 72 字节"
    return None
