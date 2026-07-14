"""G2-08 CA4 strict env layer coverage + default coordination."""
from __future__ import annotations

import pytest


@pytest.fixture
def strict_env(monkeypatch):
    """Set BUTLER_CODING_STRICT=1; cleanup after."""
    monkeypatch.setenv("BUTLER_CODING_STRICT", "1")
    yield
    monkeypatch.delenv("BUTLER_CODING_STRICT", raising=False)


def test_coding_strict_env_unset_returns_false(monkeypatch):
    """BUTLER_CODING_STRICT unset → coding_strict_enabled() returns False."""
    monkeypatch.delenv("BUTLER_CODING_STRICT", raising=False)
    from butler.dev_engine.dev_tools import coding_strict_enabled
    assert coding_strict_enabled() is False


def test_coding_strict_env_set_returns_true(strict_env):
    """BUTLER_CODING_STRICT=1 → coding_strict_enabled() returns True."""
    from butler.dev_engine.dev_tools import coding_strict_enabled
    assert coding_strict_enabled() is True


def test_effective_coding_strict_safe_default_false(monkeypatch):
    """effective_coding_strict_safe() default keyword changed to False (G2-08 spec §4.2)."""
    monkeypatch.delenv("BUTLER_CODING_STRICT", raising=False)
    from butler.dev_engine.delegate_init_ops import effective_coding_strict_safe
    sig = effective_coding_strict_safe.__kwdefaults__
    assert sig is not None
    assert sig.get("default") is False