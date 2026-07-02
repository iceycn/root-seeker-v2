#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:8010"
PAYLOAD = {
    "content": (
        "RuntimeError in rootseeker flow runtime at "
        "rootseeker/flow_runtime/runtime.py:42\n"
        "service: rootseeker-api env: prod severity: error\n"
        "trace_id: e2e-test-trace-003\n"
        "message: Failed to execute default flow during error triage"
    ),
    "service_name": "rootseeker-api",
    "environment": "prod",
    "severity": "error",
    "trace_id": "e2e-test-trace-003",
}


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=180.0, trust_env=False)

    print("=== 1. 提交错误排查 ===")
    resp = client.post("/api/error-chat", json=PAYLOAD)
    print("status", resp.status_code)
    if resp.status_code != 200:
        print(resp.text[:1000])
        return 1
    item = resp.json()["item"]
    item_id = item["id"]
    case = item.get("case", {})
    print("item_id", item_id)
    print("case_id", case.get("case_id"))
    print("case_status", case.get("status"))
    print("flow_elapsed_ms", item.get("flow_elapsed_ms"))
    print("evidence_count", item.get("evidence_count"))
    print("root_cause", item.get("report", {}).get("root_cause"))
    print("ai_initial", {k: item.get("ai_analysis", {}).get(k) for k in ("ok", "pending", "reason", "error")})

    print("\n=== 2. Flow 步骤 ===")
    for step in case.get("steps", []):
        print(f"  {step.get('step_id')}: {step.get('status')} action={step.get('action')}")

    print("\n=== 3. 工具调用 ===")
    for tool in item.get("tool_results", []):
        name = tool.get("tool_name")
        ok = tool.get("ok")
        content = tool.get("content") or {}
        keys = list(content.keys())[:6]
        skipped = content.get("skipped")
        error = content.get("error") or content.get("detail")
        extra = ""
        if name == "code.search" and content.get("hits"):
            extra = f" hits={len(content['hits'])}"
        elif name == "repo.list" and content.get("repos"):
            extra = f" repos={len(content['repos'])}"
        elif name == "index.get_status":
            extra = f" ready={content.get('ready')}"
        print(f"  {name}: ok={ok} skipped={skipped} keys={keys}{extra} err={error}")

    print("\n=== 4. 等待 AI 分析 ===")
    final = item
    for attempt in range(30):
        if not final.get("ai_analysis", {}).get("pending"):
            break
        time.sleep(2)
        items = client.get("/api/error-chat").json().get("items", [])
        final = next((x for x in items if x.get("id") == item_id), final)
        print(f"  poll {attempt + 1}: pending={final.get('ai_analysis', {}).get('pending')}")

    ai = final.get("ai_analysis", {})
    print("ai_final", {k: ai.get(k) for k in ("ok", "pending", "reason", "error")})
    summary = ai.get("summary") or ai.get("analysis") or ai.get("content")
    if summary:
        text = summary if isinstance(summary, str) else json.dumps(summary, ensure_ascii=False)
        print("ai_summary_preview:", text[:600])

    print("\n=== 5. 结论 ===")
    steps = final.get("case", {}).get("steps", [])
    failed = [s for s in steps if s.get("status") == "failed"]
    tool_ok = sum(1 for t in final.get("tool_results", []) if t.get("ok"))
    tool_total = len(final.get("tool_results", []))
    code_search = next((t for t in final.get("tool_results", []) if t.get("tool_name") == "code.search"), None)
    code_read = next((t for t in final.get("tool_results", []) if t.get("tool_name") == "code.read"), None)
    cs_content = (code_search or {}).get("content") or {}
    cr_content = (code_read or {}).get("content") or {}

    checks = {
        "flow_completed": final.get("case", {}).get("status") in {"completed", "succeeded", "closed"},
        "no_failed_steps": len(failed) == 0,
        "tools_ok": f"{tool_ok}/{tool_total}",
        "code_search_hit": bool(code_search and code_search.get("ok") and cs_content.get("total", 0) > 0),
        "code_read_ok": bool(code_read and code_read.get("ok") and cr_content.get("content")),
        "ai_done": ai.get("pending") is not True,
        "ai_ok": bool(ai.get("ok")),
    }
    for k, v in checks.items():
        print(f"  {k}: {v}")
    if failed:
        print("  failed_steps:", [s.get("step_id") for s in failed])

    return 0 if checks["no_failed_steps"] and checks["ai_done"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
