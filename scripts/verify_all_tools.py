"""Invoke every registered internal tool once and report functional status."""

from __future__ import annotations

import json
import os
import traceback
from pathlib import Path
from typing import Any

os.environ.setdefault("ROOTSEEKER_STORAGE_BACKEND", "memory")
os.environ.setdefault("ROOTSEEKER_ZOEKT_ENDPOINT", "http://127.0.0.1:6070")
os.environ.setdefault("ZOEKT_ENDPOINT", "http://127.0.0.1:6070")
os.environ.setdefault("ROOTSEEKER_QDRANT_ENDPOINT", "http://127.0.0.1:6333")
os.environ.setdefault("QDRANT_ENDPOINT", "http://127.0.0.1:6333")
os.environ.setdefault("ROOTSEEKER_REPO_BASE_PATH", "repos")

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.code_index.repo_sync import RepoSyncService
from rootseeker.contracts.tool import ToolCallRequest


ROOT = Path(__file__).resolve().parents[1]
TEMP_REPO = "_tool_verify_temp_repo"


def invoke(runtime, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    req = ToolCallRequest(
        case_id="tool-verify",
        step_id="s1",
        skill_name="flows/default-log-triage",
        tool_name=tool_name,
        arguments=arguments,
    )
    result = runtime.gateway.invoke(req, actor="tool-verify", plugin_id="builtin.default_log_triage_flow")
    return {
        "ok": bool(result.ok),
        "content": result.content if result.ok else None,
        "error": (result.error.message if result.error else None) if not result.ok else None,
    }


def summarize(content: Any, limit: int = 180) -> str:
    try:
        text = json.dumps(content, ensure_ascii=False, default=str)
    except Exception:
        text = str(content)
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def main() -> None:
    from rootseeker.contracts.repository import RepositoryRef

    real_sync_names = [
        name
        for name in ("iceycn__mcp-server-apollo", "iceycn__root_seeker")
        if (ROOT / "repos" / name / ".git").is_dir()
    ]
    repo_sync_service = RepoSyncService(
        base_path=ROOT / "repos",
        enable_zoekt=False,
        enable_qdrant=False,
    )
    if real_sync_names:
        for name in real_sync_names:
            repo_sync_service.register(
                RepositoryRef(
                    name=name,
                    url=None,
                    local_path=str((ROOT / "repos" / name).resolve()),
                    default_branch="main",
                    metadata={"source": "docker-import", "verify": "tool-verify"},
                )
            )
    else:
        print("[WARN] ./repos missing Docker imports; repo.sync/sync_all will use TEMP_REPO only")

    runtime = create_dev_runtime(ROOT, repo_sync_service=repo_sync_service)
    specs = sorted(runtime.tool_registry.list_specs(), key=lambda s: s.name)
    print(f"registered_tools={len(specs)}")
    for spec in specs:
        print(f"  - {spec.name}")

    # Pick a real indexed repo/file from Zoekt for code.read / lsp.
    from mcp_servers.external.zoekt_adapter import ZoektCodeAdapter, ZoektConfig

    zoekt = ZoektCodeAdapter(config=ZoektConfig.from_env())
    search = zoekt.search_code("create_dev_runtime", num_results=5)
    hit = (search.get("hits") or [{}])[0]
    sample_repo = str(hit.get("repo") or "iceycn__root_seeker")
    sample_path = str(hit.get("path") or "README.md")

    cases: list[tuple[str, dict[str, Any], str]] = [
        (
            "incident.normalize",
            {
                "payload": {
                    "title": "tool verify",
                    "service_name": "order-service",
                    "message": "NullPointerException at PopRecordService.insertPopRecordLogic(PopRecordService.java:42)",
                    "source": "webhook",
                    "trace_id": "trace-tool-verify",
                    "tenant": "demo",
                    "environment": "prod",
                }
            },
            "normalize",
        ),
        (
            "catalog.resolve_service",
            {"tenant": "demo", "environment": "prod", "service_name": "order-service"},
            "catalog",
        ),
        (
            "catalog.get_log_sources",
            {"tenant": "demo", "environment": "prod", "service_name": "order-service"},
            "catalog",
        ),
        (
            "log.query_by_trace_id",
            {"trace_id": "trace-tool-verify", "service_name": "order-service"},
            "external-optional",
        ),
        (
            "log.query_by_template",
            {"template_id": "default.error_window", "service_name": "order-service"},
            "external-optional",
        ),
        ("trace.get_chain", {"trace_id": "trace-tool-verify"}, "external-optional"),
        ("code.search", {"query": "create_dev_runtime"}, "code"),
        ("code.semantic_search", {"query": "create_dev_runtime", "limit": 5}, "code"),
        ("code.read", {"path": sample_path, "repo": sample_repo}, "code"),
        (
            "code.find_callers",
            {
                "call_chain": [
                    "PopRecordService.insertPopRecordLogic (PopRecordService.java:42)",
                    "MyTaskService.run (MyTaskService.java:100)",
                ],
                "service_name": "order-service",
                "limit": 10,
            },
            "code",
        ),
        ("index.get_status", {}, "code"),
        ("notify.send", {"channel": "webhook", "message": "tool-verify ping"}, "external-optional"),
        ("repo.list", {}, "repo"),
        (
            "repo.register",
            {
                "name": TEMP_REPO,
                "url": "https://github.com/example/tool-verify-temp.git",
                "branch": "main",
                "metadata": {"source": "tool-verify"},
            },
            "repo",
        ),
        ("repo.get", {"name": TEMP_REPO}, "repo"),
        ("repo.index_status", {"name": TEMP_REPO}, "repo"),
        ("repo.semantic_search", {"query": "create_dev_runtime", "limit": 5}, "code"),
        (
            "lsp.references",
            {"repo": sample_repo, "path": sample_path, "line": 1, "character": 1},
            "lsp-optional",
        ),
        (
            "lsp.definition",
            {"repo": sample_repo, "path": sample_path, "line": 1, "character": 1},
            "lsp-optional",
        ),
        (
            "lsp.hover",
            {"repo": sample_repo, "path": sample_path, "line": 1, "character": 1},
            "lsp-optional",
        ),
        (
            "lsp.symbols",
            {"repo": sample_repo, "path": sample_path},
            "lsp-optional",
        ),
        ("repo.unregister", {"name": TEMP_REPO}, "repo"),
    ]

    if real_sync_names:
        # Run real sync AFTER unregistering TEMP, so sync_all only covers Docker imports.
        cases.extend(
            [
                (
                    "repo.sync",
                    {"name": real_sync_names[0], "trigger_index": False, "force_reclone": False},
                    "repo",
                ),
                ("repo.sync_all", {"trigger_index": False}, "repo"),
            ]
        )

    rows: list[dict[str, Any]] = []
    for tool_name, args, kind in cases:
        try:
            out = invoke(runtime, tool_name, args)
            ok = out["ok"]
            content = out["content"]
            err = out["error"]
            # Optional externals: structured "not configured" still counts as functional.
            if not ok and kind in {"external-optional", "lsp-optional", "repo-optional"}:
                status = "DEGRADED"
            elif ok:
                # Some adapters return ok=False inside content.
                if isinstance(content, dict) and content.get("ok") is False and kind in {
                    "external-optional",
                    "lsp-optional",
                    "repo-optional",
                    "code",
                }:
                    status = "DEGRADED"
                elif isinstance(content, dict) and content.get("configured") is False:
                    status = "DEGRADED"
                elif tool_name == "code.read" and isinstance(content, dict) and content.get("error"):
                    status = "DEGRADED"
                elif kind == "lsp-optional" and isinstance(content, dict):
                    # Empty LSP payloads usually mean language server binary is missing.
                    if content.get("hover") is None and not content.get("items"):
                        status = "DEGRADED"
                    else:
                        status = "PASS"
                else:
                    status = "PASS"
            else:
                status = "FAIL"
            detail = summarize(content if ok else err)
            rows.append({"tool": tool_name, "status": status, "detail": detail})
            print(f"[{status}] {tool_name}: {detail}")
        except Exception as e:
            rows.append({"tool": tool_name, "status": "FAIL", "detail": f"{type(e).__name__}: {e}"})
            print(f"[FAIL] {tool_name}: {type(e).__name__}: {e}")
            traceback.print_exc()

    # Ensure unregister even if earlier steps failed mid-way.
    try:
        invoke(runtime, "repo.unregister", {"name": TEMP_REPO})
    except Exception:
        pass

    counts = {"PASS": 0, "DEGRADED": 0, "FAIL": 0, "SKIP": 0}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    print("\n===== SUMMARY =====")
    print(json.dumps(counts, ensure_ascii=False))
    missing = {s.name for s in specs} - {r["tool"] for r in rows}
    if missing:
        print("missing_from_matrix:", sorted(missing))
    fail = [r for r in rows if r["status"] == "FAIL"]
    if fail:
        print("failures:")
        for r in fail:
            print(f"  - {r['tool']}: {r['detail']}")
    out_path = ROOT / "data" / "tmp-tool-verify-report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"counts": counts, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report: {out_path}")


if __name__ == "__main__":
    main()
