"""Shift card YAML 解析 + schema 校验入口。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from butler.blackboard.errors import SchemaError
from butler.blackboard.schema import ShiftCard

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _split_frontmatter(text: str) -> tuple[str, str]:
    """返回 (yaml_block, body)。无 frontmatter 时抛 SchemaError。"""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise SchemaError("missing YAML frontmatter (expected leading '---' ... '---' block)")
    return m.group(1), text[m.end() :]


def parse_shift_card_yaml(text: str) -> ShiftCard:
    """解析 YAML 文本 + 校验，返回 ShiftCard。失败抛 SchemaError。"""
    yaml_block, _body = _split_frontmatter(text)
    try:
        data: dict[str, Any] = yaml.safe_load(yaml_block)
    except yaml.YAMLError as exc:
        raise SchemaError(f"invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise SchemaError(f"frontmatter must be a YAML mapping, got {type(data).__name__}")
    try:
        return ShiftCard.model_validate(data)
    except ValidationError as exc:
        raise SchemaError(str(exc)) from exc


def parse_shift_card_file(path: Path) -> ShiftCard:
    """读文件 + 解析 + 校验。文件不存在抛 FileNotFoundError。"""
    text = Path(path).read_text(encoding="utf-8")
    return parse_shift_card_yaml(text)