"""CLI tests for ``butler memory merge-pending``."""

from __future__ import annotations

import argparse
import json
from unittest.mock import patch

import pytest

from butler.cli.memory_cli import _cmd_memory_merge_pending


@pytest.mark.unit
def test_merge_pending_list_empty(capsys):
    with patch(
        "butler.memory.experience_consolidation.load_merge_pending",
        return_value={},
    ):
        code = _cmd_memory_merge_pending(argparse.Namespace(apply="", dismiss="", json=False))
    assert code == 0
    out = capsys.readouterr().out
    assert "待审队列为空" in out


@pytest.mark.unit
def test_merge_pending_list_json(capsys):
    pending = {
        "exp_merge_1_1": {
            "existing_id": 1,
            "similarity": 0.85,
            "existing_content": "a",
            "new_content": "b",
        }
    }
    with patch(
        "butler.memory.experience_consolidation.load_merge_pending",
        return_value=pending,
    ):
        code = _cmd_memory_merge_pending(argparse.Namespace(apply="", dismiss="", json=True))
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 1
    assert "exp_merge_1_1" in payload["entries"]


@pytest.mark.unit
def test_merge_pending_apply(capsys):
    with patch(
        "butler.memory.experience_consolidation.apply_merge_pending",
        return_value={"ok": True, "key": "k1", "row_id": 3, "similarity": 0.88},
    ):
        code = _cmd_memory_merge_pending(
            argparse.Namespace(apply="k1", dismiss="", json=False),
        )
    assert code == 0
    assert "已合并" in capsys.readouterr().out


@pytest.mark.unit
def test_merge_pending_dismiss_error(capsys):
    with patch(
        "butler.memory.experience_consolidation.dismiss_merge_pending",
        return_value={"ok": False, "error": "unknown key: x"},
    ):
        code = _cmd_memory_merge_pending(
            argparse.Namespace(apply="", dismiss="x", json=False),
        )
    assert code == 1
