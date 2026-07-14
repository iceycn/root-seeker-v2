from __future__ import annotations

import json

from rootseeker.code_index.gitnexus_adapter import GitNexusAdapter, _symbol_candidates
from rootseeker.code_index.gitnexus_cli import GitNexusCli, GitNexusCliConfig, GitNexusCommandResult
from rootseeker.analysis.call_chain import extract_call_chain_summary
from rootseeker.analysis.find_callers import analyze_call_chain


class _FakeCli(GitNexusCli):
    def __init__(self) -> None:
        super().__init__(GitNexusCliConfig(enabled=True, command="gitnexus"))
        self.calls: list[list[str]] = []

    def run(self, args, *, cwd=None, timeout_seconds=None, prefer_json=True):  # noqa: ANN001
        self.calls.append(list(args))
        if args and args[0] == "impact":
            return GitNexusCommandResult(
                ok=True,
                exit_code=0,
                stdout="",
                stderr="",
                data={
                    "upstream": [
                        {
                            "name": "StudyProjectProcessService.batchDealProjectQualifiedEvent",
                            "file": "StudyProjectProcessService.java",
                            "line": 1753,
                            "confidence": 0.9,
                        }
                    ]
                },
                command=["gitnexus", *args],
            )
        return GitNexusCommandResult(ok=True, exit_code=0, stdout="{}", stderr="", data={}, command=["gitnexus", *args])


def test_match_gitnexus_repo_suffix_and_contains() -> None:
    from rootseeker.code_index.gitnexus_adapter import _match_gitnexus_repo

    available = [
        "6183d17ff1ae9b61971d96b5__training-manage-api",
        "training-manage-api",
        "other-service",
    ]
    assert _match_gitnexus_repo("training-manage-api", available) == "training-manage-api"
    assert (
        _match_gitnexus_repo("training-manage-api", ["6183d17ff1ae9b61971d96b5__training-manage-api"])
        == "6183d17ff1ae9b61971d96b5__training-manage-api"
    )


def test_graph_hit_usable_rejects_bare_target() -> None:
    from rootseeker.code_index.gitnexus_adapter import _graph_hit_usable

    assert not _graph_hit_usable({"target": {"name": "x"}, "impactedCount": 0})
    assert _graph_hit_usable({"impactedCount": 2, "byDepth": {"1": [{"name": "a"}]}})

    from rootseeker.code_index.gitnexus_adapter import _pick_ambiguous_candidate

    pick = _pick_ambiguous_candidate(
        [
            {
                "uid": "iface",
                "name": "insertPopRecordLogic",
                "filePath": "service/IPopRecordService.java",
                "score": 0.54,
            },
            {
                "uid": "impl",
                "name": "insertPopRecordLogic",
                "filePath": "service/impl/PopRecordService.java",
                "score": 0.54,
            },
        ],
        symbol="PopRecordService.insertPopRecordLogic",
    )
    assert pick is not None
    assert pick["uid"] == "impl"


def test_extract_callers_from_byDepth() -> None:
    from rootseeker.code_index.gitnexus_adapter import _extract_callers_from_impact

    callers = _extract_callers_from_impact(
        {
            "byDepth": {
                "1": [
                    {
                        "depth": 1,
                        "name": "batchDealProjectQualifiedEvent",
                        "filePath": "StudyProjectProcessService.java",
                        "confidence": 0.85,
                    }
                ]
            }
        },
        max_depth=5,
    )
    assert callers
    assert callers[0]["caller_method"] == "batchDealProjectQualifiedEvent"
    assert callers[0]["path"] == "StudyProjectProcessService.java"


def test_impact_retries_method_name_when_qualified_missing() -> None:
    class _Cli(GitNexusCli):
        def __init__(self) -> None:
            super().__init__(GitNexusCliConfig(enabled=True, command="gitnexus"))
            self.seen: list[str] = []

        def run(self, args, *, cwd=None, timeout_seconds=None, prefer_json=True):  # noqa: ANN001
            symbol = args[1] if len(args) > 1 else ""
            self.seen.append(symbol)
            if any(a == "--uid" for a in args):
                data = {
                    "impactedCount": 2,
                    "risk": "HIGH",
                    "byDepth": {"1": [{"name": "batchDealProjectQualifiedEvent", "filePath": "X.java"}]},
                }
            elif symbol == "PopRecordService.insertPopRecordLogic":
                data = {
                    "error": "Target 'PopRecordService.insertPopRecordLogic' not found",
                    "impactedCount": 0,
                    "risk": "UNKNOWN",
                }
            elif symbol == "insertPopRecordLogic":
                data = {
                    "status": "ambiguous",
                    "candidates": [
                        {
                            "uid": "impl",
                            "name": "insertPopRecordLogic",
                            "filePath": "service/impl/PopRecordService.java",
                            "score": 0.9,
                        }
                    ],
                }
            else:
                data = {}
            return GitNexusCommandResult(
                ok=True,
                exit_code=0,
                stdout=json.dumps(data),
                stderr="",
                data=data,
                command=["gitnexus", *args],
            )

    adapter = GitNexusAdapter(cli=_Cli())
    result = adapter.impact("PopRecordService.insertPopRecordLogic", repo="training-manage-api")
    assert result.get("ok") is True
    assert (result.get("result") or {}).get("impactedCount") == 2
    assert result.get("disambiguated_uid") == "impl"


def test_gitnexus_adapter_callers_for_symbol() -> None:
    adapter = GitNexusAdapter(cli=_FakeCli())
    result = adapter.callers_for_symbol("PopRecordService.insertPopRecordLogic")
    assert result["ok"] is True
    assert result["source"] == "gitnexus"
    assert result["static_callers"]
    assert result["static_callers"][0]["caller_method"] == "batchDealProjectQualifiedEvent"


def test_analyze_call_chain_prefers_graph_then_skips_zoekt() -> None:
    runtime = extract_call_chain_summary(
        "at PopRecordService.insertPopRecordLogic(PopRecordService.java:60)\n"
        "at StudyProjectProcessService.batchDealProjectQualifiedEvent(StudyProjectProcessService.java:1)\n"
    )
    zoekt_calls: list[str] = []

    def search_code(query: str, limit: int, repo_filter: str | None) -> dict:
        zoekt_calls.append(query)
        return {"hits": []}

    def graph_callers(symbol: str, *, repo=None, file=None, max_depth=5):  # noqa: ANN001
        return {
            "ok": True,
            "symbol": symbol,
            "static_callers": [
                {
                    "caller_class": "StudyProjectProcessService",
                    "caller_method": "batchDealProjectQualifiedEvent",
                    "path": "StudyProjectProcessService.java",
                    "line": 1,
                    "score": 1.0,
                    "depth": 1,
                }
            ],
        }

    result = analyze_call_chain(
        runtime,
        search_code=search_code,
        graph_callers=graph_callers,
        prefer_graph=True,
    )
    assert result["source"] == "gitnexus"
    assert zoekt_calls == []
    assert result["static_callers"][0]["caller_method"] == "batchDealProjectQualifiedEvent"


def test_analyze_call_chain_falls_back_to_zoekt_when_graph_empty() -> None:
    runtime = [
        "PopRecordService.insertPopRecordLogic (PopRecordService.java:60)",
    ]

    def search_code(query: str, limit: int, repo_filter: str | None) -> dict:
        return {
            "hits": [
                {
                    "repo": "demo",
                    "path": "Caller.java",
                    "line_start": 10,
                    "snippet": "insertPopRecordLogic(x);",
                    "score": 5.0,
                }
            ]
        }

    def read_code(path: str, repo: str | None = None, **kwargs):  # noqa: ANN003
        return {"content": "public void run() { insertPopRecordLogic(x); }\n"}

    def graph_callers(symbol: str, **kwargs):  # noqa: ANN003
        return {"ok": False, "static_callers": [], "error": "no graph"}

    result = analyze_call_chain(
        runtime,
        search_code=search_code,
        read_code=read_code,
        graph_callers=graph_callers,
        prefer_graph=True,
    )
    assert result["source"] == "zoekt"
    assert result["graph"]["attempted"] is True
