"""MetaGPT / workflow feature flags (PR-X5 / PR-X6)."""

from __future__ import annotations

import os

from butler.defaults.env_defaults import (
    WORKFLOW_MAX_DAG_NODES,
    WORKFLOW_MAX_DAG_PARALLEL,
)
from butler.env_parse import env_truthy

MAX_DAG_NODES = WORKFLOW_MAX_DAG_NODES
MAX_DAG_PARALLEL = WORKFLOW_MAX_DAG_PARALLEL


def exp_cache_enabled() -> bool:
    return env_truthy("BUTLER_EXP_CACHE", default=False)


def tool_recall_bm25_enabled() -> bool:
    return env_truthy("BUTLER_TOOL_RECALL_BM25", default=False)


def workflow_checkpoint_enabled() -> bool:
    return env_truthy("BUTLER_WORKFLOW_CHECKPOINT", default=True)


def output_schema_validate_enabled() -> bool:
    return env_truthy("BUTLER_OUTPUT_SCHEMA_VALIDATE", default=True)


def workflow_max_parallel_default() -> int | None:
    raw = os.getenv("BUTLER_WORKFLOW_MAX_PARALLEL", "").strip()
    if not raw:
        return MAX_DAG_PARALLEL
    try:
        return max(1, min(MAX_DAG_PARALLEL, int(raw)))
    except ValueError:
        return MAX_DAG_PARALLEL


__all__ = [
    "exp_cache_enabled",
    "output_schema_validate_enabled",
    "tool_recall_bm25_enabled",
    "workflow_checkpoint_enabled",
    "workflow_max_parallel_default",
]
