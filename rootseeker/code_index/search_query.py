from __future__ import annotations

import re

__all__ = [
    "ZOEKT_NOISE_FILTERS",
    "build_zoekt_search_query",
    "extract_code_identifiers",
    "lexical_overlap_score",
    "tokenize_code_text",
]

_STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "for",
    "from",
    "high",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "prod",
    "production",
    "ratio",
    "the",
    "to",
    "with",
    "error",
    "errors",
    "failed",
    "failure",
    "exception",
    "null",
    "undefined",
    "service",
    "api",
    "request",
    "response",
}

# Keep Zoekt away from minified / i18n / fuzzer corpora that drown relevance.
ZOEKT_NOISE_FILTERS = (
    r"-file:\.min\.js$",
    r"-file:\.min\.css$",
    r"-file:\.map$",
    r"-file:chunk-[a-f0-9]+\.js$",
    r"-file:messages_.*\.properties$",
    r"-file:fuzzdb/",
    r"-file:node_modules/",
    r"-file:vendor/",
    r"-file:\.pb\.go$",
)

_IDENTIFIER_RE = re.compile(
    r"\b(?:"
    r"[A-Z][A-Za-z0-9]+(?:[A-Z][A-Za-z0-9]+)+"  # PascalCase
    r"|[a-z][a-z0-9]*(?:[A-Z][A-Za-z0-9]+)+"  # camelCase
    r"|[A-Za-z_][A-Za-z0-9_]*_[A-Za-z0-9_]+"  # snake_case
    r"|[A-Za-z_][A-Za-z0-9_]{2,}(?:\.[A-Za-z_][A-Za-z0-9_]{2,})+"  # dotted refs
    r")\b"
)
_PATH_RE = re.compile(
    r"([A-Za-z0-9_./-]+\.(?:java|kt|py|go|ts|tsx|js|jsx|cs|rb|php|scala|rs|cpp|c|h))(?::\d+)?"
)
_TOKEN_SPLIT_RE = re.compile(r"[^A-Za-z0-9_]+")
_CAMEL_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")


def extract_code_identifiers(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for match in _IDENTIFIER_RE.finditer(text or ""):
        token = match.group(0)
        if token.lower() in _STOPWORDS:
            continue
        if token not in seen:
            seen.add(token)
            found.append(token)
    return found


def tokenize_code_text(text: str) -> set[str]:
    """Split code-ish text into lowercase tokens, including camelCase parts."""
    tokens: set[str] = set()
    for raw in _TOKEN_SPLIT_RE.split(text or ""):
        if not raw:
            continue
        lower = raw.lower()
        if len(lower) >= 2:
            tokens.add(lower)
        parts = _CAMEL_RE.findall(raw)
        for part in parts:
            p = part.lower()
            if len(p) >= 2:
                tokens.add(p)
    return tokens


def build_zoekt_search_query(symptom: str, *, include_noise_filters: bool = True) -> str:
    """Build a Zoekt query that prefers identifiers/phrases over stopword-heavy prose."""
    text = (symptom or "").strip()
    if not text:
        return ""

    path_match = _PATH_RE.search(text)
    if path_match:
        query = f"file:{path_match.group(1)}"
        return _with_filters(query, include_noise_filters)

    first_line = text.splitlines()[0].strip()
    identifiers = extract_code_identifiers(first_line)
    if identifiers:
        # Prefer the most specific identifiers first (longer usually = better).
        ranked = sorted(identifiers, key=lambda item: (-len(item), item))[:4]
        query = " ".join(ranked)
        return _with_filters(query, include_noise_filters)

    words = [
        w
        for w in re.findall(r"[A-Za-z0-9_]+", first_line)
        if w.lower() not in _STOPWORDS and len(w) >= 3
    ]
    if len(words) >= 2:
        phrase = " ".join(words[:8])
        return _with_filters(f'"{phrase}"', include_noise_filters)
    if words:
        return _with_filters(words[0], include_noise_filters)

    # Last resort: quoted original first line to force phrase match.
    compact = " ".join(first_line.split())
    if not compact:
        return ""
    return _with_filters(f'"{compact}"', include_noise_filters)


def lexical_overlap_score(query: str, *documents: str) -> float:
    q_raw = (query or "").strip()
    if not q_raw:
        return 0.0
    haystack = "\n".join(documents).lower()
    identifiers = extract_code_identifiers(q_raw)
    if identifiers:
        symbols: list[str] = []
        seen: set[str] = set()
        for item in identifiers:
            parts = item.split(".") if "." in item else [item]
            for part in parts:
                if part and part not in seen:
                    seen.add(part)
                    symbols.append(part)
        exact_hits = sum(1 for item in symbols if item.lower() in haystack)
        if exact_hits:
            return exact_hits / float(len(symbols))
        return 0.0

    q_tokens = tokenize_code_text(q_raw)
    if not q_tokens:
        return 0.0
    doc_tokens: set[str] = set()
    for doc in documents:
        doc_tokens |= tokenize_code_text(doc)
    if not doc_tokens:
        return 0.0
    return len(q_tokens & doc_tokens) / float(len(q_tokens))


def _with_filters(query: str, include_noise_filters: bool) -> str:
    if not include_noise_filters:
        return query
    filters = " ".join(ZOEKT_NOISE_FILTERS)
    return f"{query} {filters}".strip()
