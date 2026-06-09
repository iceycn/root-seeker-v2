from __future__ import annotations

import re

from rootseeker.contracts.log_query import LogQueryResult

__all__ = ["redact_log_result"]

_SENSITIVE = re.compile(r"(?i)(password|secret|token)\s*[:=]\s*\S+")


def redact_log_result(result: LogQueryResult) -> LogQueryResult:
    redacted = result.model_copy(deep=True)
    for record in redacted.records:
        record.message = _SENSITIVE.sub(r"\1=***", record.message)
    redacted.metadata["redacted"] = True
    return redacted
