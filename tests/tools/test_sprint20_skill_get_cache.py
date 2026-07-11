"""Sprint 20-4 PERF-20-C-1: get_skill / get_skills N+1 缓存.

Sprint 20 subagent C 性能审计:
- SkillManager.get_skill (manager.py:324) 与 get_skills (manager.py:332)
  每次都调 `_load_all()`, `_load_all()` 调 `_load_skill_from_path(path, source)`
  重新 read_text + yaml.safe_load. 一个 LLM turn 内若 AgentLoop 多次
  触发 skill retrieval (e.g. steer / 中断 / 重新派发), 单 turn 内 N skills
  × K calls = N×K file reads + N×K yaml.parse, 全可避免.
- _load_metadata 已有 (path, source) → (mtime, size) 签名缓存, 但只覆盖
  frontmatter (无 content); get_skill 需要 full body, 不命中.

修复: 加 `_full_cache` (同 _metadata_cache 模式, key=(path, source),
value=(sig, full_skill_dict)), `_load_all` 走缓存. 文件 mtime/size 变化
时自动失效, 与 _metadata_cache 失效条件一致 (签名比对). 沿用
Sprint 18-3 read_json_cached 思路但限定在 SkillManager 内部 (per-instance,
因为签名比较是 path 维度, 跨进程无意义).

行为保证:
1) 同 mtime/size 二次 get_skill → 不调 read_text/yaml.safe_load
2) 文件修改 (mtime 变化) → 自动失效, 新内容生效
3) 文件删除 (签名拿不到) → 返回 None
4) cache 命中返回的 dict 与原数据深拷贝, 调用方修改不影响缓存
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from butler.skills.manager import SkillManager


def _write_skill(td: str, name: str, content: str = "Body") -> Path:
    path = Path(td) / f"{name}.md"
    path.write_text(
        f"---\n"
        f"name: {name}\n"
        f"description: {name} desc\n"
        f"triggers:\n"
        f"  - {name}\n"
        f"version: 1\n"
        f"created: '2026-06-01'\n"
        f"---\n"
        f"{content}\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.unit
class TestGetSkillCachesFileRead:
    """get_skill 二次调用应命中缓存, 不重新 read_text."""

    def test_second_get_skill_uses_cache(self, tmp_path: Path):
        """同一 mtime 下, get_skill("foo") 第二次调用不触发 _load_skill_from_path."""
        mgr = SkillManager(tmp_path)
        mgr.create("foo", "Foo", ["foo"], "Body 1", _bypass_approval=True)
        # create() pre-populates _full_cache via _load_all(); clear it so the
        # patched spy below actually sees the first load.
        mgr._full_cache.clear()

        # Spy on _load_skill_from_path via a wrapper.
        original = mgr._load_skill_from_path
        calls: list[tuple[str, str]] = []

        def spy(path, source):
            calls.append((str(path), source))
            return original(path, source)

        with patch.object(mgr, "_load_skill_from_path", side_effect=spy):
            mgr.get_skill("foo")
            first_count = sum(
                1 for p, _ in calls if Path(p).name == "foo.md"
            )
            mgr.get_skill("foo")
            second_count = sum(
                1 for p, _ in calls if Path(p).name == "foo.md"
            )

        # 第一次: 1 次 _load_skill_from_path 调用 (foo.md 第一次加载)
        # 第二次: 0 次 (cache 命中)
        assert second_count == first_count, (
            f"get_skill 第二次调用应命中缓存, 不再调 _load_skill_from_path. "
            f"first={first_count}, second={second_count}"
        )
        assert second_count == first_count and first_count >= 1, (
            f"第一次至少应调 1 次 _load_skill_from_path, 实际: {first_count}"
        )

    def test_get_skills_uses_cache_for_repeated_calls(self, tmp_path: Path):
        """get_skills 多次调用应复用缓存."""
        mgr = SkillManager(tmp_path)
        mgr.create("skill-a", "A", ["a"], "Body A", _bypass_approval=True)
        mgr.create(
            "skill-b", "B", ["b"], "Body B",
            similarity_threshold=1.1, _bypass_approval=True,
        )
        mgr._full_cache.clear()

        original = mgr._load_skill_from_path
        calls: list[str] = []

        def spy(path, source):
            calls.append(Path(path).name)
            return original(path, source)

        with patch.object(mgr, "_load_skill_from_path", side_effect=spy):
            mgr.get_skills(["skill-a", "skill-b"])
            first_count = len(calls)
            mgr.get_skills(["skill-a", "skill-b"])
            second_count = len(calls)

        # 第一次: 2 次 (skill-a.md + skill-b.md)
        # 第二次: 0 新增
        assert second_count == first_count, (
            f"get_skills 第二次调用应命中缓存, "
            f"first={first_count}, second={second_count}"
        )


@pytest.mark.unit
class TestCacheInvalidation:
    """文件变化后缓存应失效."""

    def test_mtime_change_invalidates_cache(self, tmp_path: Path):
        """修改 skill body 后, 下次 get_skill 应拿到新内容."""
        mgr = SkillManager(tmp_path)
        mgr.create("foo", "Foo", ["foo"], "Original body", _bypass_approval=True)
        path = tmp_path / "foo.md"

        # 第一次: 拿到 original
        first = mgr.get_skill("foo")
        assert first["content"] == "Original body"

        # 修改文件 (用 os.utime 强制 mtime +1 ns, 避免文件系统精度问题)
        old_mtime = path.stat().st_mtime_ns
        path.write_text(
            "---\nname: foo\ndescription: Foo\n"
            "triggers:\n  - foo\nversion: 1\n"
            "created: '2026-06-01'\n---\nUpdated body",
            encoding="utf-8",
        )
        os.utime(path, ns=(old_mtime + 1_000_000, old_mtime + 1_000_000))

        # 第二次: 应拿到 updated
        second = mgr.get_skill("foo")
        assert second["content"] == "Updated body", (
            f"文件 mtime 变化后应失效缓存, 实际: {second['content']!r}"
        )

    def test_same_mtime_returns_cached_version(self, tmp_path: Path):
        """同 mtime+size (内容已改但签名未变) → 缓存仍命中, 返回旧值.

        这是签名缓存的契约: 签名一致即返回旧值. 实际场景中 size 通常会
        变, 但若有 caller 写同样长度内容并保留 mtime, 缓存仍命中, 这是
        正确行为 (签名一致性 > 内容实时性).
        """
        mgr = SkillManager(tmp_path)
        mgr.create("foo", "Foo", ["foo"], "Original body", _bypass_approval=True)
        path = tmp_path / "foo.md"
        cached_mtime = path.stat().st_mtime_ns
        cached_size = path.stat().st_size

        # 第一次
        first = mgr.get_skill("foo")
        assert first["content"] == "Original body"

        # 修改内容但保持 mtime+size 完全相同 (signature 仍命中)
        path.write_text(
            "---\nname: foo\ndescription: Foo\n"
            "triggers:\n  - foo\nversion: 1\n"
            "created: '2026-06-01'\n---\nStale body!",
            encoding="utf-8",
        )
        # Stale body! = 11 chars; Original body = 13 chars + \n = 14.
        # 强制 size 一致: 通过 truncate 补到原长
        current = path.read_bytes()
        if len(current) < cached_size:
            path.write_bytes(current + b" " * (cached_size - len(current)))
        elif len(current) > cached_size:
            path.write_bytes(current[:cached_size])
        os.utime(path, ns=(cached_mtime, cached_mtime))
        assert path.stat().st_size == cached_size, (
            f"size 应该等于 cached_size={cached_size}, 实际 {path.stat().st_size}"
        )

        # 第二次: 签名一致, 仍命中缓存, 返回旧内容
        second = mgr.get_skill("foo")
        assert second["content"] == "Original body", (
            f"同 mtime+size 应返回缓存旧值, 实际: {second['content']!r}"
        )


@pytest.mark.unit
class TestReturnedDictIsCopy:
    """get_skill 返回的 dict 是深拷贝, 改它不影响缓存."""

    def test_modifying_returned_dict_does_not_corrupt_cache(self, tmp_path: Path):
        mgr = SkillManager(tmp_path)
        mgr.create("foo", "Foo", ["foo"], "Original body", _bypass_approval=True)

        first = mgr.get_skill("foo")
        first["content"] = "MUTATED"
        first["name"] = "MUTATED_NAME"

        second = mgr.get_skill("foo")
        assert second["content"] == "Original body", (
            f"修改第一次返回的 dict 不应影响缓存, 实际: {second['content']!r}"
        )
        assert second["name"] == "foo", (
            f"修改第一次返回的 name 不应影响缓存, 实际: {second['name']!r}"
        )


@pytest.mark.unit
class TestEdgeCases:
    """边界情况."""

    def test_missing_file_returns_none(self, tmp_path: Path):
        """skill 文件不存在 → get_skill 返 None, 不抛异常."""
        mgr = SkillManager(tmp_path)
        mgr.create("foo", "Foo", ["foo"], "Body", _bypass_approval=True)
        # 删除文件
        (tmp_path / "foo.md").unlink()
        result = mgr.get_skill("foo")
        assert result is None

    def test_multiple_skills_cached_independently(self, tmp_path: Path):
        """多个 skill 各自缓存, 一个失效不影响其他."""
        mgr = SkillManager(tmp_path)
        mgr.create("skill-a", "A", ["a"], "A body", _bypass_approval=True)
        mgr.create(
            "skill-b", "B", ["b"], "B body",
            similarity_threshold=1.1, _bypass_approval=True,
        )

        a_first = mgr.get_skill("skill-a")
        b_first = mgr.get_skill("skill-b")

        # 修改 skill-a 的 mtime
        a_path = tmp_path / "skill-a.md"
        old_mtime = a_path.stat().st_mtime_ns
        a_path.write_text(
            "---\nname: skill-a\ndescription: A\n"
            "triggers:\n  - a\nversion: 1\n"
            "created: '2026-06-01'\n---\nA updated",
            encoding="utf-8",
        )
        os.utime(a_path, ns=(old_mtime + 1_000_000, old_mtime + 1_000_000))

        a_second = mgr.get_skill("skill-a")
        b_second = mgr.get_skill("skill-b")
        assert a_second["content"] == "A updated"
        # skill-b 的 mtime 没变, 应命中缓存
        assert b_second["content"] == "B body"

    def test_static_contract_full_cache_exists(self, tmp_path: Path):
        """SkillManager 内部必须有 `_full_cache` 属性 (静态契约)."""
        mgr = SkillManager(tmp_path)
        assert hasattr(mgr, "_full_cache"), (
            "SkillManager 缺 _full_cache 字段, get_skill N+1 修复未应用"
        )
        # 初始应为空 dict
        assert mgr._full_cache == {}, (
            f"_full_cache 初始应为空, 实际: {mgr._full_cache}"
        )
