#!/usr/bin/env python3
"""Test error-chat with alternate semantics and verify Skill wiring."""
from __future__ import annotations

import json
import time

import httpx

BASE = "http://127.0.0.1:8010"
EXPECTED_SKILL = "flows/default-log-triage"
EXPECTED_ACTIONS = [
    "incident.normalize",
    "catalog.resolve_service",
    "catalog.get_log_sources",
    "log.query_by_trace_id",
    "log.query_by_template",
    "trace.get_chain",
    "index.get_status",
    "repo.list",
    "code.search",
    "code.read",
    "notify.send",
]

PAYLOAD = {
    "content": (
        "ConnectionTimeoutError: Apollo config center unreachable after 30s\n"
        "at src/apollo_mcp/server.py:88 in fetch_namespace_config\n"
        "service: apollo-gateway env: staging severity: critical\n"
        "trace_id: skill-e2e-trace-apollo-001\n"
        "error_code: APOLLO_CONFIG_TIMEOUT upstream=meta.server.com"
    ),
    "service_name": "apollo-gateway",
    "environment": "staging",
    "severity": "critical",
    "trace_id": "skill-e2e-trace-apollo-001",
}


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=180.0, trust_env=False)

    print("=== Skill 注册检查 ===")
    skills = client.get("/api/skills").json()["items"]
    slugs = [s["slug"] for s in skills]
    print("registered_skills:", slugs)
    assert EXPECTED_SKILL in slugs, f"missing builtin skill {EXPECTED_SKILL}"

    skill_detail = client.get(f"/api/skills/{EXPECTED_SKILL}").json()
    skill_steps = [s["action"] for s in skill_detail.get("steps", [])]
    print("skill_step_actions:", skill_steps)
    assert skill_steps == EXPECTED_ACTIONS, "skill spec steps mismatch"

    skill_content = client.get(f"/api/skills/{EXPECTED_SKILL}/content").json()
    print("skill_md_lines:", len(skill_content.get("skill_md", "").splitlines()))
    print("references:", len(skill_content.get("references", [])))

    print("\n=== 提交语义不同的错误 ===")
    item = client.post("/api/error-chat", json=PAYLOAD).json()["item"]
    item_id = item["id"]
    case = item["case"]
    print("item_id", item_id)
    print("symptom_preview:", item["content"][:120])

    print("\n=== Skill 绑定验证 ===")
    print("selected_skills:", case.get("selected_skills"))
    assert case.get("selected_skills") == [EXPECTED_SKILL]

    step_actions = [s.get("action") for s in case.get("steps", [])]
    step_skills = {s.get("skill_name") for s in case.get("steps", [])}
    step_status = {s.get("step_id"): s.get("status") for s in case.get("steps", [])}
    print("executed_actions:", step_actions)
    print("step_skill_names:", step_skills)
    assert step_skills == {EXPECTED_SKILL}
    assert step_actions == EXPECTED_ACTIONS
    assert all(status == "completed" for status in step_status.values())

    print("\n=== 工具与代码证据 ===")
    for tool in item.get("tool_results", []):
        name = tool.get("tool_name")
        content = tool.get("content") or {}
        if name == "incident.normalize":
            extracted = content.get("extracted") or {}
            print("normalized_service:", extracted.get("service_name"))
            print("normalized_trace:", extracted.get("trace_id"))
            print("normalized_code_path:", extracted.get("code_path"))
        if name == "code.search":
            print("code_search_query:", content.get("query"))
            print("code_search_total:", content.get("total"))
            if content.get("hits"):
                hit = content["hits"][0]
                print("code_search_top:", hit.get("repo"), hit.get("path"))
        if name == "code.read":
            preview = (content.get("content") or "")[:120].replace("\n", " ")
            print("code_read_path:", content.get("path"), "repo:", content.get("repo"))
            print("code_read_preview:", preview)

    print("\n=== 等待 AI 分析 ===")
    final = item
    for i in range(25):
        if final.get("ai_analysis", {}).get("pending") is not True:
            break
        time.sleep(2)
        final = next(x for x in client.get("/api/error-chat").json()["items"] if x["id"] == item_id)

    ai = final.get("ai_analysis", {})
    print("ai_ok:", ai.get("ok"), "pending:", ai.get("pending"))
    summary = ai.get("summary") or ""
    print("ai_summary_preview:", str(summary)[:500])

    checks = {
        "skill_registered": EXPECTED_SKILL in slugs,
        "skill_steps_match": skill_steps == EXPECTED_ACTIONS,
        "case_selected_skill": case.get("selected_skills") == [EXPECTED_SKILL],
        "all_steps_completed": all(s.get("status") == "completed" for s in case.get("steps", [])),
        "code_search_has_hits": any(
            (t.get("content") or {}).get("total", 0) > 0
            for t in item.get("tool_results", [])
            if t.get("tool_name") == "code.search"
        ),
        "ai_ok": bool(ai.get("ok")),
    }
    print("\n=== 结论 ===")
    for k, v in checks.items():
        print(f"  {k}: {v}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
