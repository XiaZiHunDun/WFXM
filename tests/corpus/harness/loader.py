"""Load and validate corpus YAML suites."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_ANY_KEY = re.compile(r"^must_contain_any(\d*)$")


def load_corpus(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"corpus root must be a mapping: {path}")
    return data


def resolve_corpus_path(registry_entry: dict[str, Any], corpus_root: Path) -> Path:
    rel = registry_entry["corpus_path"]
    if registry_entry.get("legacy"):
        return (corpus_root / rel).resolve()
    return (corpus_root / rel).resolve()


def validate_gateway_corpus(corpus: dict[str, Any]) -> list[str]:
    """Validate wechat/gateway scripted scenario YAML."""
    errors: list[str] = []
    meta = corpus.get("meta") or {}
    if not meta.get("version"):
        errors.append("meta.version is required")
    scenarios: list[dict[str, Any]] = []
    for key in ("lingwen_real_dialogue", "general_dev_habits", "scenarios", "cases"):
        block = corpus.get(key)
        if isinstance(block, list):
            scenarios.extend(block)
    catalog = corpus.get("utterance_catalog") or []
    if not scenarios and not catalog:
        errors.append(
            "gateway corpus needs lingwen_real_dialogue/scenarios/cases or utterance_catalog"
        )
    for row in catalog:
        cid = row.get("id")
        if not cid:
            errors.append("utterance_catalog entry missing id")
            continue
        if not row.get("user"):
            errors.append(f"{cid}: utterance_catalog missing user")
        if row.get("runner") == "legacy":
            if not row.get("pytest"):
                errors.append(f"{cid}: legacy catalog entry missing pytest")
        elif row.get("kind") != "multi" and not row.get("kind"):
            errors.append(f"{cid}: utterance_catalog missing kind")
    seen: set[str] = set()
    for sc in scenarios:
        sid = sc.get("id")
        if not sid:
            errors.append("scenario missing id")
            continue
        if sid in seen:
            errors.append(f"duplicate scenario id: {sid}")
        seen.add(sid)
        if not sc.get("user") and not sc.get("pytest"):
            errors.append(f"{sid}: missing user or pytest reference")
    return errors


def validate_corpus_schema(
    corpus: dict[str, Any],
    *,
    channel: str = "agent_loop",
) -> list[str]:
    """Return human-readable validation errors (empty if ok)."""
    if channel == "gateway_wechat":
        return validate_gateway_corpus(corpus)
    errors: list[str] = []
    meta = corpus.get("meta") or {}
    if not meta.get("version"):
        errors.append("meta.version is required")
    cases = corpus.get("cases") or []
    if not cases:
        errors.append("cases must be non-empty")
    seen: set[str] = set()
    dims = set(meta.get("dimensions") or [])
    for case in cases:
        cid = case.get("id")
        if not cid:
            errors.append("case missing id")
            continue
        if cid in seen:
            errors.append(f"duplicate case id: {cid}")
        seen.add(cid)
        dim = case.get("dimension")
        if dim and dims and dim not in dims:
            errors.append(f"{cid}: dimension {dim!r} not in meta.dimensions")
        turns = case.get("turns")
        user = case.get("user")
        if turns:
            if user:
                errors.append(f"{cid}: multi-turn must not have top-level user")
            if len(turns) < 2:
                errors.append(f"{cid}: multi-turn needs at least 2 turns")
            for i, turn in enumerate(turns):
                if not turn.get("user"):
                    errors.append(f"{cid} turn {i}: missing user")
        elif not user:
            errors.append(f"{cid}: single-turn missing user")
        _validate_rubric_keys(case, cid, errors)
        if turns:
            for i, turn in enumerate(turns):
                _validate_rubric_keys(turn, f"{cid} turn {i}", errors)
    smoke = corpus.get("live_smoke_ids") or []
    for sid in smoke:
        if sid not in seen:
            errors.append(f"live_smoke_ids references unknown id: {sid}")
    return errors


def _validate_rubric_keys(rules: dict[str, Any], label: str, errors: list[str]) -> None:
    for k in rules:
        if k.startswith("must_contain_any") and not _ANY_KEY.match(k):
            errors.append(f"{label}: invalid rubric key {k!r}")
    for k, v in rules.items():
        if k.startswith("must_contain_any") and v is not None and not isinstance(v, list):
            errors.append(f"{label}: {k} must be a list")
