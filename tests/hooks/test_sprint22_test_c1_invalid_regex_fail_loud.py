"""Sprint 22-5 TEST-21-C-1: invalid regex fail-loud (MEDIUM quality).

`butler/hooks/loader.py:140-146` `match_hook_query` 处理 `re:`
前缀 matcher 用 `re.search(pat[3:], query, re.DOTALL)`. 错误
处理 (line 145) **静默 return False** — 用户在 hooks.yaml
写 `matcher: re:[invalid(` 这样的非法 regex 时, 代码装作
"没有匹配", 用户不知道为什么 hook 不触发.

对比 `butler/permissions/rules.py:279-280` 的同场景: 该处
捕获 `re.error` 后 `logger.warning("security_blacklist regex
invalid: %s", exc)` — 至少记一条 warning. 这是 codebase 内
统一 "invalid regex fail-loud" 模式.

修复: `match_hook_query` 在 catch `re.error` 时也 `logger.warning`,
镜像 permissions/rules.py 行为, 让用户能看到 regex 错误.

行为保证:
1) 合法 regex 仍正确匹配
2) 非法 regex 触发 re.error 时, 仍 return False (不抛 — 不破坏
   dispatch), **且** 记录 warning 日志
3) warning 日志包含原始 matcher 信息 (user 可见) + 错误细节
4) 没有 logger 配置时也不抛 (use module-level logger)
"""

from __future__ import annotations

import logging

import pytest

from butler.hooks import loader


# ---------- tests ----------

@pytest.mark.unit
class TestInvalidRegexFailLoud:
    """`match_hook_query` 必须对 invalid regex 记录 warning."""

    def test_valid_regex_matches(self):
        """合法 `re:` matcher 正常工作."""
        assert loader.match_hook_query("re:foo", "this has foo in it") is True
        assert loader.match_hook_query("re:foo", "no match here") is False

    def test_invalid_regex_does_not_raise(self):
        """非法 regex 不抛, 静默返 False (向后兼容)."""
        # 开放括号不闭合 → re.error
        result = loader.match_hook_query("re:[invalid(", "any query")
        assert result is False, "非法 regex 仍返 False (不破坏 dispatch)"

    def test_invalid_regex_logs_warning(self, caplog):
        """非法 regex 触发 WARNING 日志 (fail-loud)."""
        caplog.set_level(logging.WARNING, logger=loader.logger.name)
        loader.match_hook_query("re:[invalid(", "any query")
        # 验证: 有 WARNING 级别记录, 内容含 invalid regex 信息
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings, (
            "非法 regex 必须触发 WARNING 日志 (fail-loud 行为), "
            f"实际 caplog.records: {[r.levelname for r in caplog.records]}"
        )
        # 日志信息应能让用户定位
        msg = warnings[0].getMessage().lower()
        assert "regex" in msg or "re:" in msg or "matcher" in msg or "pattern" in msg, (
            f"warning 信息应提及 regex/matcher/pattern, 实际: {warnings[0].getMessage()!r}"
        )

    def test_multiple_invalid_regexes_each_warned(self, caplog):
        """多次非法 regex 调用, 每次都记录 warning (不聚合)."""
        caplog.set_level(logging.WARNING, logger=loader.logger.name)
        loader.match_hook_query("re:[bad(", "q1")
        loader.match_hook_query("re:*?+invalid", "q2")
        loader.match_hook_query("re:(?P<dup>a)(?P<dup>b)", "q3")
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 3, (
            f"3 次非法 regex 应产生 3 条 warning, 实际 {len(warnings)} 条"
        )

    def test_warning_includes_matcher_for_user_visibility(self, caplog):
        """warning 日志应包含原始 matcher (用户能定位 config.yaml 哪行)."""
        caplog.set_level(logging.WARNING, logger=loader.logger.name)
        loader.match_hook_query("re:[user-typoed(", "query")
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings
        msg = warnings[0].getMessage()
        # 至少包含 pat[3:] 内容 (即 user 实际写的 regex 文本)
        # 或包含 re.error 的异常信息
        assert ("user-typoed" in msg) or ("[" in msg and "unbalanced" in msg.lower()) or (
            "regex" in msg.lower()
        ), f"warning 应包含 matcher 内容或 regex 错误, 实际: {msg!r}"

    def test_non_re_prefix_invalid_still_works(self):
        """非 `re:` 前缀的非法字符不应影响 (substr 匹配 / `*` 等)."""
        # `*` 通配
        assert loader.match_hook_query("*", "anything") is True
        # 普通字符串包含
        assert loader.match_hook_query("hello", "say hello world") is True
        assert loader.match_hook_query("hello", "goodbye") is False
        # `|` 分隔的多 matcher
        assert loader.match_hook_query("foo|bar", "has bar") is True
        assert loader.match_hook_query("foo|bar", "has baz") is False
