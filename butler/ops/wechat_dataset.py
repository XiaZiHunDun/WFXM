"""WeChat corpus → LangFuse Dataset converter.

Reads utterance catalog YAML files and converts them to LangFuse Dataset items
for structured evaluation. Supports both single-turn and multi-turn catalogs.

Usage::

    from butler.ops.wechat_dataset import load_and_push_wechat_dataset
    report = load_and_push_wechat_dataset()
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CORPUS_ROOT = Path(__file__).resolve().parent.parent.parent / "tests" / "corpus" / "suites"
WECHAT_CATALOG_DIR = CORPUS_ROOT / "wechat_real" / "lw_real"

DATASET_NAME_SINGLE = "butler-wechat-single-turn"
DATASET_NAME_MULTI = "butler-wechat-multi-turn"


def _safe_load_yaml(path: Path) -> Any:
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except ImportError:
        import json
        logger.warning("PyYAML not installed; attempting JSON fallback for %s", path.name)
        return None
    except Exception as exc:
        logger.warning("Failed to load %s: %s", path, exc)
        return None


def parse_utterance_catalog(path: Path) -> list[dict[str, Any]]:
    """Parse an utterance catalog YAML into a list of structured items."""
    data = _safe_load_yaml(path)
    if data is None:
        return []

    items: list[dict[str, Any]] = []
    catalog = data.get("utterance_catalog", [])
    if not catalog:
        catalog = data.get("catalog", [])

    for entry in catalog:
        if not isinstance(entry, dict):
            continue
        item_id = entry.get("id", "")
        user_text = entry.get("user", "")
        if not user_text:
            continue

        expect = entry.get("expect", {}) or {}
        items.append({
            "id": item_id,
            "input": {
                "user_message": user_text,
                "category": entry.get("category", ""),
                "kind": entry.get("kind", ""),
                "fixture": entry.get("fixture", ""),
            },
            "expected_output": {
                "response_contains": expect.get("response_contains", []),
                "response_contains_any": expect.get("response_contains_any", []),
                "tools": expect.get("tools", []),
                "intent": expect.get("intent", entry.get("category", "")),
                "no_llm": expect.get("no_llm", False),
                "response_max_lines": expect.get("response_max_lines", 0),
            },
            "metadata": {
                "source_file": path.name,
                "setup": entry.get("setup", ""),
                "script": entry.get("script", ""),
            },
        })

    return items


def parse_multiturn_catalog(path: Path) -> list[dict[str, Any]]:
    """Parse a multi-turn utterance catalog into structured items."""
    data = _safe_load_yaml(path)
    if data is None:
        return []

    items: list[dict[str, Any]] = []
    scenarios = data.get("multiturn_scenarios", [])
    if not scenarios:
        scenarios = data.get("scenarios", [])

    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        scenario_id = scenario.get("id", "")
        turns = scenario.get("turns", [])
        if not turns:
            continue

        messages = []
        expected_outputs = []
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            user_msg = turn.get("user", "")
            if user_msg:
                messages.append({"role": "user", "content": user_msg})
            expect = turn.get("expect", {}) or {}
            if expect:
                expected_outputs.append({
                    "turn": turn.get("turn", len(messages)),
                    "response_contains": expect.get("response_contains", []),
                    "response_contains_any": expect.get("response_contains_any", []),
                    "tools": expect.get("tools", []),
                })

        items.append({
            "id": scenario_id,
            "input": {
                "scenario_id": scenario_id,
                "turns": messages,
                "category": scenario.get("category", ""),
            },
            "expected_output": {
                "turn_expectations": expected_outputs,
            },
            "metadata": {
                "source_file": path.name,
                "turn_count": len(messages),
                "description": scenario.get("description", ""),
            },
        })

    return items


def catalog_to_dataset_items(catalog_items: list[dict[str, Any]]) -> list[Any]:
    """Convert parsed catalog items to DatasetItem objects."""
    from butler.ops.eval_bridge import DatasetItem

    result = []
    for item in catalog_items:
        result.append(DatasetItem(
            input=item.get("input", {}),
            expected_output=item.get("expected_output", {}),
            metadata=item.get("metadata", {}),
            source_id=item.get("id", ""),
        ))
    return result


def load_and_push_wechat_dataset(
    catalog_dir: Path | None = None,
) -> dict[str, Any]:
    """Load all WeChat catalogs and push to LangFuse datasets.

    Returns a summary dict with counts.
    """
    from butler.ops.eval_bridge import (
        create_dataset,
        push_dataset_items,
    )

    catalog_dir = catalog_dir or WECHAT_CATALOG_DIR
    summary: dict[str, Any] = {
        "single_turn_items": 0,
        "multi_turn_items": 0,
        "datasets_created": [],
        "push_reports": [],
    }

    single_items: list[dict[str, Any]] = []
    multi_items: list[dict[str, Any]] = []

    utterance_catalog = catalog_dir / "utterance_catalog.yaml"
    if utterance_catalog.exists():
        single_items.extend(parse_utterance_catalog(utterance_catalog))

    production_catalog = catalog_dir / "production_utterance_catalog.yaml"
    if production_catalog.exists():
        single_items.extend(parse_utterance_catalog(production_catalog))

    reference_catalog = catalog_dir / "reference_utterance_catalog.yaml"
    if reference_catalog.exists():
        single_items.extend(parse_utterance_catalog(reference_catalog))

    multiturn_catalog = catalog_dir / "utterance_multiturn_catalog.yaml"
    if multiturn_catalog.exists():
        multi_items.extend(parse_multiturn_catalog(multiturn_catalog))

    summary["single_turn_items"] = len(single_items)
    summary["multi_turn_items"] = len(multi_items)

    if single_items:
        ds_id = create_dataset(DATASET_NAME_SINGLE, "WeChat single-turn utterance catalog")
        if ds_id:
            summary["datasets_created"].append(DATASET_NAME_SINGLE)
        ds_items = catalog_to_dataset_items(single_items)
        report = push_dataset_items(DATASET_NAME_SINGLE, ds_items)
        summary["push_reports"].append(report.summary())

    if multi_items:
        ds_id = create_dataset(DATASET_NAME_MULTI, "WeChat multi-turn conversation scenarios")
        if ds_id:
            summary["datasets_created"].append(DATASET_NAME_MULTI)
        ds_items = catalog_to_dataset_items(multi_items)
        report = push_dataset_items(DATASET_NAME_MULTI, ds_items)
        summary["push_reports"].append(report.summary())

    return summary
