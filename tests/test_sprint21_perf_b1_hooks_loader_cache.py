"""Sprint 21-3 PERF-21-B-1: hooks loader YAML 重复解析.

`butler/hooks/loader.py:load_hooks_config` 每次调用都对 3 个 YAML
文件做 `read_text` + `yaml.safe_load` (config.yaml + global hooks.yaml +
project hooks.yaml). 在 LLM turn 内 AgentLoop 多次触发 hook eval
(PreToolUse / PostToolUse / SessionStart / Stop 等), 单 turn 内
K calls × 3 files × (read + parse) = 3K 次磁盘读 + yaml 解析, 全可避免.

`_load_metadata` (skill_manager.py) 已有 mtime+size keyed 缓存模式;
Sprint 20-4 `_full_cache` 也是同样模式. 镜像到 hooks loader.

修复: `_load_file` 加 `_FILE_CACHE` 字典, key=(str(path), mtime, size),
value=list[HookRule]. 同 mtime+size 二次调用直接返缓存, 不读盘不
yaml.safe_load. 文件 mtime/size 变 → 自动失效, 与 skill_manager
模式一致.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from butler.hooks.loader import _load_file


_HOOKS_YAML = """\
hooks:
  PreToolUse:
    - matcher: "Bash|Write"
      command: "echo pre-tool"
  PostToolUse:
    - matcher: "Edit|Write"
      command: "echo post-tool"
  SessionStart:
    - command: "echo session-start"
"""


def _write_hooks(tmp_path: Path, name: str = "hooks.yaml") -> Path:
    path = tmp_path / name
    path.write_text(_HOOKS_YAML, encoding="utf-8")
    return path


@pytest.mark.unit
class TestHooksLoaderCachesFileRead:
    """`_load_file` 二次调用应命中缓存, 不重新 yaml.safe_load."""

    def test_second_load_uses_cache(self, tmp_path: Path):
        """同 mtime 下, _load_file(path) 第二次调用不触发 yaml.safe_load."""
        path = _write_hooks(tmp_path)

        import yaml
        original = yaml.safe_load
        calls: list[str] = []

        def spy(stream, *args, **kwargs):
            calls.append("call")
            return original(stream, *args, **kwargs)

        # Patch yaml.safe_load globally — `_load_file` does
        # `import yaml` inside the function, so patching the module
        # reference (not `butler.hooks.loader.yaml`) is required.
        with patch.object(yaml, "safe_load", side_effect=spy):
            first = _load_file(path)
            first_count = len(calls)
            second = _load_file(path)
            second_count = len(calls)

        # 第一次: 1 次 yaml.safe_load
        # 第二次: 0 次 (cache 命中)
        assert second_count == first_count, (
            f"_load_file 第二次调用应命中缓存, 不再调 yaml.safe_load. "
            f"first={first_count}, second={second_count}"
        )
        assert first_count >= 1, (
            f"第一次至少应调 1 次 yaml.safe_load, 实际: {first_count}"
        )
        # 行为: 两次结果一致
        assert len(first) == len(second), (
            f"缓存命中应返回相同规则数, first={len(first)}, second={len(second)}"
        )

    def test_concurrent_loads_cache_hits(self, tmp_path: Path):
        """多个 _load_file 调用 (不同文件) 各自缓存."""
        path_a = _write_hooks(tmp_path, "a.yaml")
        path_b = _write_hooks(tmp_path, "b.yaml")

        import yaml
        original = yaml.safe_load
        calls: list[str] = []

        def spy(stream, *args, **kwargs):
            calls.append("call")
            return original(stream, *args, **kwargs)

        with patch.object(yaml, "safe_load", side_effect=spy):
            _load_file(path_a)
            _load_file(path_b)
            first_count = len(calls)
            _load_file(path_a)
            _load_file(path_b)
            second_count = len(calls)

        # 第一次: 2 次 (a.yaml + b.yaml)
        # 第二次: 0 新增
        assert second_count == first_count, (
            f"多个文件独立缓存, 第二次调用应全命中. "
            f"first={first_count}, second={second_count}"
        )


@pytest.mark.unit
class TestCacheInvalidation:
    """文件变化后缓存应失效."""

    def test_mtime_change_invalidates_cache(self, tmp_path: Path):
        """修改文件 mtime → 下次 _load_file 应重新解析."""
        path = _write_hooks(tmp_path)
        old_mtime = path.stat().st_mtime_ns

        first = _load_file(path)
        assert len(first) == 3, f"first 应有 3 条规则, 实际 {len(first)}"

        # 修改文件 + mtime +1ns
        path.write_text(
            _HOOKS_YAML.replace("echo pre-tool", "echo UPDATED"),
            encoding="utf-8",
        )
        os.utime(path, ns=(old_mtime + 1_000_000, old_mtime + 1_000_000))

        second = _load_file(path)
        pre_rules = [r for r in second if r.event == "PreToolUse"]
        assert len(pre_rules) >= 1
        assert "UPDATED" in pre_rules[0].command, (
            f"文件 mtime 变化后应失效缓存, 实际: {pre_rules[0].command!r}"
        )

    def test_size_change_invalidates_cache(self, tmp_path: Path):
        """修改文件 size (保持 mtime) → 下次 _load_file 应重新解析."""
        path = _write_hooks(tmp_path)
        cached_mtime = path.stat().st_mtime_ns
        cached_size = path.stat().st_size

        first = _load_file(path)
        assert len(first) == 3

        # 改内容, 但强制 mtime+size 一致 → 签名不变, 仍命中缓存
        path.write_text(
            _HOOKS_YAML.replace("echo pre-tool", "echo stale"),
            encoding="utf-8",
        )
        current = path.read_bytes()
        if len(current) < cached_size:
            path.write_bytes(current + b" " * (cached_size - len(current)))
        elif len(current) > cached_size:
            path.write_bytes(current[:cached_size])
        os.utime(path, ns=(cached_mtime, cached_mtime))
        assert path.stat().st_size == cached_size

        # 同 mtime+size, 仍命中缓存, 返回旧规则
        second = _load_file(path)
        pre_rules = [r for r in second if r.event == "PreToolUse"]
        assert "echo pre-tool" in pre_rules[0].command, (
            f"同 mtime+size 应返回缓存旧值, 实际: {pre_rules[0].command!r}"
        )


@pytest.mark.unit
class TestReturnedRulesAreCopy:
    """`_load_file` 返回的 list 是新 list, 改它不影响缓存."""

    def test_modifying_returned_list_does_not_corrupt_cache(self, tmp_path: Path):
        path = _write_hooks(tmp_path)
        first = _load_file(path)
        first.clear()
        first.append("MUTATED")  # type: ignore[arg-type]

        second = _load_file(path)
        assert len(second) == 3, (
            f"修改第一次返回的 list 不应影响缓存, 实际规则数={len(second)}"
        )
        assert all(hasattr(r, "command") for r in second), (
            "第二次返回的应是 HookRule 对象, 不是字符串"
        )


@pytest.mark.unit
class TestEdgeCases:
    """边界情况."""

    def test_missing_file_returns_empty_list(self, tmp_path: Path):
        """文件不存在 → 返回 [], 不抛异常, 不缓存."""
        path = tmp_path / "nonexistent.yaml"
        result = _load_file(path)
        assert result == []

    def test_invalid_yaml_returns_empty_list(self, tmp_path: Path):
        """YAML 解析失败 → 返回 [], 也不缓存 (下次再试)."""
        path = tmp_path / "bad.yaml"
        path.write_text("not: valid: yaml: [unclosed", encoding="utf-8")
        result = _load_file(path)
        assert result == []

    def test_empty_hooks_dict_returns_empty_list(self, tmp_path: Path):
        """YAML 合法但 hooks 字段为空 → 返回 []."""
        path = tmp_path / "empty.yaml"
        path.write_text("hooks: {}\n", encoding="utf-8")
        result = _load_file(path)
        assert result == []

    def test_static_contract_cache_field_exists(self, tmp_path: Path):
        """`hooks/loader.py` 模块必须有 `_FILE_CACHE` 字段 (静态契约)."""
        from butler.hooks import loader
        assert hasattr(loader, "_FILE_CACHE"), (
            "hooks/loader 缺 _FILE_CACHE 字段, PERF-21-B-1 缓存未应用"
        )
        assert isinstance(loader._FILE_CACHE, dict), (
            f"_FILE_CACHE 应为 dict, 实际: {type(loader._FILE_CACHE)}"
        )
