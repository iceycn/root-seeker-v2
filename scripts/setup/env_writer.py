from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

_SECRET_KEY_RE = re.compile(r"(API_KEY|PASSWORD|SECRET|TOKEN|ROOT_PASSWORD)", re.I)


def _is_secret_key(key: str) -> bool:
    return _SECRET_KEY_RE.search(key) is not None


def _parse_env_lines(text: str) -> tuple[list[str], dict[str, str]]:
    """Return (order markers, key->value)."""
    values: dict[str, str] = {}
    order: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            order.append(line)
            continue
        if "=" not in stripped:
            order.append(line)
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        values[key] = value
        order.append(f"__KEY__:{key}")
    return order, values


def merge_env_file(
    path: Path,
    updates: dict[str, str],
    *,
    overwrite_existing: bool = False,
) -> None:
    """Merge key=value pairs into an .env file atomically.

    When ``overwrite_existing`` is False, existing secret-like keys
    (API_KEY/PASSWORD/SECRET/TOKEN/...) keep their values; other keys update.
    """
    existing_text = path.read_text(encoding="utf-8") if path.exists() else ""
    order, values = _parse_env_lines(existing_text)

    for key, value in updates.items():
        if (
            key in values
            and not overwrite_existing
            and _is_secret_key(key)
            and values[key] != ""
        ):
            continue
        if key not in values:
            order.append(f"__KEY__:{key}")
        values[key] = value

    lines: list[str] = []
    seen: set[str] = set()
    for item in order:
        if item.startswith("__KEY__:"):
            key = item.removeprefix("__KEY__:")
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"{key}={values[key]}")
        else:
            lines.append(item)
    for key, value in values.items():
        if key not in seen:
            lines.append(f"{key}={value}")

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(lines)
    if payload and not payload.endswith("\n"):
        payload += "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=".env-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
