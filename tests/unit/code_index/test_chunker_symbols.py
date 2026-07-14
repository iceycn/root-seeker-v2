from __future__ import annotations

from pathlib import Path

from rootseeker.code_index.chunker import ChunkConfig, chunk_code_file, extract_symbol_spans
from rootseeker.code_index.file_scanner import CodeFile


def _file(path: str, content: str, language: str) -> CodeFile:
    return CodeFile(
        path=path,
        absolute_path=Path(path),
        content=content,
        language=language,
        sha256="abc",
        size_bytes=len(content.encode("utf-8")),
    )


def test_python_chunks_by_function_and_class() -> None:
    content = (
        "import os\n"
        "\n"
        "class Service:\n"
        "    def run(self):\n"
        "        return 1\n"
        "\n"
        "def helper():\n"
        "    return 2\n"
    )
    spans = extract_symbol_spans(content.splitlines(), "python")
    names = {span.name for span in spans}
    assert names == {"Service", "run", "helper"}

    chunks = chunk_code_file("repo", _file("a.py", content, "python"))
    by_symbol = {c.symbol: c for c in chunks if c.symbol}
    assert "run" in by_symbol
    assert "helper" in by_symbol
    assert "Service" in by_symbol
    assert "def run" in by_symbol["run"].content
    assert any(c.symbol is None and "import os" in c.content for c in chunks)


def test_java_chunks_by_method_inside_class() -> None:
    content = "\n".join(
        [
            "package demo;",
            "public class PopRecordService {",
            "    public void insertPopRecordLogic(long planId, long userId) {",
            "        int count = 0;",
            "        if (count == 0) {",
            "            save();",
            "        }",
            "    }",
            "",
            "    private void save() {",
            "        return;",
            "    }",
            "}",
        ]
    )
    spans = extract_symbol_spans(content.splitlines(), "java")
    names = {span.name for span in spans}
    assert "PopRecordService" in names
    assert "insertPopRecordLogic" in names
    assert "save" in names

    chunks = chunk_code_file("repo", _file("PopRecordService.java", content, "java"))
    insert = next(c for c in chunks if c.symbol == "insertPopRecordLogic")
    assert insert.symbol_kind == "method"
    assert "insertPopRecordLogic" in insert.content
    assert insert.start_line < insert.end_line


def test_large_symbol_is_windowed_but_keeps_symbol() -> None:
    body = "\n".join(f"    x = {i}" for i in range(250))
    content = f"def huge():\n{body}\n"
    chunks = chunk_code_file(
        "repo",
        _file("big.py", content, "python"),
        config=ChunkConfig(max_lines=50, overlap_lines=10),
    )
    assert len(chunks) > 1
    assert all(c.symbol == "huge" for c in chunks)
    assert chunks[0].start_line == 1


def test_no_symbols_indexes_whole_file_unit() -> None:
    content = "FOO = 1\nBAR = 2\n"
    chunks = chunk_code_file("repo", _file("constants.txt", content, "text"))
    assert len(chunks) == 1
    assert chunks[0].symbol is None
    assert "FOO = 1" in chunks[0].content
