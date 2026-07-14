from __future__ import annotations

from rootseeker.flow_runtime.runtime import resolve_resume_step_index


def test_resolve_resume_step_index_maps_old_checkpoint_before_find_callers() -> None:
    # Old flow ended at notify; current flow inserted graph + find-callers before notify.
    # Completed steps through code-read should resume at the new graph-impact step,
    # not blindly reuse the old numeric index that pointed at notify.
    old_steps = [
        {"step_id": "normalize-incident", "status": "completed"},
        {"step_id": "resolve-service", "status": "completed"},
        {"step_id": "resolve-log-sources", "status": "completed"},
        {"step_id": "query-logs-trace", "status": "completed"},
        {"step_id": "query-logs-template", "status": "completed"},
        {"step_id": "trace-chain", "status": "completed"},
        {"step_id": "index-status", "status": "completed"},
        {"step_id": "repo-list", "status": "completed"},
        {"step_id": "code-search", "status": "completed"},
        {"step_id": "code-read", "status": "completed"},
        {"step_id": "notify", "status": "pending"},
    ]
    current_flow = [
        "normalize-incident",
        "resolve-service",
        "resolve-log-sources",
        "query-logs-trace",
        "query-logs-template",
        "trace-chain",
        "index-status",
        "repo-list",
        "code-search",
        "code-read",
        "graph-impact",
        "graph-context",
        "find-callers",
        "notify",
    ]

    mapped = resolve_resume_step_index(
        current_steps=old_steps,
        current_next_step_index=10,  # old notify index
        flow_step_ids=current_flow,
    )

    assert current_flow[mapped] == "graph-impact"
    assert current_flow[10] == "graph-impact"
    assert current_flow[13] == "notify"


def test_resolve_resume_step_index_skips_to_notify_when_find_callers_already_done() -> None:
    steps = [
        {"step_id": "code-read", "status": "completed"},
        {"step_id": "graph-impact", "status": "completed"},
        {"step_id": "graph-context", "status": "completed"},
        {"step_id": "find-callers", "status": "completed"},
        {"step_id": "notify", "status": "pending"},
    ]
    mapped = resolve_resume_step_index(
        current_steps=steps,
        current_next_step_index=4,
        flow_step_ids=["code-read", "graph-impact", "graph-context", "find-callers", "notify"],
    )
    assert mapped == 4
    assert ["code-read", "graph-impact", "graph-context", "find-callers", "notify"][mapped] == "notify"


def test_resolve_resume_step_index_inserts_find_callers_without_completed_statuses() -> None:
    # Legacy checkpoint only stored next_step_index toward notify; no completed markers.
    old_steps = [{"step_id": "notify", "status": "pending"}]
    current_flow = ["code-read", "graph-impact", "graph-context", "find-callers", "notify"]
    mapped = resolve_resume_step_index(
        current_steps=old_steps,
        current_next_step_index=0,
        flow_step_ids=current_flow,
    )
    assert current_flow[mapped] != "notify"
    assert mapped < current_flow.index("notify")
