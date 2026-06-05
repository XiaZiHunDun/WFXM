"""R2-15 [H] log_continue (SSRF 降级) — skill_sources 的 except Exception 把 safe_registry_get 自身的 SSRF 拒绝吞掉.

`butler/registry/skill_sources/github.py:115-126` (`_fetch_raw`):

    for branch in (ref, "master"):
        url = f"{_RAW}/{owner}/{repo}/{branch}/{path}"
        try:
            from butler.registry.url_safety import safe_registry_get
            resp = safe_registry_get(url)
            if resp.status_code == 200:
                return resp.text
        except Exception:        # ← 把 ValueError (SSRF 拒绝) 一起吞
            continue

问题:
- safe_registry_get 在 URL 不安全 (私网 IP / 不在白名单) 时 raise ValueError
- except Exception 把这个**安全信号**当成普通网络错误吞掉
- 操作者只看到通用的 "fetch failed", 不知道 URL 是被 SSRF 检查拒绝
- marketplace.py:240-247, 251-258 同模式

修复:
1) 内层 except 缩窄到 httpx.HTTPError (网络/超时/5xx)
2) ValueError (SSRF 拒绝) 让它**传播到 fetch() 外层**
3) fetch() 在边界处捕获 ValueError, log WARNING (含 URL) + 写 diagnostics
4) 返回 None 与旧行为一致 (操作者仍能继续), 但 SSRF 事件被记录
5) network 错误仍静默 (debug 级别), 不污染日志

行为保证:
1) URL 触发 SSRF 拒绝 (ValueError) → fetch() 返回 None, log WARNING with URL, 记入 diagnostics buffer
2) network 错误 (httpx.HTTPError) → fetch() 返回 None, 无 WARNING log
3) 合法 URL 成功 → fetch() 返回正常 SkillBundle
4) diagnostics buffer 按 FIFO 截断
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
import pytest

from butler.registry import skill_sources
from butler.registry.skill_sources import github as gh_mod
from butler.registry.skill_sources.github import (
    _MAX_SSRF_REJECTION_ENTRIES,
    GitHubSource,
    recent_ssrf_rejections,
    reset_ssrf_rejections,
)


@pytest.fixture(autouse=True)
def _reset_ssrf():
    reset_ssrf_rejections()
    yield
    reset_ssrf_rejections()


def _mock_safe_registry_get(monkeypatch, *, raise_value: Exception | None = None,
                            return_value: Any = None):
    """Patch butler.registry.url_safety.safe_registry_get for the test."""
    def _impl(url, **kwargs):
        if raise_value is not None:
            raise raise_value
        return return_value
    monkeypatch.setattr("butler.registry.url_safety.safe_registry_get", _impl)


def _fake_resp(text: str = "ok", status: int = 200):
    """Build a minimal duck-typed response."""
    return httpx.Response(status_code=status, text=text)


# -----------------------------------------------------------------------
# Test 1: SSRF rejection (ValueError) propagates from inner loop
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestSSRFPropagates:
    """safe_registry_get 抛 ValueError (SSRF 拒绝) 时, 内层 except 不应吞掉."""

    def test_fetch_raw_propagates_value_error(self, monkeypatch):
        """_fetch_raw 内层不应吞 ValueError, 让 SSRF 拒绝传播."""
        _mock_safe_registry_get(monkeypatch, raise_value=ValueError("unsafe registry url: https://x"))
        with pytest.raises(ValueError) as excinfo:
            gh_mod._fetch_raw("owner", "repo", "path.md")
        assert "unsafe" in str(excinfo.value).lower() or "registry" in str(excinfo.value).lower()

    def test_fetch_raw_catches_network_error(self, monkeypatch):
        """httpx.HTTPError 仍被内层 except 吞 (尝试下一个 branch)."""
        _mock_safe_registry_get(
            monkeypatch,
            raise_value=httpx.ConnectError("network down"),
        )
        result = gh_mod._fetch_raw("owner", "repo", "path.md")
        assert result is None, "网络错误应被吞, 返回 None (尝试其他 branch)"

    def test_fetch_api_logs_network_error(self, monkeypatch, caplog):
        """_fetch_api 网络错误 (httpx.HTTPError) log at DEBUG, 不污染日志."""
        # patch httpx.get in the github module namespace
        def _explode(*args, **kwargs):
            raise httpx.ConnectError("network down")
        monkeypatch.setattr(gh_mod.httpx, "get", _explode)
        with caplog.at_level(logging.DEBUG, logger="butler.registry.skill_sources.github"):
            result = gh_mod._fetch_api("owner", "repo", "path.md")
        assert result is None
        debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("github api" in r.message.lower() for r in debug_records), (
            "网络错误应 log at DEBUG"
        )


# -----------------------------------------------------------------------
# Test 2: fetch() boundary catches ValueError, logs warning, records
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestFetchBoundaryHandlesSSRF:
    """fetch() 边界捕获 SSRF 拒绝 → log WARNING + 写 diagnostics, 返回 None."""

    def test_fetch_returns_none_on_ssrf(self, monkeypatch, caplog):
        _mock_safe_registry_get(monkeypatch, raise_value=ValueError("unsafe registry url: https://x"))
        with caplog.at_level(logging.DEBUG, logger="butler.registry.skill_sources.github"):
            result = GitHubSource().fetch("github:owner/repo/path.md")
        assert result is None, (
            "SSRF 拒绝时 fetch() 应返回 None (与旧行为一致)"
        )
        # WARNING log 含 "ssrf" 关键词
        warning_records = [
            r for r in caplog.records
            if r.levelno == logging.WARNING and "ssrf" in r.message.lower()
        ]
        assert warning_records, (
            f"SSRF 拒绝必须 log WARNING, 实际: "
            f"{[(r.levelname, r.message) for r in caplog.records]}"
        )

    def test_fetch_records_ssrf_in_diagnostics(self, monkeypatch):
        _mock_safe_registry_get(monkeypatch, raise_value=ValueError("unsafe registry url: https://x"))
        GitHubSource().fetch("github:owner/repo/path.md")
        rejections = recent_ssrf_rejections()
        assert len(rejections) == 1
        assert "github" in rejections[0]["source"]
        assert "owner/repo" in rejections[0]["url"] or "https://x" in rejections[0]["url"]
        assert "unsafe" in rejections[0]["reason"].lower() or "registry" in rejections[0]["reason"].lower()

    def test_fetch_network_error_does_not_record(self, monkeypatch):
        """网络错误 (httpx.HTTPError) 不写 diagnostics (避免 log spam)."""
        _mock_safe_registry_get(monkeypatch, raise_value=httpx.ConnectError("network"))
        GitHubSource().fetch("github:owner/repo/path.md")
        assert recent_ssrf_rejections() == [], (
            f"网络错误不应记入 SSRF diagnostics, 实际: {recent_ssrf_rejections()!r}"
        )

    def test_fetch_success_does_not_record(self, monkeypatch):
        """合法响应 → fetch() 正常工作, 不写 diagnostics."""
        _mock_safe_registry_get(monkeypatch, return_value=_fake_resp("---\nname: ok\n---\nbody"))
        result = GitHubSource().fetch("github:owner/repo/path.md")
        assert result is not None
        assert result.name == "ok"
        assert recent_ssrf_rejections() == []


# -----------------------------------------------------------------------
# Test 3: public reader API + FIFO cap
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestPublicReader:
    """recent_ssrf_rejections / reset_ssrf_rejections 必须可独立测试."""

    def test_reader_empty_initially(self):
        assert recent_ssrf_rejections() == []

    def test_reset_clears_buffer(self, monkeypatch):
        _mock_safe_registry_get(monkeypatch, raise_value=ValueError("unsafe"))
        GitHubSource().fetch("github:o/r/p.md")
        assert recent_ssrf_rejections()
        reset_ssrf_rejections()
        assert recent_ssrf_rejections() == []

    def test_buffer_is_bounded(self, monkeypatch):
        """buffer 满后按 FIFO 丢弃旧 entry (防止长会话无限增长)."""
        monkeypatch.setattr(gh_mod, "_MAX_SSRF_REJECTION_ENTRIES", 3)
        _mock_safe_registry_get(monkeypatch, raise_value=ValueError("unsafe"))
        for i in range(5):
            GitHubSource().fetch(f"github:o-{i}/r/p.md")
        entries = recent_ssrf_rejections()
        assert len(entries) == 3
        # FIFO: 最旧 2 个 (o-0, o-1) 应被丢弃
        assert all(
            "o-0" not in e["url"] and "o-1" not in e["url"]
            for e in entries
        ), f"最旧 2 个 entry 应被 FIFO 丢弃, 实际: {entries!r}"


# -----------------------------------------------------------------------
# Test 4: marketplace.py _fetch_raw_tree 同样修复
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestMarketplaceSSRF:
    """marketplace._fetch_raw_tree 也遵守相同 narrow-except + boundary 模式."""

    def test_marketplace_fetch_raw_tree_propagates_ssrf(self, monkeypatch):
        from butler.registry.skill_sources import marketplace as mp_mod
        _mock_safe_registry_get(monkeypatch, raise_value=ValueError("unsafe registry url"))
        with pytest.raises(ValueError):
            mp_mod._fetch_raw_tree("https://raw.githubusercontent.com/o/r", "plugins/x")

    def test_marketplace_fetch_raw_tree_catches_network(self, monkeypatch):
        from butler.registry.skill_sources import marketplace as mp_mod
        _mock_safe_registry_get(monkeypatch, raise_value=httpx.ConnectError("network"))
        result = mp_mod._fetch_raw_tree("https://raw.githubusercontent.com/o/r", "plugins/x")
        assert result == {}, "网络错误应被吞, 返回空 dict"
