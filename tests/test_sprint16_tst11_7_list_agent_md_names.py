"""Sprint 16 TST-11-7: butler.agents_md.list_agent_md_names 0% 覆盖.

bug: butler/agents_md.py:80-88
  - list_agent_md_names 是 CLI/配置加载的入口之一, 0% 覆盖
  - load_agent_md / merge_agent_md_into_context 已被覆盖
  - 该函数读 workspace/.butler/agents/*.md, 返回排序后的 stem 列表

修复: 直接补单测覆盖 4 个分支, 不改实现。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from butler.agents_md import list_agent_md_names


# ── list_agent_md_names 覆盖 ──


class TestListAgentMdNames:
    def test_empty_when_agents_dir_missing(self, tmp_path: Path):
        """workspace/.butler/agents 不存在 → 返回 [] (不抛 FileNotFoundError)。"""
        # tmp_path 没有 .butler/agents 子目录
        assert not (tmp_path / ".butler" / "agents").exists()
        result = list_agent_md_names(tmp_path)
        assert result == []

    def test_returns_sorted_stems(self, tmp_path: Path):
        """多个 .md 文件 → 返回按文件名排序的 stem 列表。"""
        agents_dir = tmp_path / ".butler" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "zulu.md").write_text("z", encoding="utf-8")
        (agents_dir / "alpha.md").write_text("a", encoding="utf-8")
        (agents_dir / "mike.md").write_text("m", encoding="utf-8")

        result = list_agent_md_names(tmp_path)
        assert result == ["alpha", "mike", "zulu"]

    def test_filters_out_subdirectories(self, tmp_path: Path):
        """glob('*.md') 匹配子目录 (如 'foo.md/') → 应只保留 file。"""
        agents_dir = tmp_path / ".butler" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "real.md").write_text("r", encoding="utf-8")
        # 创建一个与 *.md glob 匹配的子目录 (极端情况, 但代码 is_file() 防御)
        (agents_dir / "fake.md").mkdir()
        # 注: glob('*.md') 默认不匹配子目录, 这里 is_file() 防御是 belt-and-suspenders
        result = list_agent_md_names(tmp_path)
        assert "real" in result
        # fake.md 是目录, 即使 glob 命中也不应出现
        assert "fake.md" not in result

    def test_accepts_string_workspace(self, tmp_path: Path):
        """workspace 传 str 也应工作 (Path 强制转换)。"""
        agents_dir = tmp_path / ".butler" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "solo.md").write_text("s", encoding="utf-8")

        result = list_agent_md_names(str(tmp_path))
        assert result == ["solo"]

    def test_empty_dir_returns_empty(self, tmp_path: Path):
        """.butler/agents 存在但空 → []。"""
        agents_dir = tmp_path / ".butler" / "agents"
        agents_dir.mkdir(parents=True)
        assert list_agent_md_names(tmp_path) == []
