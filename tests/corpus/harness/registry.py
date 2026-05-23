"""Load corpus suite entries from registry.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from tests.corpus.harness.loader import load_corpus, resolve_corpus_path

_CORPUS_ROOT = Path(__file__).resolve().parents[1]
_REGISTRY_PATH = _CORPUS_ROOT / "registry.yaml"


def corpus_root() -> Path:
    return _CORPUS_ROOT


def load_registry() -> dict[str, Any]:
    with _REGISTRY_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def iter_suites(*, runner: str | None = None) -> list[dict[str, Any]]:
    reg = load_registry()
    suites = reg.get("suites") or []
    if runner:
        return [e for e in suites if e.get("runner") == runner]
    return list(suites)


def get_suite(suite_id: str) -> dict[str, Any]:
    for entry in iter_suites():
        if entry.get("suite_id") == suite_id:
            return entry
    raise KeyError(f"unknown suite_id: {suite_id}")


def load_suite_corpus(entry: dict[str, Any]) -> tuple[dict[str, Any], Path]:
    path = resolve_corpus_path(entry, _CORPUS_ROOT)
    return load_corpus(path), path


def agent_loop_suite_ids() -> list[str]:
    return [e["suite_id"] for e in iter_suites(runner="agent_loop_rubric")]


def live_smoke_ids(corpus: dict[str, Any]) -> list[str]:
    return list(corpus.get("live_smoke_ids") or [])
