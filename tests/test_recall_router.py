"""RecallRouter dispatch tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from butler.memory.recall_router import dispatch_recall, memory_state_for_scope


def test_memory_state_for_scope():
    assert memory_state_for_scope("transcript") == "session"
    assert memory_state_for_scope("observation") == "derived"
    assert memory_state_for_scope("experience") == "ssot"


def test_dispatch_recall_experience_tags_memory_state(monkeypatch):
    facade = MagicMock()
    facade._project_memory = None
    facade._project_root = None

    class _Exp:
        def get_recent(self, limit: int = 8):
            return [{"content": "recent fact"}]

    facade._butler_global = MagicMock()
    facade._butler_global.experience = _Exp()
    facade._butler_global.semantic = None

    raw = dispatch_recall(facade, {"scope": "experience", "query": ""})
    payload = json.loads(raw)
    assert payload["ok"] is True
    assert payload["memory_state"] == "ssot"
    assert payload["results"][0]["memory_state"] == "ssot"
