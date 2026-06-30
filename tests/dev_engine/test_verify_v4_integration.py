"""Tests for DE-GAP-2 — enhanced auto-verify V1-V5 and verify_level_for_edit."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestVerifyLevelForEdit:
    def test_empty_files(self):
        from butler.dev_engine.verify import verify_level_for_edit
        assert verify_level_for_edit([]) == "lint"

    def test_source_file(self):
        from butler.dev_engine.verify import verify_level_for_edit
        result = verify_level_for_edit(["foo.py"])
        assert "lint" in result
        assert "test" in result

    def test_test_file(self):
        from butler.dev_engine.verify import verify_level_for_edit
        result = verify_level_for_edit(["test_foo.py"])
        assert "lint" in result
        assert "test" in result

    def test_config_file(self):
        from butler.dev_engine.verify import verify_level_for_edit
        result = verify_level_for_edit(["pyproject.toml"])
        assert "lint" in result
        assert "build" in result

    def test_mixed_files(self):
        from butler.dev_engine.verify import verify_level_for_edit
        result = verify_level_for_edit(["main.py", "setup.toml"])
        assert "lint" in result
        assert "test" in result
        assert "build" in result

    def test_docs_file_lint_only(self):
        from butler.dev_engine.verify import verify_level_for_edit
        result = verify_level_for_edit(["README.md"])
        assert result == "lint"

    def test_js_file(self):
        from butler.dev_engine.verify import verify_level_for_edit
        result = verify_level_for_edit(["app.js"])
        assert "test" in result


class TestAutoVerifyLevels:
    def test_default(self, monkeypatch):
        monkeypatch.delenv("BUTLER_DEV_AUTO_VERIFY_LEVELS", raising=False)
        from butler.dev_engine import verify
        import importlib
        importlib.reload(verify)
        assert verify.auto_verify_levels() == "lint,test"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("BUTLER_DEV_AUTO_VERIFY_LEVELS", "lint,typecheck,test,build")
        from butler.dev_engine.verify import auto_verify_levels
        assert auto_verify_levels() == "lint,typecheck,test,build"


class TestVerifyIntegration:
    def test_verify_integration_no_pytest(self, tmp_path):
        from butler.dev_engine.verify import verify_integration
        from butler.dev_engine.dev_state import VerifyStatus
        with patch("butler.dev_engine.verify._has_tool", return_value=False):
            result = verify_integration(tmp_path)
        assert result.status == VerifyStatus.SKIP

    def test_verify_integration_with_pytest(self, tmp_path):
        from butler.dev_engine.verify import verify_integration
        from butler.dev_engine.dev_state import VerifyStatus
        with patch("butler.dev_engine.verify._has_tool", return_value=True):
            result = verify_integration(tmp_path, timeout=5)
        assert result.status in (
            VerifyStatus.PASS,
            VerifyStatus.FAIL,
            VerifyStatus.SKIP,
            VerifyStatus.TIMEOUT,
        )


class TestVerifyLayeredIntegrationLevel:
    def test_integration_in_dispatch(self):
        from butler.dev_engine.verify import verify_layered
        from butler.dev_engine.dev_state import VerifyStatus
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            with patch("butler.dev_engine.verify._has_tool", return_value=False):
                result = verify_layered(ws, levels="integration")
            assert result.status in (VerifyStatus.PASS, VerifyStatus.SKIP)

    def test_full_v1_to_v5_levels(self):
        from butler.dev_engine.verify import verify_layered
        from butler.dev_engine.dev_state import VerifyStatus
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            with patch("butler.dev_engine.verify._has_tool", return_value=False):
                result = verify_layered(ws, levels="lint,typecheck,test,integration,build")
            assert result.status in (VerifyStatus.PASS, VerifyStatus.SKIP)
