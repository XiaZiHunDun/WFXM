"""Shifts 目录读写：write + list。"""

from __future__ import annotations

from pathlib import Path

import yaml

from butler.blackboard import paths as bb_paths
from butler.blackboard.errors import ShiftIdConflict
from butler.blackboard.schema import ShiftCard


def _shift_path(shift_id: str) -> Path:
    return bb_paths.SHIFTS_DIR / f"{shift_id}.md"


def write_shift_card(card: ShiftCard, body: str = "") -> Path:
    """写一张班次卡到 shifts/<shift_id>.md。

    若文件已存在抛 ShiftIdConflict。
    """
    path = _shift_path(card.shift_id)
    if path.exists():
        raise ShiftIdConflict(f"shift card already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)

    frontmatter = yaml.safe_dump(card.model_dump(mode="json"), allow_unicode=True, sort_keys=False)
    text = f"---\n{frontmatter}---\n\n{body}".rstrip() + "\n"
    path.write_text(text, encoding="utf-8")
    return path


def list_shift_cards() -> list[ShiftCard]:
    """列出所有班次卡（按 shift_id 字典序）。"""
    from butler.blackboard.validator import parse_shift_card_file

    shifts_dir = bb_paths.SHIFTS_DIR
    if not shifts_dir.is_dir():
        return []
    paths = sorted(p for p in shifts_dir.iterdir() if p.suffix == ".md" and p.stem != ".gitkeep")
    return [parse_shift_card_file(p) for p in paths]