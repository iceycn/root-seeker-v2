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
