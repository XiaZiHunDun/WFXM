"""WeChat corpus eval best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any, cast

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def catalog_delegate_stats_safe() -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        from tests.corpus.harness.gateway_catalog import load_utterance_catalog

        rows = load_utterance_catalog(include_smoke_reference=False)
        delegate_rows = [
            row for row in rows if (row.get("expect") or {}).get("uses_delegate")
        ]
        return {
            "catalog_total": len(rows),
            "delegate_entries": len(delegate_rows),
            "delegate_ratio": round(len(delegate_rows) / max(1, len(rows)), 4),
        }

    result = safe_best_effort(
        _run,
        label="wechat_corpus_eval.catalog_stats",
        default={},
    )
    return result if isinstance(result, dict) else {}


def parametrized_catalog_count_safe() -> int:
    def _run() -> int:
        from tests.corpus.harness.gateway_catalog import parametrized_catalog_ids

        return len(parametrized_catalog_ids())

    result = safe_best_effort(
        _run,
        label="wechat_corpus_eval.catalog_ids",
        default=0,
    )
    return int(result or 0)


def push_wechat_corpus_scores_safe(summary: dict[str, Any]) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        from butler.ops.wechat_corpus_eval import push_wechat_corpus_scores

        return cast(dict[str, Any], push_wechat_corpus_scores(summary))

    result = safe_best_effort(
        _run,
        label="wechat_corpus_eval.push_scores",
        default=None,
    )
    return result if isinstance(result, dict) else {}
