"""R5-2/R5-3: ButlerMemory.close releases sqlite handles."""

from __future__ import annotations

import pytest

from butler.memory.butler_memory import ButlerMemory


@pytest.mark.unit
def test_butler_memory_close_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    mem = ButlerMemory(tmp_path, tenant_id="t-close")
    mem.close()
    mem.close()
