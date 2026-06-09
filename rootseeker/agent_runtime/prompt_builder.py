from __future__ import annotations

import json
from typing import Any

from rootseeker.contracts.case import CaseCreateRequest

__all__ = ["PromptBuilder"]


class PromptBuilder:
    """Build the auditable prompt snapshot used by an Agent attempt."""

    def build_messages(
        self,
        case_request: CaseCreateRequest,
        *,
        history_summary: str | None = None,
    ) -> list[dict[str, str]]:
        metadata = _stable_json(case_request.metadata)
        user_parts = [
            f"title: {case_request.title}",
            f"service_name: {case_request.service_name}",
            f"source: {case_request.source}",
            f"symptom: {case_request.symptom}",
            f"metadata: {metadata}",
        ]
        if history_summary:
            user_parts.append(f"history_summary: {history_summary}")
        return [
            {
                "role": "system",
                "content": (
                    "You are RootSeeker Agent Runtime. Execute the incident triage plan, "
                    "collect tool evidence through MCP, and keep each attempt replayable."
                ),
            },
            {"role": "user", "content": "\n".join(user_parts)},
        ]


def _stable_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
