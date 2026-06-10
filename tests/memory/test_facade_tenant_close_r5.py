"""R5-3: facade closes ButlerMemory on tenant switch."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from butler.memory.facade import ButlerMemoryService


@pytest.mark.unit
def test_reload_butler_global_closes_previous(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    svc = ButlerMemoryService()
    prev = MagicMock()
    prev.tenant_id = "old"
    svc._butler_global = prev

    with patch("butler.memory.facade.ButlerMemory") as bm_cls:
        bm_cls.return_value = MagicMock(tenant_id="new")
        with patch("butler.tenant.resolve_tenant_for_project", return_value="new"):
            with patch("butler.config.get_butler_settings"):
                with patch("butler.project.manager.get_project_manager"):
                    svc._reload_butler_global()

    prev.close.assert_called_once()
