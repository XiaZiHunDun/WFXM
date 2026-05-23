"""L2 golden path index — corpus.yaml ↔ test_gateway_dev_conversations."""

from __future__ import annotations

import importlib
from typing import Any

from tests.corpus.harness.registry import get_suite, load_suite_corpus

_DEV_MODULE = "tests.test_gateway_dev_conversations"


def golden_blocks(corpus: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        "lingwen_real_dialogue": list(corpus.get("lingwen_real_dialogue") or []),
        "general_dev_habits": list(corpus.get("general_dev_habits") or []),
    }


def validate_golden_index(corpus: dict[str, Any] | None = None) -> list[str]:
    """Ensure each corpus row's ``pytest`` points at an existing test method."""
    if corpus is None:
        corpus, _ = load_suite_corpus(get_suite("wechat_real.lw_real"))
    dev_mod = importlib.import_module(_DEV_MODULE)
    errors: list[str] = []

    for block_name, rows in golden_blocks(corpus).items():
        for row in rows:
            eid = row.get("id", "?")
            pytest_path = str(row.get("pytest") or "").strip()
            if not pytest_path:
                errors.append(f"{block_name}/{eid}: missing pytest")
                continue
            parts = pytest_path.split("::")
            if len(parts) != 2:
                errors.append(f"{block_name}/{eid}: invalid pytest path {pytest_path!r}")
                continue
            cls_name, meth_name = parts
            cls = getattr(dev_mod, cls_name, None)
            if cls is None:
                errors.append(f"{block_name}/{eid}: unknown class {cls_name}")
                continue
            if not getattr(cls, meth_name, None):
                errors.append(f"{block_name}/{eid}: unknown method {meth_name}")
    return errors


def golden_entry_ids(corpus: dict[str, Any] | None = None) -> list[str]:
    if corpus is None:
        corpus, _ = load_suite_corpus(get_suite("wechat_real.lw_real"))
    ids: list[str] = []
    for rows in golden_blocks(corpus).values():
        ids.extend(str(r["id"]) for r in rows if r.get("id"))
    return ids
