from __future__ import annotations

import os
import sys


def _noninteractive() -> bool:
    if os.environ.get("ROOTSEEKER_SETUP_NONINTERACTIVE", "").strip() in {"1", "true", "yes"}:
        return True
    return not sys.stdin.isatty()


def info(msg: str) -> None:
    print(f"[信息] {msg}")


def ok(msg: str) -> None:
    print(f"[完成] {msg}")


def warn(msg: str) -> None:
    print(f"[警告] {msg}")


def error(msg: str) -> None:
    print(f"[错误] {msg}", file=sys.stderr)


def confirm(prompt: str, default: bool = True) -> bool:
    if _noninteractive():
        return default
    suffix = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{prompt} [{suffix}]: ").strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes", "是"}:
            return True
        if raw in {"n", "no", "否"}:
            return False
        print("请输入 y 或 n")


def choose(prompt: str, options: list[tuple[str, str]], default: str) -> str:
    """options: list of (id, Chinese label)."""
    ids = {opt_id for opt_id, _ in options}
    if default not in ids:
        default = options[0][0]
    if _noninteractive():
        return default
    print(prompt)
    for index, (opt_id, label) in enumerate(options, start=1):
        marker = " (默认)" if opt_id == default else ""
        print(f"  {index}. {label}{marker}")
    while True:
        raw = input("请选择序号: ").strip()
        if not raw:
            return default
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1][0]
        for opt_id, label in options:
            if raw == opt_id or raw == label:
                return opt_id
        print("无效选择，请重试")


def ask(prompt: str, default: str = "") -> str:
    if _noninteractive():
        return default
    suffix = f" [{default}]" if default else ""
    raw = input(f"{prompt}{suffix}: ").strip()
    return raw if raw else default
