from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ExecApprovalGuard", "ExecApprovalResult"]


@dataclass
class ExecApprovalResult:
    approved: bool
    reason: str = ""


class ExecApprovalGuard:
    def __init__(self, *, allow_patterns: list[str] | None = None, deny_all: bool = False) -> None:
        self._allow_patterns = allow_patterns or []
        self._deny_all = deny_all

    def check(self, command: str) -> ExecApprovalResult:
        if self._deny_all:
            return ExecApprovalResult(approved=False, reason="execution denied by policy")
        if not self._allow_patterns:
            return ExecApprovalResult(approved=True, reason="no allowlist configured")
        approved = any(command.startswith(prefix) for prefix in self._allow_patterns)
        return ExecApprovalResult(
            approved=approved,
            reason="matched allowlist" if approved else "command not in allowlist",
        )
