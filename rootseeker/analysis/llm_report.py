from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from rootseeker.analysis.root_cause_engine import RootCauseAnalysisResult
from rootseeker.contracts.evidence import ContextWindow, EvidencePack, RootCauseConclusion
from rootseeker.contracts.report import CaseReport
from rootseeker.infra_core.openai_compat import (
    build_openai_compat_chat_payload,
    build_openai_compat_headers,
)
from rootseeker.infra_core.settings import RootSeekerSettings

__all__ = [
    "LlmReportConfig",
    "LlmReportResult",
    "OpenAICompatibleReportClient",
    "apply_llm_report_result",
    "build_llm_http_timeout",
    "parse_llm_report_content",
]


SYSTEM_PROMPT = (
    "你是 RootSeeker 根因分析助手。请基于结构化证据、上下文窗口和规则引擎候选结论，"
    "输出一个紧凑 JSON 对象，不要输出 Markdown。JSON 字段：summary, root_cause, "
    "next_actions。其中 root_cause 包含 title, narrative, confidence, contributing_factors。"
)


@dataclass(frozen=True)
class LlmReportConfig:
    base_url: str
    api_key: str
    model: str
    provider_name: str = "openai_compatible"
    timeout_seconds: float = 180.0
    temperature: float = 0.2
    max_evidence_items: int = 8
    enabled: bool = True
    max_retries: int = 1

    @classmethod
    def from_settings(cls, settings: RootSeekerSettings | None = None) -> LlmReportConfig | None:
        settings = settings or RootSeekerSettings()
        if not settings.llm_enabled:
            return None
        base_url = (settings.llm_base_url or "").strip().rstrip("/")
        api_key = (settings.llm_api_key or "").strip()
        model = (settings.llm_model or "").strip()
        if not base_url or not api_key or not model:
            return None
        return cls(
            base_url=base_url,
            api_key=api_key,
            model=model,
            provider_name=settings.llm_provider_name,
            timeout_seconds=settings.llm_timeout_seconds,
            temperature=settings.llm_temperature,
            max_evidence_items=settings.llm_max_evidence_items,
            enabled=settings.llm_enabled,
        )


@dataclass
class LlmReportResult:
    ok: bool
    skipped: bool = False
    provider: str | None = None
    model: str | None = None
    elapsed_ms: int | None = None
    content: str = ""
    parsed: dict[str, Any] | None = None
    raw: dict[str, Any] | None = None
    error: str | None = None
    reason: str | None = None

    def to_payload(
        self, *, include_content: bool = True, include_raw: bool = False
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "skipped": self.skipped,
            "provider": self.provider,
            "model": self.model,
            "elapsed_ms": self.elapsed_ms,
            "parsed": self.parsed is not None,
        }
        if self.reason:
            payload["reason"] = self.reason
        if self.error:
            payload["error"] = self.error
        if include_content and self.content:
            payload["content"] = self.content
        if self.raw:
            usage = self.raw.get("usage")
            if usage is not None:
                payload["usage"] = usage
        if include_raw and self.raw is not None:
            payload["raw"] = self.raw
        return {key: value for key, value in payload.items() if value is not None}


class OpenAICompatibleReportClient:
    def __init__(
        self,
        config: LlmReportConfig,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config
        self._transport = transport

    def analyze_case(
        self,
        *,
        case_id: str,
        title: str,
        pack: EvidencePack,
        context: ContextWindow,
        analysis: RootCauseAnalysisResult,
    ) -> LlmReportResult:
        messages = build_llm_report_messages(
            case_id=case_id,
            title=title,
            pack=pack,
            context=context,
            analysis=analysis,
            max_evidence_items=self.config.max_evidence_items,
        )
        result = self.complete(messages)
        if result.content:
            result.parsed = parse_llm_report_content(result.content)
        return result

    def complete(self, messages: list[dict[str, str]]) -> LlmReportResult:
        if not self.config.enabled:
            return LlmReportResult(
                ok=False,
                skipped=True,
                provider=self.config.provider_name,
                model=self.config.model,
                reason="disabled",
            )
        request_payload = build_openai_compat_chat_payload(
            base_url=self.config.base_url,
            model=self.config.model,
            messages=messages,
            temperature=self.config.temperature,
        )
        http_timeout = build_llm_http_timeout(self.config.timeout_seconds)
        max_attempts = max(1, int(self.config.max_retries) + 1)
        client_kwargs: dict[str, Any] = {
            "timeout": http_timeout,
            "trust_env": False,
        }
        if self._transport is not None:
            client_kwargs["transport"] = self._transport
        last_error: str | None = None
        for attempt in range(max_attempts):
            try:
                started = time.perf_counter()
                with httpx.Client(**client_kwargs) as client:
                    response = client.post(
                        f"{self.config.base_url}/chat/completions",
                        headers=build_openai_compat_headers(self.config.api_key),
                        json=request_payload,
                    )
                    elapsed_ms = int((time.perf_counter() - started) * 1000)
                    response.raise_for_status()
                    data = response.json()
                return LlmReportResult(
                    ok=True,
                    provider=self.config.provider_name,
                    model=self.config.model,
                    elapsed_ms=elapsed_ms,
                    content=_extract_message_content(data),
                    raw=data,
                )
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text[:500] if exc.response is not None else ""
                return LlmReportResult(
                    ok=False,
                    provider=self.config.provider_name,
                    model=self.config.model,
                    error=f"{exc}. body: {detail}",
                )
            except (httpx.ReadTimeout, httpx.TimeoutException) as exc:
                last_error = str(exc)
                if attempt + 1 < max_attempts:
                    continue
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                break
        return LlmReportResult(
            ok=False,
            provider=self.config.provider_name,
            model=self.config.model,
            error=last_error or "LLM request failed",
        )


def build_llm_http_timeout(read_seconds: float) -> httpx.Timeout:
    """Use a generous read timeout for slow coding-model responses."""
    read_timeout = max(30.0, float(read_seconds))
    return httpx.Timeout(connect=30.0, read=read_timeout, write=30.0, pool=30.0)


def build_llm_report_messages(
    *,
    case_id: str,
    title: str,
    pack: EvidencePack,
    context: ContextWindow,
    analysis: RootCauseAnalysisResult,
    max_evidence_items: int,
) -> list[dict[str, str]]:
    payload = {
        "case": {"case_id": case_id, "title": title},
        "evidence_summary": pack.summary,
        "rule_analysis": {
            "conclusion": analysis.conclusion.model_dump(mode="json"),
            "hypotheses": [item.model_dump(mode="json") for item in analysis.hypotheses],
            "converged": analysis.is_converged,
        },
        "context_window": context.model_dump(mode="json"),
        "evidence_preview": [
            item.model_dump(mode="json") for item in pack.items[: max(1, max_evidence_items)]
        ],
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def apply_llm_report_result(report: CaseReport, result: LlmReportResult) -> CaseReport:
    metadata = dict(report.metadata)
    metadata["llm"] = result.to_payload(include_content=False)

    if not result.ok or not result.content:
        return report.model_copy(update={"metadata": metadata})

    parsed = result.parsed or parse_llm_report_content(result.content)
    if parsed is None:
        metadata["llm_analysis"] = {"text": result.content}
        metadata["builder"] = "root_cause_engine+llm"
        return report.model_copy(update={"summary": result.content, "metadata": metadata})

    metadata["llm_analysis"] = parsed
    metadata["builder"] = "root_cause_engine+llm"
    if report.root_cause is not None:
        metadata["rule_root_cause"] = report.root_cause.model_dump(mode="json")

    summary = _as_text(parsed.get("summary")) or report.summary
    root_cause = _build_root_cause_from_parsed(parsed, report.root_cause)
    return report.model_copy(
        update={"summary": summary, "root_cause": root_cause, "metadata": metadata}
    )


def parse_llm_report_content(content: str) -> dict[str, Any] | None:
    text = _strip_code_fence(content.strip())
    for candidate in (text, _first_json_object(text)):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _extract_message_content(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts).strip()
    return ""


def _strip_code_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()


def _first_json_object(text: str) -> str | None:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    return match.group(0) if match else None


def _build_root_cause_from_parsed(
    parsed: dict[str, Any],
    fallback: RootCauseConclusion | None,
) -> RootCauseConclusion:
    root_node = parsed.get("root_cause")
    if not isinstance(root_node, dict):
        root_node = {}
    fallback_title = fallback.title if fallback is not None else "LLM analysis"
    fallback_narrative = fallback.narrative if fallback is not None else ""
    fallback_confidence = fallback.confidence if fallback is not None else 0.0
    fallback_factors = fallback.contributing_factors if fallback is not None else []
    title = _as_text(root_node.get("title") or parsed.get("root_cause_title")) or fallback_title
    narrative = (
        _as_text(root_node.get("narrative") or parsed.get("root_cause_narrative"))
        or fallback_narrative
    )
    confidence = _coerce_confidence(
        root_node.get("confidence", parsed.get("confidence")),
        fallback_confidence,
    )
    factors = _string_list(
        root_node.get("contributing_factors") or parsed.get("contributing_factors")
    )
    if not factors:
        factors = list(fallback_factors)
    return RootCauseConclusion(
        title=title,
        narrative=narrative,
        confidence=confidence,
        contributing_factors=factors,
    )


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _coerce_confidence(value: Any, fallback: float) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = fallback
    return min(1.0, max(0.0, confidence))
