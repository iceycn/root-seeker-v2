from __future__ import annotations

from rootseeker.code_index.search_query import (
    build_zoekt_search_query,
    extract_code_identifiers,
    lexical_overlap_score,
)


def test_build_zoekt_query_prefers_file_path() -> None:
    q = build_zoekt_search_query("boom in FooService.java:12 during checkout")
    assert q.startswith("file:FooService.java")
    assert "-file:\\.min\\.js$" in q


def test_build_zoekt_query_prefers_identifiers_over_prose() -> None:
    q = build_zoekt_search_query("error ratio high in prod insertPopRecordLogic failed")
    assert "insertPopRecordLogic" in q
    assert "error ratio high in prod" not in q


def test_build_zoekt_query_quotes_natural_language() -> None:
    q = build_zoekt_search_query("error ratio high in prod")
    assert '"error ratio high in prod"' in q or q.startswith('"')


def test_extract_identifiers() -> None:
    ids = extract_code_identifiers("NullPointerException in PopRecordService.insertPopRecordLogic")
    assert "NullPointerException" in ids
    assert "PopRecordService" in ids or "PopRecordService.insertPopRecordLogic" in ids


def test_build_zoekt_query_uses_snake_case_identifier() -> None:
    q = build_zoekt_search_query("create_dev_runtime bootstrap failed")
    assert "create_dev_runtime" in q
    assert '"create_dev_runtime bootstrap"' not in q


def test_lexical_overlap_requires_exact_identifier() -> None:
    score_hit = lexical_overlap_score(
        "insertPopRecordLogic",
        "PopRecordService.java",
        "void insertPopRecordLogic(",
    )
    score_miss = lexical_overlap_score(
        "insertPopRecordLogic",
        "user_account_mapping.sql",
        "insert into user_account_mapping",
    )
    assert score_hit == 1.0
    assert score_miss == 0.0
