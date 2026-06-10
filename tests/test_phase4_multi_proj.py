"""Tests for Phase 4: D7 PIM encryption + D2-6 decay monitoring + C1 external repo."""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestD7PIMEncryption:
    """D7: TenantStore Fernet encryption (opt-in)."""

    def test_encrypt_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("BUTLER_PIM_ENCRYPT", raising=False)
        from butler.tools.tenant_store import _pim_encrypt_enabled
        assert not _pim_encrypt_enabled()

    def test_encrypt_enabled_by_env(self, monkeypatch):
        monkeypatch.setenv("BUTLER_PIM_ENCRYPT", "1")
        from butler.tools.tenant_store import _pim_encrypt_enabled
        assert _pim_encrypt_enabled()

    def test_encrypt_text_passthrough_when_disabled(self, monkeypatch):
        monkeypatch.delenv("BUTLER_PIM_ENCRYPT", raising=False)
        from butler.tools.tenant_store import _encrypt_text
        text = '{"id": "test", "name": "hello"}'
        assert _encrypt_text(text) == text

    def test_decrypt_text_passthrough_without_prefix(self):
        from butler.tools.tenant_store import _decrypt_text
        text = '{"id": "test"}'
        assert _decrypt_text(text) == text

    def test_get_fernet_no_key(self, monkeypatch):
        monkeypatch.setenv("BUTLER_PIM_ENCRYPT", "1")
        monkeypatch.setenv("BUTLER_PIM_ENCRYPT_KEY", "")
        from butler.tools.tenant_store import _get_fernet
        assert _get_fernet() is None

    def test_get_fernet_no_cryptography(self, monkeypatch):
        monkeypatch.setenv("BUTLER_PIM_ENCRYPT", "1")
        monkeypatch.setenv("BUTLER_PIM_ENCRYPT_KEY", "dGVzdGtleQ==")
        with patch.dict("sys.modules", {"cryptography": None, "cryptography.fernet": None}):
            from butler.tools import tenant_store
            import importlib
            importlib.reload(tenant_store)
            result = tenant_store._get_fernet()
        assert result is None

    def test_tenant_store_save_load_unencrypted(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BUTLER_PIM_ENCRYPT", raising=False)
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        monkeypatch.setenv("BUTLER_TENANT", "test_tenant")
        from butler.tools.tenant_store import TenantStore
        store = TenantStore("test_items")
        record = {"id": "item1", "name": "测试", "value": 42}
        store.save(record)
        loaded = store.load_all()
        assert len(loaded) == 1
        assert loaded[0]["name"] == "测试"

    def test_tenant_store_load_one(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BUTLER_PIM_ENCRYPT", raising=False)
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        monkeypatch.setenv("BUTLER_TENANT", "test_tenant")
        from butler.tools.tenant_store import TenantStore
        store = TenantStore("test_items")
        store.save({"id": "rec1", "data": "hello"})
        result = store.load_one("rec1")
        assert result is not None
        assert result["data"] == "hello"


class TestD26DecayMonitoring:
    """D2-6: Decay error rate monitoring in production rerank."""

    def test_rerank_records_decay_evaluation(self):
        from butler.memory.retrieval_ranking import rerank_memory_hits
        now = time.time()
        hits = [
            {"score": 0.8, "created_at": now - 1 * 86400, "access_count": 2},
            {"score": 0.9, "created_at": now - 5 * 86400, "access_count": 1},
        ]
        mock_collector = MagicMock()
        with patch("butler.memory.memory_metrics.get_collector", return_value=mock_collector):
            result = rerank_memory_hits(hits, now=now)
        assert len(result) == 2
        mock_collector.on_decay_evaluation.assert_called_once()
        args = mock_collector.on_decay_evaluation.call_args
        assert args.kwargs["total_important"] == 2

    def test_decay_kills_old_items(self):
        from butler.memory.retrieval_ranking import rerank_memory_hits
        now = time.time()
        hits = [
            {"score": 0.5, "created_at": now - 365 * 86400, "access_count": 0},
        ]
        mock_collector = MagicMock()
        with patch("butler.memory.memory_metrics.get_collector", return_value=mock_collector):
            result = rerank_memory_hits(hits, now=now)
        assert result[0].get("decay_killed", False)
        mock_collector.on_decay_evaluation.assert_called_once_with(
            total_important=1, killed=1,
        )

    def test_recent_items_not_killed(self):
        from butler.memory.retrieval_ranking import rerank_memory_hits
        now = time.time()
        hits = [
            {"score": 0.9, "created_at": now - 1 * 86400, "access_count": 5},
        ]
        mock_collector = MagicMock()
        with patch("butler.memory.memory_metrics.get_collector", return_value=mock_collector):
            result = rerank_memory_hits(hits, now=now)
        assert not result[0].get("decay_killed", False)

    def test_empty_hits_no_call(self):
        from butler.memory.retrieval_ranking import rerank_memory_hits
        mock_collector = MagicMock()
        with patch("butler.memory.memory_metrics.get_collector", return_value=mock_collector):
            result = rerank_memory_hits([])
        mock_collector.on_decay_evaluation.assert_not_called()


class TestC1ExternalRepo:
    """C1: CLI support for Git URL in project register."""

    def test_is_git_url_https(self):
        from butler.cli.projects_cli import _is_git_url
        assert _is_git_url("https://github.com/user/repo.git")

    def test_is_git_url_ssh(self):
        from butler.cli.projects_cli import _is_git_url
        assert _is_git_url("git@github.com:user/repo.git")

    def test_is_not_git_url(self):
        from butler.cli.projects_cli import _is_git_url
        assert not _is_git_url("/home/user/projects/myapp")

    def test_clone_for_register_target_exists(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(tmp_path))
        (tmp_path / "repo").mkdir()
        with patch("butler.config.get_butler_settings") as mock_settings:
            mock_settings.return_value.projects_dir = tmp_path
            from butler.cli.projects_cli import _clone_for_register
            ok, msg = _clone_for_register("https://github.com/user/repo.git")
        assert not ok
        assert "已存在" in msg

    def test_clone_for_register_git_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(tmp_path))
        with patch("butler.config.get_butler_settings") as mock_settings:
            mock_settings.return_value.projects_dir = tmp_path
            with patch("subprocess.run", side_effect=FileNotFoundError):
                from butler.cli.projects_cli import _clone_for_register
                ok, msg = _clone_for_register("https://github.com/user/new_repo.git")
        assert not ok
        assert "git not found" in msg

    def test_register_parser_accepts_path(self):
        from butler.cli.projects_cli import _add_project_register_parser
        import argparse
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers()
        _add_project_register_parser(sub)
