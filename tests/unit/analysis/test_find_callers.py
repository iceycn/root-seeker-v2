from __future__ import annotations

from rootseeker.analysis.call_chain import extract_call_chain_summary
from rootseeker.analysis.find_callers import (
    align_runtime_static_chain,
    analyze_call_chain,
    build_caller_search_query,
    parse_call_chain_frame,
)

SAMPLE_STACK = """
org.springframework.dao.DuplicateKeyException:
at net.coolcollege.training.service.impl.PopRecordService.insertPopRecordLogic(PopRecordService.java:60)
at net.coolcollege.training.service.impl.StudyProjectProcessService.batchDealProjectQualifiedEvent(StudyProjectProcessService.java:1753)
at net.coolcollege.training.controller.StudyProjectController.saveProgress(StudyProjectController.java:1132)
"""


def test_parse_call_chain_frame() -> None:
    frame = "PopRecordService.insertPopRecordLogic (PopRecordService.java:60)"
    parsed = parse_call_chain_frame(frame)
    assert parsed == {
        "class_name": "PopRecordService",
        "method_name": "insertPopRecordLogic",
        "file_path": "PopRecordService.java",
        "line": 60,
        "summary": frame,
    }


def test_parse_call_chain_frame_accepts_symbol_without_file() -> None:
    parsed = parse_call_chain_frame(
        "BizPracticeService.queryBizPracticeListByUserDepaGroupPost"
    )
    assert parsed is not None
    assert parsed["class_name"] == "BizPracticeService"
    assert parsed["method_name"] == "queryBizPracticeListByUserDepaGroupPost"


def test_parse_call_chain_frame_accepts_qualified_java_class() -> None:
    parsed = parse_call_chain_frame(
        "net.coolcollege.usercenter.facade.handler.AesTypeHandler.decryptField"
    )
    assert parsed is not None
    assert parsed["class_name"].endswith("AesTypeHandler")
    assert parsed["method_name"] == "decryptField"


def test_build_caller_search_query() -> None:
    assert build_caller_search_query(method_name="saveProgress") == "saveProgress("
    assert (
        build_caller_search_query(method_name="saveProgress", repo="training-manage-api")
        == "repo:training-manage-api saveProgress("
    )


def test_align_runtime_static_chain() -> None:
    runtime = extract_call_chain_summary(SAMPLE_STACK)
    static = [
        {
            "caller_class": "StudyProjectProcessService",
            "caller_method": "batchDealProjectQualifiedEvent",
            "runtime_match": True,
        }
    ]
    aligned = align_runtime_static_chain(runtime, static)
    assert aligned["fault_method"] == "PopRecordService.insertPopRecordLogic"
    assert aligned["entry_method"] == "StudyProjectController.saveProgress"
    assert "StudyProjectController.saveProgress" in aligned["aligned_path"]


def test_analyze_call_chain_with_mock_search() -> None:
    runtime = extract_call_chain_summary(SAMPLE_STACK)

    def search_code(query: str, limit: int, repo_filter: str | None) -> dict:
        return {
            "query": query,
            "hits": [
                {
                    "repo": "training-manage-api",
                    "path": "src/StudyProjectProcessService.java",
                    "line_start": 1753,
                    "snippet": "insertPopRecordLogic(userId, planId);",
                    "score": 10.0,
                }
            ],
        }

    def read_code(path: str, repo: str | None = None, **kwargs):
        return {
            "content": (
                "public void batchDealProjectQualifiedEvent(Long userId) {\n"
                "    insertPopRecordLogic(userId, planId);\n"
                "}\n"
            )
        }

    result = analyze_call_chain(
        runtime,
        search_code=search_code,
        read_code=read_code,
        repo="training-manage-api",
    )
    assert result["target"]["method_name"] == "insertPopRecordLogic"
    assert "insertPopRecordLogic(" in result["queries"][0]
    assert result["static_callers"]
    assert result["static_callers"][0]["runtime_match"] is True
    assert result["entrypoints"][0]["class_name"] == "StudyProjectController"


def test_analyze_call_chain_uses_planner_symbol_not_wrapper_frame() -> None:
    seen: list[str] = []

    def graph_callers(symbol: str, *, repo=None, file=None, max_depth=5):  # noqa: ANN001
        seen.append(symbol)
        return {
            "ok": True,
            "static_callers": [
                {
                    "caller_class": "AesTypeHandler",
                    "caller_method": "getNullableResult",
                    "path": "AesTypeHandler.java",
                    "line": 28,
                }
            ],
        }

    result = analyze_call_chain(
        [
            "BizPracticeService.queryBizPracticeListByUserDepaGroupPost (BizPracticeService.java:2361)",
            "AesTypeHandler.decryptField (AesTypeHandler.java:53)",
        ],
        search_code=lambda *args, **kwargs: {"hits": []},
        graph_callers=graph_callers,
        target_symbol="net.coolcollege.usercenter.facade.handler.AesTypeHandler.decryptField",
    )
    assert result["target"]["method_name"] == "decryptField"
    assert result["target"]["class_name"].endswith("AesTypeHandler")
    assert seen
    assert "decryptField" in seen[0]
    assert "queryBizPracticeListByUserDepaGroupPost" not in seen[0]
