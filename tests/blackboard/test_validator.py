"""YAML 解析 + schema 校验测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from butler.blackboard.errors import SchemaError
from butler.blackboard.validator import parse_shift_card_yaml, parse_shift_card_file


VALID_YAML = """---
shift_id: 2026-07-13-claude-001
agent: claude-code
session_window:
  start: 2026-07-13T09:00:00+08:00
intent: 测试
scope: [tests/]
read_at_start: [.blackboard/README.md]
schema_version: 1
---

# Body
"""


def test_parse_yaml_string_valid():
    card = parse_shift_card_yaml(VALID_YAML)
    assert card.shift_id == "2026-07-13-claude-001"
    assert card.intent == "测试"


def test_parse_yaml_string_missing_frontmatter():
    bad = "# No frontmatter\nbody\n"
    with pytest.raises(SchemaError):
        parse_shift_card_yaml(bad)


def test_parse_yaml_string_invalid_agent():
    bad = """---
shift_id: 2026-07-13-x-001
agent: not-in-enum
session_window: {start: 2026-07-13T09:00:00+08:00}
intent: x
scope: [tests/]
read_at_start: [.blackboard/README.md]
schema_version: 1
---
"""
    with pytest.raises(SchemaError):
        parse_shift_card_yaml(bad)


def test_parse_file_valid(tmp_path):
    p = tmp_path / "2026-07-13-claude-001.md"
    p.write_text(VALID_YAML)
    card = parse_shift_card_file(p)
    assert card.shift_id == "2026-07-13-claude-001"


def test_parse_file_missing(tmp_path):
    p = tmp_path / "nope.md"
    with pytest.raises(FileNotFoundError):
        parse_shift_card_file(p)