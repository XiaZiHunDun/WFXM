"""Prefetch hybrid + coding merge (L5 direction H)."""

from __future__ import annotations

from unittest.mock import MagicMock

from butler.memory.recall_router import memory_state_for_scope
from butler.session.memory_prefetch_ops import hybrid_experience_hits


def test_hybrid_experience_hits_merges_coding_when_unified_off(monkeypatch):
    monkeypatch.setenv("BUTLER_MEMORY_UNIFIED_RECALL", "0")

    class _Exp:
        def search(self, query: str, **kwargs):
            return [{"content": f"exp:{query}", "score": 1.0}]

    class _BM:
        experience = _Exp()
        semantic = None

    orch = MagicMock()
    orch.butler_memory = _BM()
    orch.project_memory = None

    monkeypatch.setattr(
        "butler.session.memory_prefetch_ops.hybrid_experience_search",
        lambda *a, **kw: [{"content": f"exp:{kw.get('query') or a[2]}", "score": 1.0}],
    )
    monkeypatch.setattr(
        "butler.memory.coding_recall.search_coding_experiences",
        lambda q, **kw: {
            "ok": True,
            "results": [{"content": f"code:{q}", "pattern": "demo"}],
        },
    )

    rows = hybrid_experience_hits(orch, "auth bug", limit=5)
    contents = {str(r.get("content") or "") for r in rows}
    assert "exp:auth bug" in contents
    assert "code:auth bug" in contents
    coding = [r for r in rows if r.get("recall_scope") == "coding"]
    assert coding and coding[0].get("memory_state") == memory_state_for_scope("coding")
