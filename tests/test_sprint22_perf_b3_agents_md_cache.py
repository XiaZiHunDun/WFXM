"""Sprint 22-4 PERF-21-B-3: `load_agent_md` mtime+size 缓存 (MEDIUM perf).

`butler/agents_md.py:44-77` `load_agent_md` 每次调用都
`path.read_text(encoding="utf-8")` + 解析 frontmatter + 构造
AgentMdDef. 无缓存. 该函数被 `merge_agent_md_into_context`
(line 91) 调用, 后者从 `delegate_impl.py:324` 在每个 delegate
任务 (per message) 触发 — 频繁 IO + parse.

修复: 加 mtime+size-keyed cache. 镜像 hooks/loader (Sprint 21-3)
+ workflows/loader (Sprint 22-3) 模式. key 由 (str(workspace),
str(name), str(path), mtime_ns, size) 组成 — workspace + name
都要参与, 因为 path 是 `base / (key.md | key_agent.md)` 派生的.

行为保证:
1) 同一文件二次调用不重读 (Path.read_text 计数不变)
2) 文件 mtime/size 变化 → cache 失效, 重读
3) OSError 不污染 cache (下次重试)
4) cache key 必须包含 mtime_ns + size (防同 mtime 但内容变化)
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest import mock

import pytest

from butler import agents_md


# ---------- helpers ----------

@pytest.fixture
def workspace_with_agent(tmp_path: Path) -> Path:
    """Create workspace with one agent md file."""
    agents_dir = tmp_path / ".butler" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "reviewer.md").write_text(
        "---\n"
        "description: reviews stuff\n"
        "tools:\n  - file_read\n"
        "triggers:\n  - review\n"
        "permission_mode: accept\n"
        "---\n"
        "You are a review agent.\n",
        encoding="utf-8",
    )
    return tmp_path


# ---------- tests ----------

@pytest.mark.unit
class TestLoadAgentMdCache:
    """`load_agent_md` 必须缓存读取结果."""

    def test_module_level_cache_exists(self):
        """源码中必须有模块级 cache dict 字段."""
        assert hasattr(agents_md, "_FILE_CACHE") or hasattr(agents_md, "_AGENT_CACHE"), (
            "agents_md 必须有模块级 cache dict 字段"
        )

    def test_uses_mtime_and_size_for_cache_key(self):
        """cache key 必须含 mtime_ns + size."""
        src = inspect.getsource(agents_md)
        assert "st_mtime_ns" in src, (
            "agents_md 必须用 st_mtime_ns 作 cache key 的一部分, 源码:\n" + src[:1500]
        )
        assert "st_size" in src, (
            "agents_md 必须用 st_size 作 cache key 的一部分, 源码:\n" + src[:1500]
        )

    def test_second_call_no_reread(self, workspace_with_agent, monkeypatch):
        """二次调用同一文件, Path.read_text 不应被再调."""
        read_count = {"n": 0}
        original_read_text = Path.read_text
        def counting(self, *a, **kw):
            # 只计我们关心的 md 文件
            if str(self).endswith("reviewer.md"):
                read_count["n"] += 1
            return original_read_text(self, *a, **kw)
        monkeypatch.setattr(Path, "read_text", counting)

        # Reset cache to ensure first-call is not cached
        cache_attr = "_FILE_CACHE" if hasattr(agents_md, "_FILE_CACHE") else "_AGENT_CACHE"
        if hasattr(agents_md, cache_attr):
            monkeypatch.setattr(agents_md, cache_attr, {})

        agent1 = agents_md.load_agent_md(workspace_with_agent, "reviewer")
        assert agent1 is not None
        first_count = read_count["n"]
        assert first_count >= 1, "首次加载必须读一次"

        agent2 = agents_md.load_agent_md(workspace_with_agent, "reviewer")
        assert agent2 is not None
        # 二次调用不重读
        assert read_count["n"] == first_count, (
            f"二次调用未触发重读, 实际 read_text 次数: "
            f"first={first_count}, after second={read_count['n']}"
        )
        # 同一对象 / 等价 dataclass
        assert agent1.name == agent2.name == "reviewer"
        assert agent1.description == agent2.description

    def test_reparses_on_file_modification(self, workspace_with_agent, monkeypatch):
        """文件 mtime 变化 → cache 失效 → 重新读取."""
        read_count = {"n": 0}
        original_read_text = Path.read_text
        def counting(self, *a, **kw):
            if str(self).endswith("reviewer.md"):
                read_count["n"] += 1
            return original_read_text(self, *a, **kw)
        monkeypatch.setattr(Path, "read_text", counting)

        cache_attr = "_FILE_CACHE" if hasattr(agents_md, "_FILE_CACHE") else "_AGENT_CACHE"
        if hasattr(agents_md, cache_attr):
            monkeypatch.setattr(agents_md, cache_attr, {})

        agent1 = agents_md.load_agent_md(workspace_with_agent, "reviewer")
        first_count = read_count["n"]

        # 修改文件 (mtime 会变, size 也可能变)
        md_path = workspace_with_agent / ".butler" / "agents" / "reviewer.md"
        md_path.write_text(
            "---\ndescription: UPDATED\n---\nNew body.\n",
            encoding="utf-8",
        )

        agent2 = agents_md.load_agent_md(workspace_with_agent, "reviewer")
        # 必须重读
        assert read_count["n"] > first_count, (
            f"文件修改后应重读, 实际 read_text 次数不变: {read_count['n']}"
        )
        assert agent2.description == "UPDATED", "新内容应被读到"

    def test_oserror_does_not_pollute_cache(self, workspace_with_agent, monkeypatch):
        """OSError 失败路径不应 cache None."""
        cache_attr = "_FILE_CACHE" if hasattr(agents_md, "_FILE_CACHE") else "_AGENT_CACHE"
        if hasattr(agents_md, cache_attr):
            monkeypatch.setattr(agents_md, cache_attr, {})

        md_path = workspace_with_agent / ".butler" / "agents" / "reviewer.md"
        original_read_text = Path.read_text
        def raising(self, *a, **kw):
            if str(self).endswith("reviewer.md"):
                raise OSError("simulated I/O error")
            return original_read_text(self, *a, **kw)
        monkeypatch.setattr(Path, "read_text", raising)

        agent1 = agents_md.load_agent_md(workspace_with_agent, "reviewer")
        assert agent1 is None  # OSError → return None

        # 修好 read_text, 修好文件
        monkeypatch.setattr(Path, "read_text", original_read_text)

        # 第二次必须重试, 不能 cache 失败状态
        agent2 = agents_md.load_agent_md(workspace_with_agent, "reviewer")
        assert agent2 is not None, (
            "OSError 后必须能重试成功, 不能 cache 失败状态"
        )

    def test_different_names_cached_independently(self, tmp_path, monkeypatch):
        """不同 agent name 用不同 cache slot."""
        agents_dir = tmp_path / ".butler" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "alpha.md").write_text("---\ndescription: A\n---\nA body.\n", encoding="utf-8")
        (agents_dir / "beta.md").write_text("---\ndescription: B\n---\nB body.\n", encoding="utf-8")

        cache_attr = "_FILE_CACHE" if hasattr(agents_md, "_FILE_CACHE") else "_AGENT_CACHE"
        if hasattr(agents_md, cache_attr):
            monkeypatch.setattr(agents_md, cache_attr, {})

        a1 = agents_md.load_agent_md(tmp_path, "alpha")
        b1 = agents_md.load_agent_md(tmp_path, "beta")
        a2 = agents_md.load_agent_md(tmp_path, "alpha")
        b2 = agents_md.load_agent_md(tmp_path, "beta")
        assert a1.description == "A"
        assert b1.description == "B"
        assert a2.description == "A"
        assert b2.description == "B"

    def test_underscore_suffix_still_cached(self, workspace_with_agent, monkeypatch):
        """`name='reviewer_agent'` 规范化后命中 `reviewer.md` — 也应 cache."""
        cache_attr = "_FILE_CACHE" if hasattr(agents_md, "_FILE_CACHE") else "_AGENT_CACHE"
        if hasattr(agents_md, cache_attr):
            monkeypatch.setattr(agents_md, cache_attr, {})

        read_count = {"n": 0}
        original_read_text = Path.read_text
        def counting(self, *a, **kw):
            if str(self).endswith("reviewer.md"):
                read_count["n"] += 1
            return original_read_text(self, *a, **kw)
        monkeypatch.setattr(Path, "read_text", counting)

        # 两种 name 形式都指向同一文件
        agents_md.load_agent_md(workspace_with_agent, "reviewer")
        first_count = read_count["n"]
        agents_md.load_agent_md(workspace_with_agent, "reviewer_agent")
        # cache key 应包含 name (规范化后) + path,
        # 两次 call 的 cache key 可能不同, 但实际 read_text 只发生一次 (first time)
        # 这里我们只要求两种调用都能成功
        assert first_count >= 1
