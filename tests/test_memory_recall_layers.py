"""PR-F3: private tags + progressive recall layers."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from butler.memory.butler_memory import ButlerMemory
from butler.memory.facade import ButlerMemoryService
from butler.memory.private_tags import strip_private_tags
from butler.memory.recall_layers import recall_fetch, recall_index


def test_strip_private_tags():
    public, all_priv = strip_private_tags("hello <private>secret</private> world")
    assert "secret" not in public
    assert "hello" in public
    assert not all_priv

    _, all_priv2 = strip_private_tags("<private>only this</private>")
    assert all_priv2


def test_recall_index_and_fetch():
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        bm = ButlerMemory(home, tenant_id="default")
        row_id = bm.experience.add(
            project="demo",
            category="note",
            content="Butler recall layers integration test unique-token-xyz",
        )
        from butler.memory.semantic_index import index_experience_row

        index_experience_row(
            getattr(bm, "semantic", None),
            row_id,
            project="demo",
            category="note",
            content="Butler recall layers integration test unique-token-xyz",
        )

        svc = ButlerMemoryService()
        svc._butler_global = bm
        svc._session_id = "test"

        idx_raw = recall_index(
            svc,
            {"query": "unique-token-xyz", "limit": 5},
        )
        idx = json.loads(idx_raw)
        assert idx["ok"] and idx["mode"] == "index"
        assert idx["count"] >= 1
        cid = idx["items"][0]["chunk_id"]

        fetch_raw = recall_fetch(svc, {"ids": [cid]})
        fetched = json.loads(fetch_raw)
        assert fetched["ok"] and fetched["mode"] == "fetch"
        assert "unique-token-xyz" in str(fetched["items"][0].get("content", ""))
