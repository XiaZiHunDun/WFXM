"""Unit tests for the learning_graph module."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

import pytest

from butler.core.learning_graph import (
    SkillNode,
    MemoryCard,
    build_skill_nodes,
    build_skill_edges,
    build_memory_skill_edges,
    density_stats,
    _tokenize,
    _category,
    _related,
    _to_int_ts,
)


class TestSkillNode:
    """Tests for SkillNode dataclass."""

    def test_skill_node_creation(self):
        node = SkillNode(name="test-skill", category="test")
        assert node.name == "test-skill"
        assert node.category == "test"
        assert node.source == "profile"
        assert node.use_count == 0
        assert node.state == "active"
        assert node.related == []

    def test_skill_node_with_custom_fields(self):
        node = SkillNode(
            name="custom-skill",
            category="dev",
            source="agent",
            use_count=5,
            pinned=True,
            related=["other-skill"],
        )
        assert node.source == "agent"
        assert node.use_count == 5
        assert node.pinned is True
        assert node.related == ["other-skill"]


class TestMemoryCard:
    """Tests for MemoryCard dataclass."""

    def test_memory_card_creation(self):
        card = MemoryCard(source="memory", title="Test Card", body="Test body")
        assert card.source == "memory"
        assert card.title == "Test Card"
        assert card.body == "Test body"


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_to_int_ts_none(self):
        assert _to_int_ts(None) is None

    def test_to_int_ts_int(self):
        assert _to_int_ts(1234567890) == 1234567890

    def test_to_int_ts_float(self):
        assert _to_int_ts(1234567890.5) == 1234567890

    def test_to_int_ts_string(self):
        assert _to_int_ts("1234567890") == 1234567890

    def test_to_int_ts_invalid(self):
        assert _to_int_ts("invalid") is None

    def test_category_from_frontmatter(self):
        fm = {"category": "dev"}
        assert _category(fm, Path("skills/dev/test/SKILL.md")) == "dev"

    def test_category_from_path(self):
        fm = {}
        path = Path("project/skills/dev/test/SKILL.md")
        assert _category(fm, path) == "dev"

    def test_related_from_list(self):
        fm = {"related_skills": ["skill1", "skill2"]}
        assert _related(fm) == ["skill1", "skill2"]

    def test_related_from_string(self):
        fm = {"related_skills": "[skill1, skill2]"}
        assert _related(fm) == ["skill1", "skill2"]

    def test_related_empty(self):
        fm = {}
        assert _related(fm) == []

    def test_tokenize(self):
        text = "Hello world! This is a test."
        tokens = _tokenize(text)
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens
        assert "is" not in tokens  # Too short


class TestSkillEdges:
    """Tests for skill edge building."""

    def test_build_skill_edges(self):
        nodes = {
            "skill1": SkillNode(name="skill1", category="cat1", related=["skill2"]),
            "skill2": SkillNode(name="skill2", category="cat2", related=["skill1"]),
            "skill3": SkillNode(name="skill3", category="cat3", related=["nonexistent"]),
        }
        edges = build_skill_edges(nodes)
        assert len(edges) == 1
        assert ("skill1", "skill2") in edges

    def test_build_skill_edges_no_related(self):
        nodes = {
            "skill1": SkillNode(name="skill1", category="cat1"),
            "skill2": SkillNode(name="skill2", category="cat2"),
        }
        edges = build_skill_edges(nodes)
        assert edges == []


class TestMemorySkillEdges:
    """Tests for memory-skill edge building."""

    def test_build_memory_skill_edges_exact_match(self):
        cards = [
            MemoryCard(source="memory", title="Python skill tutorial", body="Learning Python programming"),
        ]
        skills = [
            SkillNode(name="Python", category="dev"),
            SkillNode(name="Java", category="dev"),
        ]
        edges = build_memory_skill_edges(cards, skills)
        assert len(edges) == 1
        assert ("memory:memory:0", "Python") in edges

    def test_build_memory_skill_edges_token_overlap(self):
        cards = [
            MemoryCard(source="memory", title="Web development notes", body="HTML CSS JavaScript frontend"),
        ]
        skills = [
            SkillNode(name="Web Development", category="dev"),
            SkillNode(name="JavaScript", category="dev"),
        ]
        edges = build_memory_skill_edges(cards, skills)
        assert len(edges) >= 1

    def test_build_memory_skill_edges_no_match(self):
        cards = [
            MemoryCard(source="memory", title="Cooking recipe", body="How to make pasta"),
        ]
        skills = [
            SkillNode(name="Python", category="dev"),
            SkillNode(name="Java", category="dev"),
        ]
        edges = build_memory_skill_edges(cards, skills)
        assert edges == []


class TestDensityStats:
    """Tests for density statistics."""

    def test_density_stats(self):
        nodes = {
            "skill1": SkillNode(name="skill1", category="cat1"),
            "skill2": SkillNode(name="skill2", category="cat1"),
            "skill3": SkillNode(name="skill3", category="cat2"),
        }
        edges = [("skill1", "skill2")]
        stats = density_stats(nodes, edges)
        assert stats["nodes"] == 3
        assert stats["related_edges"] == 1
        assert stats["categories"] == 2
        assert stats["linked_nodes"] == 2


class TestBuildSkillNodes:
    """Tests for skill node building."""

    @patch("butler.core.learning_graph._load_skill_usage")
    def test_build_skill_nodes_empty_roots(self, mock_load_usage):
        mock_load_usage.return_value = {}
        nodes = build_skill_nodes([("test", Path("/nonexistent/path"))])
        assert nodes == {}

    @patch("butler.core.learning_graph._load_skill_usage")
    @patch("butler.core.learning_graph._iter_skill_files")
    @patch("butler.core.learning_graph._frontmatter")
    def test_build_skill_nodes_with_files(self, mock_frontmatter, mock_iter, mock_load_usage):
        mock_load_usage.return_value = {"test-skill": {"use_count": 3}}
        mock_frontmatter.return_value = {"name": "test-skill", "category": "dev"}
        mock_file = MagicMock(spec=Path)
        mock_file.read_text.return_value = "---\nname: test-skill\ncategory: dev\n---\nSkill content"
        mock_file.parent.name = "test-skill"
        mock_file.stat.return_value.st_mtime = 1234567890
        mock_iter.return_value = [("test", mock_file)]

        nodes = build_skill_nodes([("test", Path("/test"))])
        assert "test-skill" in nodes
        assert nodes["test-skill"].use_count == 3
        assert nodes["test-skill"].category == "dev"