"""Gateway dev slash commands."""

from butler.gateway.dev_commands import format_dev_status, handle_dev_command, run_dev_smoke


def test_dev_status_command():
    out = handle_dev_command("/开发状态", "")
    assert out is not None
    assert "BUTLER_ENABLE_TERMINAL" in out


def test_dev_smoke_disabled_by_default(monkeypatch):
    monkeypatch.delenv("BUTLER_WECHAT_DEV_SMOKE", raising=False)
    out = run_dev_smoke()
    assert "BUTLER_WECHAT_DEV_SMOKE=0" in out or "未启用" in out


def test_format_dev_status_has_git_write():
    assert "GIT_WRITE" in format_dev_status()
