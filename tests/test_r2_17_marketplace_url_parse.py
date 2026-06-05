"""R2-17 [H] silent_pass — marketplace URL 解析任意异常被静默吞掉.

`butler/registry/skill_sources/marketplace.py:111-112` (`_raw_base_from_github_marketplace_url`):

    try:
        parsed = urlparse(url)
        if parsed.hostname != "github.com":
            return None
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) < 2:
            return None
        owner, repo = parts[0], parts[1]
        ref = "main"
        if len(parts) > 3 and parts[2] in ("blob", "tree"):
            ref = parts[3]
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}"
    except Exception:    # ← 任意异常都吞掉
        return None

问题:
- 真正的 parse 失败 (e.g. urlparse 抛 ValueError) 被当 "URL invalid" 处理
- 后续错误信息 "URL invalid" 掩盖了真正问题 (parse 失败 vs URL 失效)
- 不可预测的 bug (IndexError, AttributeError) 都被 silently swallowed
- 修复: 区分"URL 损坏" (raise) vs "URL 失效" (return None 与旧行为一致)

行为保证:
1) 合法 GitHub URL → 返回 raw base (旧行为)
2) 非 GitHub URL → 返回 None (旧行为, "URL 失效")
3) urlparse 抛异常 → 重新抛出 (新行为, "URL 损坏" 信号)
4) 其他意外异常 (IndexError 等) → 重新抛出 (新行为)
5) 函数正常路径不变
"""

from __future__ import annotations

import pytest

from butler.registry.skill_sources import marketplace as mp_mod
from butler.registry.skill_sources.marketplace import (
    _raw_base_from_github_marketplace_url,
)


# -----------------------------------------------------------------------
# Test 1: valid GitHub URL returns raw base (existing behavior)
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestValidGitHubURL:
    """合法 GitHub URL 走 happy path, 行为不变."""

    def test_simple_owner_repo(self):
        result = _raw_base_from_github_marketplace_url(
            "https://github.com/owner/repo/marketplace.json"
        )
        assert result == "https://raw.githubusercontent.com/owner/repo/main"

    def test_blob_ref(self):
        result = _raw_base_from_github_marketplace_url(
            "https://github.com/owner/repo/blob/v1.0/marketplace.json"
        )
        assert result == "https://raw.githubusercontent.com/owner/repo/v1.0"

    def test_tree_ref(self):
        result = _raw_base_from_github_marketplace_url(
            "https://github.com/owner/repo/tree/feature-branch/marketplace.json"
        )
        assert result == "https://raw.githubusercontent.com/owner/repo/feature-branch"


# -----------------------------------------------------------------------
# Test 2: non-GitHub URL returns None (existing behavior)
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestNonGitHubURL:
    """非 GitHub URL → None (旧行为, "URL 失效" 区分于 "URL 损坏")."""

    def test_other_host(self):
        result = _raw_base_from_github_marketplace_url(
            "https://example.com/foo/bar/marketplace.json"
        )
        assert result is None

    def test_too_few_path_parts(self):
        result = _raw_base_from_github_marketplace_url(
            "https://github.com/owner"
        )
        assert result is None

    def test_empty_string(self):
        result = _raw_base_from_github_marketplace_url("")
        assert result is None


# -----------------------------------------------------------------------
# Test 3: urlparse raises → propagates (new behavior)
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestURLParseFailure:
    """urlparse 抛异常时, 必须 raise (新行为, "URL 损坏" 信号)."""

    def test_urlparse_raises_propagates(self, monkeypatch):
        """urlparse 抛 ValueError → _raw_base_from_github_marketplace_url 重抛."""
        from urllib.parse import urlparse as orig_urlparse

        def _explode(url, *args, **kwargs):
            raise ValueError("simulated urlparse corruption")

        monkeypatch.setattr(mp_mod, "urlparse", _explode)
        with pytest.raises(ValueError) as excinfo:
            _raw_base_from_github_marketplace_url("https://github.com/o/r/marketplace.json")
        assert "simulated" in str(excinfo.value).lower()

    def test_unexpected_attribute_error_propagates(self, monkeypatch):
        """意外 AttributeError (e.g. code bug) 也必须 raise, 不能被吞."""
        from urllib.parse import urlparse as orig_urlparse

        class _WeirdParsed:
            @property
            def hostname(self):
                raise AttributeError("simulated: parsed object is broken")

        monkeypatch.setattr(mp_mod, "urlparse", lambda u: _WeirdParsed())
        with pytest.raises(AttributeError):
            _raw_base_from_github_marketplace_url("https://github.com/o/r/marketplace.json")


# -----------------------------------------------------------------------
# Test 4: type-error input propagates (defensive overcatch removed)
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestTypeErrorPropagates:
    """非字符串输入 → urlparse 不抛 (返回 hostname=None), 函数返回 None (走 "非 GitHub URL" 分支)."""

    def test_none_input_returns_none(self):
        # urlparse(None) returns ParseResult with all-None fields, not raises.
        # The "not a GitHub URL" branch correctly returns None for this.
        # The contract: the function must NOT silently swallow real
        # exceptions; the audit's "URL 损坏 → raise" applies to genuine
        # parse errors, not to "no URL provided".
        result = _raw_base_from_github_marketplace_url(None)
        assert result is None
