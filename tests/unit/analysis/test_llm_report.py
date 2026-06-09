from __future__ import annotations

import json

import httpx

from rootseeker.analysis import LlmReportConfig, OpenAICompatibleReportClient, build_case_report
from rootseeker.contracts.evidence import EvidenceItem, EvidencePack, EvidenceType
from rootseeker.infra_core.settings import RootSeekerSettings


def _pack() -> EvidencePack:
    return EvidencePack(
        case_id="case-llm",
        summary="default flow evidence",
        items=[
            EvidenceItem(
                item_id="log-1",
                type=EvidenceType.LOG,
                source="log.query_by_trace_id",
                content={"message": "error: database connection timeout"},
            )
        ],
    )


def _llm_transport(seen: dict[str, object]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "LLM 判断数据库连接超时导致请求失败。",
                                    "root_cause": {
                                        "title": "数据库连接超时",
                                        "narrative": "日志证据显示数据库连接持续 timeout。",
                                        "confidence": 0.82,
                                        "contributing_factors": ["数据库连接池耗尽"],
                                    },
                                    "next_actions": ["检查连接池和数据库慢查询"],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 18},
            },
        )

    return httpx.MockTransport(handler)


def test_llm_config_from_settings_requires_enabled_and_required_fields() -> None:
    disabled = RootSeekerSettings(
        llm_enabled=False,
        llm_base_url="https://llm.example/v1",
        llm_api_key="secret",
        llm_model="triage-model",
    )
    assert LlmReportConfig.from_settings(disabled) is None

    settings = RootSeekerSettings(
        llm_base_url="https://llm.example/v1/",
        llm_api_key="secret",
        llm_model="triage-model",
        llm_provider_name="unit-provider",
    )
    config = LlmReportConfig.from_settings(settings)

    assert config is not None
    assert config.base_url == "https://llm.example/v1"
    assert config.provider_name == "unit-provider"


def test_build_case_report_uses_llm_to_enhance_report() -> None:
    seen: dict[str, object] = {}
    client = OpenAICompatibleReportClient(
        LlmReportConfig(
            base_url="https://llm.example/v1",
            api_key="secret",
            model="triage-model",
            provider_name="unit-provider",
        ),
        transport=_llm_transport(seen),
    )

    report = build_case_report(
        case_id="case-llm",
        title="Checkout failure",
        pack=_pack(),
        llm_client=client,
    )

    assert seen["url"] == "https://llm.example/v1/chat/completions"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["model"] == "triage-model"
    assert body["temperature"] == 0.2
    assert report.summary == "LLM 判断数据库连接超时导致请求失败。"
    assert report.root_cause is not None
    assert report.root_cause.title == "数据库连接超时"
    assert report.root_cause.confidence == 0.82
    assert report.metadata["builder"] == "root_cause_engine+llm"
    assert report.metadata["llm"]["ok"] is True
    assert report.metadata["llm"]["provider"] == "unit-provider"
    assert "rule_root_cause" in report.metadata


def test_build_case_report_marks_llm_disabled() -> None:
    report = build_case_report(
        case_id="case-disabled",
        title="No LLM",
        pack=_pack(),
        settings=RootSeekerSettings(llm_enabled=False),
    )

    assert report.root_cause is not None
    assert report.metadata["builder"] == "root_cause_engine"
    assert report.metadata["llm"]["skipped"] is True
    assert report.metadata["llm"]["reason"] == "disabled"
