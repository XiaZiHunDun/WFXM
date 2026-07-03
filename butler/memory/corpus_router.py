"""Route recall queries across owner / project / prompt corpus (Sprint C)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from butler.env_parse import env_truthy

_OWNER_KW = re.compile(
    r"(用户偏好|全局|owner|画像|profile|跨项目)",
    re.IGNORECASE,
)
_PROJECT_KW = re.compile(
    r"(本项目|项目记忆|MEMORY|架构|决策|facts?)",
    re.IGNORECASE,
)
_PROMPT_KW = re.compile(
    r"(提示词|语料|corpus|prompt|butler_system|规划模式)",
    re.IGNORECASE,
)
_DESIGN_KW = re.compile(
    r"(DESIGN\.md|设计稿|设计系统|ui-build|组件样式|design.token|responsive)",
    re.IGNORECASE,
)


def corpus_routing_enabled() -> bool:
    return env_truthy("BUTLER_CORPUS_ROUTING", default=True)


@dataclass(frozen=True)
class CorpusRoute:
    scope: str
    reason: str
    extra_scopes: tuple[str, ...] = ()


def route_corpus_query(query: str, *, default_scope: str = "project") -> CorpusRoute:
    if not corpus_routing_enabled():
        return CorpusRoute(scope=default_scope, reason="disabled")
    q = str(query or "").strip()
    if not q:
        return CorpusRoute(scope=default_scope, reason="empty")
    if _PROMPT_KW.search(q):
        return CorpusRoute(
            scope="project",
            reason="prompt_corpus",
            extra_scopes=("experience",),
        )
    if _OWNER_KW.search(q):
        return CorpusRoute(scope="profile", reason="owner_keywords")
    if _DESIGN_KW.search(q):
        return CorpusRoute(scope="project", reason="design_keywords")
    if _PROJECT_KW.search(q):
        return CorpusRoute(scope="project", reason="project_keywords")
    return CorpusRoute(scope=default_scope, reason="default")


def multi_scope_recall(query: str, *, limit: int = 6) -> str:
    """Invoke butler_recall for primary + optional secondary scopes (optional sub-queries)."""
    import json

    from butler.tools.memory_tools import tool_butler_recall

    from butler.memory.corpus_router_ops import decompose_recall_queries_safe

    sub_queries = decompose_recall_queries_safe(query)

    route = route_corpus_query(query)
    parts: list[dict[str, Any]] = []

    def _one(scope: str, sub_q: str) -> None:
        raw = tool_butler_recall(scope=scope, query=sub_q, limit=limit)
        try:
            parts.append({"scope": scope, "sub_query": sub_q, "payload": json.loads(raw)})
        except json.JSONDecodeError:
            parts.append({"scope": scope, "sub_query": sub_q, "payload": {"text": raw}})

    for sub_q in sub_queries:
        _one(route.scope, sub_q)
        for extra in route.extra_scopes:
            if extra != route.scope:
                _one(extra, sub_q)
    return json.dumps(
        {
            "route": route.reason,
            "sub_queries": sub_queries if len(sub_queries) > 1 else [],
            "scopes": [p["scope"] for p in parts],
            "results": parts,
        },
        ensure_ascii=False,
    )


__all__ = ["CorpusRoute", "corpus_routing_enabled", "multi_scope_recall", "route_corpus_query"]
