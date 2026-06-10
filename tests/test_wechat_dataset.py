"""Tests for butler.ops.wechat_dataset — WeChat corpus → LangFuse Dataset."""

from __future__ import annotations

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from butler.ops.wechat_dataset import (
    parse_utterance_catalog,
    parse_multiturn_catalog,
    catalog_to_dataset_items,
    load_and_push_wechat_dataset,
    WECHAT_CATALOG_DIR,
)


def _write_yaml(path: Path, content: str):
    """Write YAML content to a file."""
    path.write_text(content, encoding="utf-8")


# ── parse_utterance_catalog ──

def test_parse_utterance_catalog_basic(tmp_path):
    catalog_file = tmp_path / "utterance_catalog.yaml"
    _write_yaml(catalog_file, """
utterance_catalog:
  - id: CAT-01
    user: "/新对话"
    category: session_reset
    kind: command
    expect:
      response_contains: [清空]
      no_llm: true
  - id: CAT-02
    user: "当前项目？"
    category: project_status
    kind: command
    expect:
      response_contains: [当前项目]
""")
    items = parse_utterance_catalog(catalog_file)
    assert len(items) == 2
    assert items[0]["id"] == "CAT-01"
    assert items[0]["input"]["user_message"] == "/新对话"
    assert items[0]["input"]["category"] == "session_reset"
    assert items[0]["expected_output"]["response_contains"] == ["清空"]
    assert items[0]["expected_output"]["no_llm"] is True


def test_parse_utterance_catalog_empty_user_skipped(tmp_path):
    catalog_file = tmp_path / "utterance_catalog.yaml"
    _write_yaml(catalog_file, """
utterance_catalog:
  - id: CAT-01
    user: ""
    category: test
  - id: CAT-02
    user: "hello"
    category: greeting
""")
    items = parse_utterance_catalog(catalog_file)
    assert len(items) == 1
    assert items[0]["id"] == "CAT-02"


def test_parse_utterance_catalog_missing_file(tmp_path):
    items = parse_utterance_catalog(tmp_path / "nonexistent.yaml")
    assert items == []


# ── parse_multiturn_catalog ──

def test_parse_multiturn_catalog_basic(tmp_path):
    catalog_file = tmp_path / "multiturn.yaml"
    _write_yaml(catalog_file, """
multiturn_scenarios:
  - id: MT-01
    category: project_workflow
    description: "Multi-turn project creation"
    turns:
      - user: "创建新项目 test"
        turn: 1
        expect:
          response_contains: [创建]
          tools: [write_file]
      - user: "查看项目状态"
        turn: 2
        expect:
          response_contains: [状态]
""")
    items = parse_multiturn_catalog(catalog_file)
    assert len(items) == 1
    assert items[0]["id"] == "MT-01"
    assert items[0]["input"]["category"] == "project_workflow"
    assert len(items[0]["input"]["turns"]) == 2
    assert items[0]["expected_output"]["turn_expectations"][0]["tools"] == ["write_file"]
    assert items[0]["metadata"]["turn_count"] == 2


def test_parse_multiturn_catalog_empty_turns(tmp_path):
    catalog_file = tmp_path / "multiturn.yaml"
    _write_yaml(catalog_file, """
multiturn_scenarios:
  - id: MT-01
    turns: []
""")
    items = parse_multiturn_catalog(catalog_file)
    assert len(items) == 0


# ── catalog_to_dataset_items ──

def test_catalog_to_dataset_items():
    catalog_items = [
        {
            "id": "CAT-01",
            "input": {"user_message": "hello"},
            "expected_output": {"intent": "greeting"},
            "metadata": {"source": "test"},
        }
    ]
    ds_items = catalog_to_dataset_items(catalog_items)
    assert len(ds_items) == 1
    assert ds_items[0].input == {"user_message": "hello"}
    assert ds_items[0].source_id == "CAT-01"


# ── load_and_push_wechat_dataset ──

def test_load_and_push_wechat_dataset_from_dir(tmp_path):
    catalog_file = tmp_path / "utterance_catalog.yaml"
    _write_yaml(catalog_file, """
utterance_catalog:
  - id: T-01
    user: "你好"
    category: greeting
    kind: llm
    expect:
      response_contains_any: [你好, 您好]
  - id: T-02
    user: "/帮助"
    category: help
    kind: command
    expect:
      response_contains: [帮助]
""")

    with patch("butler.ops.eval_bridge.create_dataset", return_value="ds-1") as mock_create, \
         patch("butler.ops.eval_bridge.push_dataset_items") as mock_push:
        from butler.ops.eval_bridge import EvalReport
        mock_push.return_value = EvalReport(dataset_items_pushed=2)

        summary = load_and_push_wechat_dataset(catalog_dir=tmp_path)
        assert summary["single_turn_items"] == 2
        assert summary["multi_turn_items"] == 0
        assert "butler-wechat-single-turn" in summary["datasets_created"]
        mock_create.assert_called_once()
        mock_push.assert_called_once()


def test_load_and_push_wechat_dataset_with_multiturn(tmp_path):
    catalog_file = tmp_path / "utterance_catalog.yaml"
    _write_yaml(catalog_file, """
utterance_catalog:
  - id: T-01
    user: "hello"
    category: greeting
""")
    mt_file = tmp_path / "utterance_multiturn_catalog.yaml"
    _write_yaml(mt_file, """
multiturn_scenarios:
  - id: MT-01
    turns:
      - user: "step1"
      - user: "step2"
""")

    with patch("butler.ops.eval_bridge.create_dataset", return_value="ds-1"), \
         patch("butler.ops.eval_bridge.push_dataset_items") as mock_push:
        from butler.ops.eval_bridge import EvalReport
        mock_push.return_value = EvalReport(dataset_items_pushed=1)

        summary = load_and_push_wechat_dataset(catalog_dir=tmp_path)
        assert summary["single_turn_items"] == 1
        assert summary["multi_turn_items"] == 1
        assert mock_push.call_count == 2


def test_load_and_push_empty_dir(tmp_path):
    with patch("butler.ops.eval_bridge.create_dataset") as mock_create, \
         patch("butler.ops.eval_bridge.push_dataset_items") as mock_push:
        summary = load_and_push_wechat_dataset(catalog_dir=tmp_path)
        assert summary["single_turn_items"] == 0
        assert summary["multi_turn_items"] == 0
        mock_create.assert_not_called()
        mock_push.assert_not_called()


# ── Real catalog parse (smoke) ──

def test_real_utterance_catalog_parseable():
    """Smoke test: verify the real utterance catalog can be parsed."""
    catalog_file = WECHAT_CATALOG_DIR / "utterance_catalog.yaml"
    if not catalog_file.exists():
        pytest.skip("utterance_catalog.yaml not found")
    items = parse_utterance_catalog(catalog_file)
    assert len(items) > 0, "Should parse at least one item from real catalog"
    for item in items[:3]:
        assert item["id"], "Each item should have an id"
        assert item["input"]["user_message"], "Each item should have user text"
