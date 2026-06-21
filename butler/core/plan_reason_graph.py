"""Session-scoped DoT-lite reason graph for plan mode (opt-in)."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from butler.config import get_butler_home
from butler.core.session_transcript import _safe_segment

logger = logging.getLogger(__name__)

_GRAPH_LOCK = threading.RLock()
_GRAPH_KINDS = frozenset({"fact", "hypothesis", "step", "risk", "proposer", "critic", "summary"})
_EDGE_RELS = frozenset({"depends", "supports", "contradicts", "refines"})


def reason_graph_path(session_key: str) -> Path:
    sk = _safe_segment(session_key)
    return get_butler_home() / "sessions" / sk / "reason_graph.json"


def load_graph(session_key: str) -> dict[str, Any]:
    path = reason_graph_path(session_key)
    if not path.is_file():
        return {"nodes": [], "edges": [], "updated_at": ""}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"nodes": [], "edges": [], "updated_at": ""}
    if not isinstance(data, dict):
        return {"nodes": [], "edges": [], "updated_at": ""}
    data.setdefault("nodes", [])
    data.setdefault("edges", [])
    return data


def _save_graph(session_key: str, data: dict[str, Any]) -> None:
    path = reason_graph_path(session_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def append_node(
    session_key: str,
    *,
    text: str,
    role: str = "step",
    title: str = "",
    assumption: str = "",
    evidence: str = "",
) -> dict[str, Any]:
    """Append a node; return the node dict."""
    role_norm = str(role or "step").strip().lower()[:32]
    if role_norm not in _GRAPH_KINDS:
        role_norm = "step"
    node = {
        "id": uuid4().hex[:10],
        "role": role_norm,
        "title": (title or text or "")[:120],
        "text": (text or "")[:500],
        "assumption": (assumption or "")[:300],
        "evidence": (evidence or "")[:300],
    }
    with _GRAPH_LOCK:
        data = load_graph(session_key)
        nodes = data.get("nodes")
        if not isinstance(nodes, list):
            nodes = []
        nodes.append(node)
        data["nodes"] = nodes[-64:]
        _save_graph(session_key, data)
    return node


def append_edge(
    session_key: str,
    *,
    from_id: str,
    to_id: str,
    rel: str = "depends",
) -> dict[str, Any]:
    rel_norm = str(rel or "depends").strip().lower()[:32]
    if rel_norm not in _EDGE_RELS:
        rel_norm = "depends"
    edge = {
        "from": str(from_id or "")[:16],
        "to": str(to_id or "")[:16],
        "rel": rel_norm,
    }
    with _GRAPH_LOCK:
        data = load_graph(session_key)
        edges = data.get("edges")
        if not isinstance(edges, list):
            edges = []
        edges.append(edge)
        data["edges"] = edges[-96:]
        _save_graph(session_key, data)
    return edge


def summarize_graph(session_key: str) -> dict[str, int]:
    data = load_graph(session_key)
    nodes = data.get("nodes") if isinstance(data.get("nodes"), list) else []
    edges = data.get("edges") if isinstance(data.get("edges"), list) else []
    by_role: dict[str, int] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        r = str(n.get("role") or "step")
        by_role[r] = by_role.get(r, 0) + 1
    return {
        "nodes": len(nodes),
        "edges": len(edges),
        **{f"role_{k}": v for k, v in by_role.items()},
    }


def clear_graph(session_key: str) -> None:
    path = reason_graph_path(session_key)
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


__all__ = [
    "append_edge",
    "append_node",
    "clear_graph",
    "load_graph",
    "reason_graph_path",
    "summarize_graph",
]
