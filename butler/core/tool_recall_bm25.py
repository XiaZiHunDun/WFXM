"""BM25 tool recall for large tool registries (PR-X5 / MetaGPT subset)."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from butler.core.meta_flags import tool_recall_bm25_enabled

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(str(text or "").lower()) if len(t) >= 2]


def _tool_name(defn: dict[str, Any]) -> str:
    fn_raw = defn.get("function")
    fn = fn_raw if isinstance(fn_raw, dict) else {}
    return str(fn.get("name") or defn.get("name") or "").strip()


def _tool_document(defn: dict[str, Any]) -> str:
    fn_raw = defn.get("function")
    fn = fn_raw if isinstance(fn_raw, dict) else {}
    return f"{fn.get('name', '')} {fn.get('description', '')}"


class _BM25Index:
    def __init__(self, documents: list[list[str]]) -> None:
        self.docs = documents
        self.ndocs = len(documents)
        self.avgdl = sum(len(d) for d in documents) / self.ndocs if self.ndocs else 0.0
        self.df: Counter[str] = Counter()
        for doc in documents:
            for term in set(doc):
                self.df[term] += 1
        self.k1 = 1.5
        self.b = 0.75

    def score(self, query_tokens: list[str], doc_idx: int) -> float:
        doc = self.docs[doc_idx]
        if not doc or not query_tokens:
            return 0.0
        doc_len = len(doc)
        tf = Counter(doc)
        score = 0.0
        for term in query_tokens:
            if term not in tf:
                continue
            df = self.df.get(term, 0)
            idf = math.log(1 + (self.ndocs - df + 0.5) / (df + 0.5))
            freq = tf[term]
            denom = freq + self.k1 * (1 - self.b + self.b * doc_len / (self.avgdl or 1.0))
            score += idf * (freq * (self.k1 + 1)) / (denom or 1.0)
        return score


def rank_tools_bm25(
    tools: list[dict[str, Any]],
    query: str,
    *,
    top_k: int = 12,
) -> list[dict[str, Any]]:
    if not tools:
        return []
    docs = [_tokenize(_tool_document(t)) for t in tools]
    q_tokens = _tokenize(query)
    if not q_tokens:
        return list(tools[:top_k])
    index = _BM25Index(docs)
    scored = [
        (index.score(q_tokens, i), i, tools[i])
        for i in range(len(tools))
    ]
    scored.sort(key=lambda x: (-x[0], x[1]))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, _, defn in scored:
        name = _tool_name(defn)
        if name in seen:
            continue
        out.append(defn)
        seen.add(name)
        if len(out) >= top_k:
            break
    return out


def select_tools_with_bm25(
    tools: list[dict[str, Any]],
    *,
    user_hint: str = "",
    top_k: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    from butler.core.tool_selector import tool_selector_threshold

    cap = top_k if top_k is not None else tool_selector_threshold()
    diag = {"tool_recall_bm25_input": len(tools), "tool_recall_bm25_output": len(tools)}
    if not tool_recall_bm25_enabled() or len(tools) <= cap:
        return list(tools), diag
    chosen = rank_tools_bm25(tools, user_hint, top_k=cap)
    diag["tool_recall_bm25_output"] = len(chosen)
    diag["tool_recall_bm25_dropped"] = max(0, len(tools) - len(chosen))
    return chosen, diag


__all__ = ["rank_tools_bm25", "select_tools_with_bm25", "tool_recall_bm25_enabled"]
