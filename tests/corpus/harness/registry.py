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
    if not runner:
        return list(suites)

    def _matches(entry: dict[str, Any]) -> bool:
        if entry.get("runner") == runner:
            return True
        roles = entry.get("runner_roles") or {}
        if runner in roles.values():
            return True
        return runner == "gateway_wechat" and entry.get("channel") == "gateway_wechat"

    return [e for e in suites if _matches(e)]


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


def gateway_runner_modules(entry: dict[str, Any] | None = None) -> list[str]:
    """Pytest modules for wechat_real.lw_real (paths relative to tests/corpus or repo tests/)."""
    if entry is None:
        entry = get_suite("wechat_real.lw_real")
    return list(entry.get("runner_modules") or [])


def resolve_runner_module_path(module: str, *, corpus_root_path: Path | None = None) -> Path:
    """Resolve runner module path to filesystem path for pytest."""
    root = corpus_root_path or corpus_root()
    if module.startswith("tests/"):
        return root.parent / module[len("tests/") :]
    return root / module
