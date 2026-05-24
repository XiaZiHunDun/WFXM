"""Shared intent taxonomy — AgentLoop ↔ Gateway crosswalk."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from tests.corpus.harness.gateway_catalog import (
    _is_executable_row,
    load_utterance_catalog,
    parametrized_multiturn_ids,
)
from tests.corpus.harness.gateway_meta import category_to_dimension
from tests.corpus.harness.loader import load_corpus
from tests.corpus.harness.registry import agent_loop_suite_ids, corpus_root, get_suite, load_suite_corpus

_CROSSWALK_PATH = corpus_root() / "intent_crosswalk.yaml"

CANONICAL_INTENTS = (
    "clarify",
    "delegate",
    "detail",
    "switch",
    "safety",
    "readonly",
    "memory",
    "workflow",
    "identity",
    "recap",
    "off_topic",
    "emotion",
    "multiturn",
    "debug",
)

# PR / 问题地图：两侧至少应覆盖的意图
P0_CROSS_CHANNEL_INTENTS = ("clarify", "delegate", "detail", "switch", "safety")


def load_crosswalk() -> dict[str, Any]:
    if not _CROSSWALK_PATH.is_file():
        return {}
    return yaml.safe_load(_CROSSWALK_PATH.read_text(encoding="utf-8")) or {}


def gateway_category_to_intent(category: str | None, *, kind: str | None = None) -> str:
    cat = (category or "").lower()
    if not cat:
        return "delegate" if kind == "llm" else "switch"

    if cat == "delegate_test":
        return "delegate"
    if cat in ("clarify_first", "plan_only"):
        return "clarify"
    if cat.startswith("detail") or cat in ("brief_reply", "detail_alias", "detail_alias_plain"):
        return "detail"
    if cat.startswith("session") or "switch" in cat or "project_status" in cat or cat.startswith("slash_"):
        return "switch"
    if cat.startswith("safety") or cat == "path_traversal":
        return "safety"
    if cat.startswith("read") or cat.endswith("_readonly") or cat == "read_only":
        return "readonly"
    if "memory" in cat:
        return "memory"
    if "workflow" in cat or "runtime" in cat or "schedule" in cat or cat == "novel_factory":
        return "workflow"
    if cat in ("capabilities", "capabilities_long", "greeting", "identity"):
        return "identity"
    if cat == "recap" or "continue" in cat:
        return "recap"
    if cat == "off_topic":
        return "off_topic"
    if "delegate" in cat or cat.startswith("c_") or cat == "production_real":
        return "delegate"
    if "diagnose" in cat or "health" in cat or cat == "error" or cat.startswith("debug"):
        return "debug"
    if "harness_plan" in cat or cat == "plan_mode":
        return "readonly"

    dim = category_to_dimension(category)
    if dim:
        dim_map = {
            "A_project_session": "switch",
            "B_readonly": "readonly",
            "C_delegate_file": "delegate",
            "D_detail_report": "detail",
            "E_memory_ops": "memory",
            "F_workflow_schedule": "workflow",
            "G_safety_boundary": "safety",
            "H_ability_identity": "identity",
            "K_emotion_urgency": "emotion",
            "V_off_topic": "off_topic",
            "T_debugging": "debug",
            "production_real": "delegate",
        }
        if dim in dim_map:
            return dim_map[dim]
    return "delegate"


def gateway_entry_intent(entry: dict[str, Any]) -> str:
    script = str(entry.get("script") or "")
    if script == "plan_only":
        return "clarify"
    user = str(entry.get("user") or "")
    if "别写代码" in user or "先给方案" in user or "先别" in user:
        return "clarify"
    return gateway_category_to_intent(
        str(entry.get("category") or ""),
        kind=entry.get("kind"),
    )


def infer_agent_loop_intent(case: dict[str, Any]) -> str:
    tags = case.get("tags") or {}
    explicit = tags.get("intent")
    if explicit in CANONICAL_INTENTS:
        return str(explicit)

    dim = str(case.get("dimension") or "")
    user = str(case.get("user") or "").lower()
    title = str(case.get("title") or "").lower()
    rubric_bits: list[str] = []
    for key, val in case.items():
        if key.startswith("must_contain") and val:
            if isinstance(val, list):
                rubric_bits.extend(str(x) for x in val)
            else:
                rubric_bits.append(str(val))
    blob = f"{title} {user} {' '.join(rubric_bits).lower()}"

    if dim == "safety_bounds" or any(w in blob for w in ("违法", "删库", "rm -rf", "注入")):
        return "safety"
    if dim == "multi_turn" or case.get("turns"):
        return "multiturn"
    if "委派" in blob or "delegate" in blob:
        if any(w in blob for w in ("进度", "怎么样", "怎么问")) and not any(
            w in blob for w in ("新建", "创建", "写", "改", "删", "文件", "notes")
        ):
            return "detail"
        return "delegate"
    if any(w in blob for w in ("详细", "细节", "摘要", "进度", "状态")):
        return "detail"
    if dim == "conversational" or any(
        w in blob for w in ("别写代码", "先别", "思路", "步骤", "理一下", "不要代码", "清单")
    ):
        return "clarify"
    if dim == "product_butler":
        return "identity"
    if dim in ("incident_ops", "observability"):
        return "debug"
    if any(w in blob for w in ("切换", "项目", "会话")):
        return "switch"
    if any(w in blob for w in ("读", "read", "查看", "列出", "目录")):
        return "readonly"
    return "clarify"


def iter_agent_loop_cases() -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for suite_id in agent_loop_suite_ids():
        corpus, _ = load_suite_corpus(get_suite(suite_id))
        for case in corpus.get("cases") or []:
            cid = case.get("id")
            if cid:
                rows.append((f"{suite_id}::{cid}", case))
    return rows


def iter_gateway_catalog_entries() -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for entry in load_utterance_catalog():
        if _is_executable_row(entry):
            rows.append((str(entry["id"]), entry))
    for mt_id in parametrized_multiturn_ids():
        rows.append((mt_id, {"id": mt_id, "category": "multiturn", "kind": "multi"}))
    return rows


def build_crosswalk(*, max_per_side: int = 12) -> dict[str, Any]:
    by_intent: dict[str, dict[str, list[str]]] = {
        intent: {"agent_loop": [], "gateway": []} for intent in CANONICAL_INTENTS
    }

    for ref, case in iter_agent_loop_cases():
        intent = infer_agent_loop_intent(case)
        bucket = by_intent.setdefault(intent, {"agent_loop": [], "gateway": []})
        if len(bucket["agent_loop"]) < max_per_side:
            bucket["agent_loop"].append(ref)

    for cid, entry in iter_gateway_catalog_entries():
        if entry.get("kind") == "multi":
            intent = "multiturn"
        else:
            intent = gateway_entry_intent(entry)
        bucket = by_intent.setdefault(intent, {"agent_loop": [], "gateway": []})
        if len(bucket["gateway"]) < max_per_side:
            bucket["gateway"].append(cid)

    cross_refs = []
    for intent in CANONICAL_INTENTS:
        sides = by_intent.get(intent) or {"agent_loop": [], "gateway": []}
        if not sides["agent_loop"] and not sides["gateway"]:
            continue
        cross_refs.append(
            {
                "intent": intent,
                "agent_loop": sides["agent_loop"],
                "gateway": sides["gateway"],
            }
        )

    return {
        "meta": {
            "version": "2026-05-24-intent-r1",
            "schema": "schemas/corpus-intent-v1.md",
            "p0_intents": list(P0_CROSS_CHANNEL_INTENTS),
        },
        "cross_refs": cross_refs,
    }


def validate_crosswalk(doc: dict[str, Any] | None = None) -> list[str]:
    doc = doc or load_crosswalk()
    errors: list[str] = []
    if not doc.get("cross_refs"):
        errors.append("intent_crosswalk.yaml: empty cross_refs")
        return errors

    seen_intents: set[str] = set()
    for row in doc.get("cross_refs") or []:
        intent = row.get("intent")
        if intent not in CANONICAL_INTENTS:
            errors.append(f"unknown intent: {intent!r}")
        seen_intents.add(str(intent))
        al = row.get("agent_loop") or []
        gw = row.get("gateway") or []
        if not al and not gw:
            errors.append(f"{intent}: empty both sides")

    for intent in P0_CROSS_CHANNEL_INTENTS:
        row = next((r for r in doc.get("cross_refs") or [] if r.get("intent") == intent), None)
        if not row:
            errors.append(f"P0 intent missing from crosswalk: {intent}")
            continue
        if len(row.get("agent_loop") or []) < 1:
            errors.append(f"P0 {intent}: need >=1 agent_loop ref")
        if len(row.get("gateway") or []) < 2:
            errors.append(f"P0 {intent}: need >=2 gateway refs")

    # Verify referenced ids exist
    al_ids = {r[0] for r in iter_agent_loop_cases()}
    gw_ids = {r[0] for r in iter_gateway_catalog_entries()}
    for row in doc.get("cross_refs") or []:
        for ref in row.get("agent_loop") or []:
            if ref not in al_ids:
                errors.append(f"{row.get('intent')}: unknown agent_loop ref {ref}")
        for cid in row.get("gateway") or []:
            if cid not in gw_ids:
                errors.append(f"{row.get('intent')}: unknown gateway id {cid}")

    return errors


def touch_paths_for_unified_gate() -> list[str]:
    """Paths that should trigger full corpus mock when changed in a PR."""
    return [
        "butler/gateway/message_handler.py",
        "butler/gateway/",
        "tests/corpus/",
        "tests/test_gateway_dev_conversations.py",
    ]
