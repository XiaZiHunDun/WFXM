"""Unit tests for real API smoke gate helpers (no network)."""

from __future__ import annotations

import pytest

from tests.test_real_api_smoke import _require_provider, _require_smoke_enabled


def test_require_smoke_enabled_skips_without_flag(monkeypatch):
    monkeypatch.delenv("BUTLER_RUN_REAL_API_SMOKE", raising=False)
    with pytest.raises(pytest.skip.Exception):
        _require_smoke_enabled()


def test_require_provider_skips_without_api_key(monkeypatch):
    monkeypatch.setenv("BUTLER_RUN_REAL_API_SMOKE", "1")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(pytest.skip.Exception):
        _require_provider("deepseek")
