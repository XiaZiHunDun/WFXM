"""Tests for persisted plan mode flags."""

from butler.plan_mode import clear_plan_mode, is_plan_mode, set_plan_mode


def test_plan_mode_survives_memory_clear(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    sk = "wechat:persist:_"
    set_plan_mode(sk, True)
    from butler import plan_mode as pm

    pm._PLAN_BY_SESSION.clear()
    assert is_plan_mode(sk)
    clear_plan_mode(sk)
    assert not is_plan_mode(sk)
