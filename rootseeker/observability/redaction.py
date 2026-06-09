from __future__ import annotations

import re
from typing import Any

__all__ = ["redact_value", "redact_payload"]

_SENSITIVE_KEYS = {"token", "secret", "password", "api_key", "authorization"}
_PEM_RE = re.compile(r"-----BEGIN [A-Z ]+-----.*?-----END [A-Z ]+-----", re.S)


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        redacted = _PEM_RE.sub("[REDACTED_PEM]", value)
        if len(redacted) > 8 and ("token" in redacted.lower() or "secret" in redacted.lower()):
            return "[REDACTED]"
        return redacted
    if isinstance(value, dict):
        return redact_payload(value)
    if isinstance(value, list):
        return [redact_value(v) for v in value]
    return value


def redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in payload.items():
        if key.lower() in _SENSITIVE_KEYS:
            output[key] = "[REDACTED]"
        else:
            output[key] = redact_value(value)
    return output
