"""Load wechat_real.lw_real meta.yaml and validate tier counts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from tests.corpus.harness.gateway_catalog import (
    _LW_REAL_DIR,
    _is_executable_row,
    load_main_utterance_catalog,
    load_multiturn_catalog,
    load_production_strict_catalog,
    load_reference_smoke_catalog,
    load_reference_strict_catalog,
    load_utterance_catalog,
    parametrized_catalog_ids,
    parametrized_multiturn_ids,
)

# Multiturn chain → coverage_matrix dimension keys (phase 2)
MULTITURN_DIMENSION_TAGS: dict[str, list[str]] = {
    "MT-01": ["A_project_session"],
    "MT-02": ["C_delegate_file", "D_detail_report"],
    "MT-03": ["D_detail_report"],
    "MT-04": ["A_project_session"],
    "MT-05": ["D_detail_report"],
    "MT-06": ["D_detail_report"],
    "MT-07": ["C_delegate_file"],
    "MT-08": ["G_safety_boundary"],
    "MT-09": ["T_debugging"],
    "MT-10": ["C_delegate_file"],
    "MT-11": ["L_cross_project"],
    "MT-12": ["J_multiturn", "C_delegate_file"],
    "MT-13": ["C_delegate_file", "D_detail_report"],
    "MT-14": ["J_multiturn"],
    "MT-15": ["D_detail_report", "P_wechat_specific"],
    "MT-16": ["L_cross_project"],
    "MT-17": ["C_delegate_file", "D_detail_report", "T_debugging"],
    "MT-18": ["A_project_session"],
    "MT-19": ["B_readonly", "C_delegate_file", "D_detail_report"],
    "MT-20": ["G_safety_boundary", "B_readonly"],
}

# Handbook `category` → coverage_matrix key
HANDBOOK_CATEGORY_TO_DIMENSION: dict[str, str] = {
    "session_reset": "A_project_session",
    "project_switch": "A_project_session",
    "project_status": "A_project_session",
    "recap": "C_delegate_file",
    "brief_reply": "D_detail_report",
    "delegate_test": "C_delegate_file",
    "clarify_first": "C_delegate_file",
    "read_only": "B_readonly",
    "detail_alias": "D_detail_report",
    "delegate_write": "C_delegate_file",
    "delegate_delete": "C_delegate_file",
    "safety": "G_safety_boundary",
    "off_topic": "V_off_topic",
    "memory": "E_memory_ops",
    "workflow": "F_workflow_schedule",
    "schedule": "N_schedule_ops",
    "identity": "H_ability_identity",
    "novel_factory": "I_novel_factory",
    "cross_project": "L_cross_project",
    "failure": "C_delegate_file",
    "compliance": "U_compliance",
    "wechat": "P_wechat_specific",
}

_META_PATH = _LW_REAL_DIR / "meta.yaml"


def load_gateway_meta() -> dict[str, Any]:
    if not _META_PATH.is_file():
        return {}
    return yaml.safe_load(_META_PATH.read_text(encoding="utf-8")) or {}


def actual_tier_counts() -> dict[str, int]:
    strict = [
        *load_main_utterance_catalog(),
        *load_reference_strict_catalog(),
        *load_production_strict_catalog(),
    ]
    ga = sum(1 for r in strict if r.get("script") == "generic_ack")
    return {
        "l0_smoke": len(load_reference_smoke_catalog()),
        "l1_strict_single": len(parametrized_catalog_ids()),
        "l1_multiturn_chains": len(parametrized_multiturn_ids()),
        "l1_multiturn_turns": sum(
            len(c.get("turns") or []) for c in load_multiturn_catalog()
        ),
        "strict_generic_ack": ga,
        "handbook": len(load_main_utterance_catalog()),
        "reference_strict": len(load_reference_strict_catalog()),
        "production": len(load_production_strict_catalog()),
    }


def validate_meta_targets(meta: dict[str, Any] | None = None) -> list[str]:
    """Return list of validation error messages (empty if ok)."""
    meta = meta or load_gateway_meta()
    targets = meta.get("targets") or {}
    actual = actual_tier_counts()
    errors: list[str] = []

    for key, minimum in targets.items():
        if key not in actual:
            continue
        if actual[key] < int(minimum):
            errors.append(f"{key}: need >={minimum}, got {actual[key]}")

    max_ga = targets.get("strict_generic_ack_max")
    if max_ga is not None and actual["strict_generic_ack"] > int(max_ga):
        errors.append(
            f"strict_generic_ack: max {max_ga}, got {actual['strict_generic_ack']}"
        )
    return errors


def category_to_dimension(category: str | None) -> str | None:
    if not category:
        return None
    if category == "production_real":
        return "production_real"
    if category in HANDBOOK_CATEGORY_TO_DIMENSION:
        return HANDBOOK_CATEGORY_TO_DIMENSION[category]
    letter = category[0].upper()
    prefix_map = {
        "A": "A_project_session",
        "B": "B_readonly",
        "C": "C_delegate_file",
        "D": "D_detail_report",
        "E": "E_memory_ops",
        "F": "F_workflow_schedule",
        "G": "G_safety_boundary",
        "H": "H_ability_identity",
        "I": "I_novel_factory",
        "J": "J_multiturn",
        "K": "K_emotion_urgency",
        "L": "L_cross_project",
        "N": "N_schedule_ops",
        "O": "O_memory_conflict",
        "P": "P_wechat_specific",
        "Q": "Q_role_misunderstanding",
        "R": "R_batch_file_ops",
        "S": "S_reporting",
        "T": "T_debugging",
        "U": "U_compliance",
        "V": "V_off_topic",
    }
    return prefix_map.get(letter)


def coverage_counts_by_dimension() -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for row in load_utterance_catalog():
        if not _is_executable_row(row):
            continue
        dim = category_to_dimension(str(row.get("category") or ""))
        if not dim:
            continue
        bucket = counts.setdefault(dim, {"strict": 0, "multiturn": 0})
        bucket["strict"] += 1

    for chain in load_multiturn_catalog():
        for dim in MULTITURN_DIMENSION_TAGS.get(str(chain.get("id")), []):
            bucket = counts.setdefault(dim, {"strict": 0, "multiturn": 0})
            bucket["multiturn"] += 1
    return counts


def validate_coverage_matrix(meta: dict[str, Any] | None = None) -> list[str]:
    meta = meta or load_gateway_meta()
    matrix = meta.get("coverage_matrix") or {}
    targets = meta.get("targets") or {}
    min_strict = int(targets.get("coverage_min_strict_per_dim", 2))
    counts = coverage_counts_by_dimension()
    errors: list[str] = []

    for dim, spec in matrix.items():
        if not spec.get("strict"):
            continue
        c = counts.get(dim, {"strict": 0, "multiturn": 0})
        if c["strict"] >= min_strict:
            continue
        if spec.get("multiturn") and c["multiturn"] >= 1:
            continue
        errors.append(
            f"{dim}: need >={min_strict} strict or >=1 multiturn, "
            f"got strict={c['strict']} multiturn={c['multiturn']}"
        )
    return errors


def long_multiturn_chain_count(*, min_turns: int = 5) -> int:
    return sum(
        1
        for c in load_multiturn_catalog()
        if len(c.get("turns") or []) >= min_turns
    )


def variant_sample_entries(*, max_cases: int | None = None) -> list[dict[str, Any]]:
    """One variant per parent entry (deterministic), capped for CI."""
    meta = load_gateway_meta()
    cap = max_cases
    if cap is None:
        cap = int((meta.get("targets") or {}).get("variants_sample_max", 40))

    parents: list[dict[str, Any]] = []
    for row in load_utterance_catalog():
        if not _is_executable_row(row):
            continue
        # Command/detail 依赖精确话术路由；变体只抽检 llm 类口语改写
        if row.get("kind") not in ("llm", None):
            continue
        variants = row.get("variants") or []
        if not variants:
            continue
        parents.append(row)

    parents.sort(key=lambda r: str(r.get("id", "")))
    samples: list[dict[str, Any]] = []
    for parent in parents[:cap]:
        variants = parent.get("variants") or []
        idx = abs(hash(parent["id"])) % len(variants)
        child = dict(parent)
        child["user"] = variants[idx]
        child["id"] = f"{parent['id']}::var{idx}"
        child["_variant_parent_id"] = parent["id"]
        child["_variant_index"] = idx
        samples.append(child)
    return samples


def variant_sample_ids(*, max_cases: int | None = None) -> list[str]:
    return [e["id"] for e in variant_sample_entries(max_cases=max_cases)]
