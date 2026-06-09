from __future__ import annotations

from dataclasses import dataclass

from rootseeker.code_index.file_scanner import CodeFile

__all__ = ["CodeChunk", "ChunkConfig", "chunk_code_file", "chunk_code_files"]


@dataclass(frozen=True)
class ChunkConfig:
    max_lines: int = 120
    overlap_lines: int = 20
    min_chars: int = 1


@dataclass(frozen=True)
class CodeChunk:
    repo: str
    path: str
    language: str
    start_line: int
    end_line: int
    content: str
    sha256: str

    @property
    def stable_key(self) -> str:
        return f"{self.repo}:{self.path}:{self.start_line}:{self.end_line}:{self.sha256}"


def chunk_code_file(repo_name: str, code_file: CodeFile, config: ChunkConfig | None = None) -> list[CodeChunk]:
    cfg = config or ChunkConfig()
    lines = code_file.content.splitlines()
    if not lines:
        return []

    step = max(1, cfg.max_lines - cfg.overlap_lines)
    chunks: list[CodeChunk] = []
    start = 0
    while start < len(lines):
        end = min(len(lines), start + cfg.max_lines)
        content = "\n".join(lines[start:end]).strip()
        if len(content) >= cfg.min_chars:
            chunks.append(
                CodeChunk(
                    repo=repo_name,
                    path=code_file.path,
                    language=code_file.language,
                    start_line=start + 1,
                    end_line=end,
                    content=content,
                    sha256=code_file.sha256,
                )
            )
        if end == len(lines):
            break
        start += step
    return chunks


def chunk_code_files(repo_name: str, files: list[CodeFile], config: ChunkConfig | None = None) -> list[CodeChunk]:
    chunks: list[CodeChunk] = []
    for code_file in files:
        chunks.extend(chunk_code_file(repo_name, code_file, config=config))
    return chunks
