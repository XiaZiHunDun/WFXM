"""Evaluation bridge — push benchmark results to LangFuse as Scores/Datasets.

Bridges the gap between pytest-based correctness testing and LangFuse-based
quality observability. Consumes results from:
  - dev_benchmark (B1-B7)
  - memory_benchmark (MB1-MB7)
  - memory_metrics (S_w/H_1/E_d)
  - corpus test runs

and uploads them as LangFuse evaluation scores / dataset items.

Zero-cost when LangFuse is disabled.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class EvalScore:
    """A single evaluation score to push to LangFuse."""

    name: str
    value: float
    comment: str = ""
    category: str = ""
    trace_id: str = ""
    observation_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class DatasetItem:
    """A dataset item for LangFuse evaluation datasets."""

    input: dict[str, Any] = field(default_factory=dict)
    expected_output: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    source_id: str = ""


@dataclass
class EvalReport:
    """Summary of an evaluation push batch."""

    scores_pushed: int = 0
    scores_failed: int = 0
    dataset_items_pushed: int = 0
    errors: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def summary(self) -> dict[str, Any]:
        return {
            "scores_pushed": self.scores_pushed,
            "scores_failed": self.scores_failed,
            "dataset_items_pushed": self.dataset_items_pushed,
            "errors": self.errors[:10],
            "timestamp": self.timestamp,
        }


def _get_langfuse_client() -> Any:
    """Get LangFuse client, returns None if disabled."""
    try:
        from butler.ops.langfuse_tracer import _get_client
        return _get_client()
    except Exception:
        return None


def push_score(score: EvalScore) -> bool:
    """Push a single evaluation score to LangFuse.

    Returns True if successful, False otherwise.
    """
    client = _get_langfuse_client()
    if client is None:
        logger.debug("LangFuse disabled; score '%s' not pushed", score.name)
        return False

    try:
        kwargs: dict[str, Any] = {
            "name": score.name,
            "value": score.value,
        }
        if score.comment:
            kwargs["comment"] = score.comment
        if score.trace_id:
            kwargs["trace_id"] = score.trace_id
        if score.observation_id:
            kwargs["observation_id"] = score.observation_id

        client.score(**kwargs)
        logger.debug("Pushed score: %s = %.4f", score.name, score.value)
        return True
    except Exception as exc:
        logger.warning("Failed to push score '%s': %s", score.name, exc)
        return False


def push_scores(scores: list[EvalScore]) -> EvalReport:
    """Push a batch of evaluation scores."""
    report = EvalReport()
    for s in scores:
        if push_score(s):
            report.scores_pushed += 1
        else:
            report.scores_failed += 1
            report.errors.append(f"Failed: {s.name}")

    client = _get_langfuse_client()
    if client is not None:
        try:
            client.flush()
        except Exception:
            pass

    return report


def create_dataset(name: str, description: str = "") -> Optional[str]:
    """Create a LangFuse dataset. Returns dataset ID or None."""
    client = _get_langfuse_client()
    if client is None:
        return None
    try:
        ds = client.create_dataset(name=name, description=description)
        return str(getattr(ds, "id", name))
    except Exception as exc:
        logger.warning("Failed to create dataset '%s': %s", name, exc)
        return None


def push_dataset_item(
    dataset_name: str,
    item: DatasetItem,
) -> bool:
    """Push a single item to a LangFuse dataset."""
    client = _get_langfuse_client()
    if client is None:
        return False
    try:
        client.create_dataset_item(
            dataset_name=dataset_name,
            input=item.input,
            expected_output=item.expected_output,
            metadata=item.metadata,
            source_trace_id=item.source_id if item.source_id else None,
        )
        return True
    except Exception as exc:
        logger.warning("Failed to push dataset item: %s", exc)
        return False


def push_dataset_items(
    dataset_name: str,
    items: list[DatasetItem],
) -> EvalReport:
    """Push a batch of items to a LangFuse dataset."""
    report = EvalReport()
    for item in items:
        if push_dataset_item(dataset_name, item):
            report.dataset_items_pushed += 1
        else:
            report.errors.append(f"Failed item: {item.source_id or 'unknown'}")

    client = _get_langfuse_client()
    if client is not None:
        try:
            client.flush()
        except Exception:
            pass
    return report


# ── Converters: benchmark → EvalScore ──


def dev_benchmark_to_scores(report: Any) -> list[EvalScore]:
    """Convert a DevEngine BenchmarkReport to EvalScores.

    Args:
        report: butler.dev_engine.dev_benchmark.BenchmarkReport
    """
    scores: list[EvalScore] = []

    scores.append(EvalScore(
        name="dev_benchmark.pass_rate",
        value=report.passed / max(1, report.total),
        comment=f"{report.passed}/{report.total} passed",
        category="dev_benchmark",
    ))

    for r in getattr(report, "results", []):
        task_id = getattr(r, "task_id", getattr(r, "benchmark_id", "unknown"))
        score_val = getattr(r, "score", 1.0 if r.passed else 0.0)
        error_text = getattr(r, "error", "")
        failure_reasons = getattr(r, "failure_reasons", [])
        comment = error_text or ("; ".join(failure_reasons) if failure_reasons else
                                 ("passed" if r.passed else "failed"))
        elapsed = getattr(r, "elapsed_ms", getattr(r, "elapsed_seconds", 0))
        scores.append(EvalScore(
            name=f"dev_benchmark.{task_id}",
            value=float(score_val),
            comment=comment,
            category=r.category.value if hasattr(r.category, "value") else str(r.category),
            metadata={
                "elapsed": elapsed,
                "details": getattr(r, "details", {}),
            },
        ))

    return scores


def llm_benchmark_to_scores(report: Any) -> list[EvalScore]:
    """Convert B9 LLM delegate benchmark report to EvalScores."""
    scores: list[EvalScore] = []
    total = getattr(report, "total", 0)
    passed = getattr(report, "passed", 0)
    scores.append(EvalScore(
        name="llm_benchmark.pass_rate",
        value=passed / max(1, total),
        comment=f"{passed}/{total} passed mode={getattr(report, 'mode', 'oracle')}",
        category="llm_benchmark",
    ))
    for r in getattr(report, "results", []):
        task_id = getattr(r, "task_id", "unknown")
        scores.append(EvalScore(
            name=f"llm_benchmark.{task_id}",
            value=float(getattr(r, "score", 1.0 if r.passed else 0.0)),
            comment="; ".join(getattr(r, "failure_reasons", [])[:2]) or (
                "passed" if r.passed else "failed"
            ),
            category="llm_benchmark",
            metadata={"mode": getattr(r, "mode", ""), "tools": getattr(r, "tools_used", [])},
        ))
    return scores


def memory_benchmark_to_scores(report: Any) -> list[EvalScore]:
    """Convert a Memory BenchmarkReport to EvalScores.

    Args:
        report: butler.memory.memory_benchmark.BenchmarkReport
    """
    scores: list[EvalScore] = []

    scores.append(EvalScore(
        name="memory_benchmark.pass_rate",
        value=report.passed / max(1, report.total),
        comment=f"{report.passed}/{report.total} passed",
        category="memory_benchmark",
    ))

    for r in getattr(report, "results", []):
        scores.append(EvalScore(
            name=f"memory_benchmark.{r.benchmark_id}",
            value=r.score,
            comment=r.error or ("passed" if r.passed else "failed"),
            category=r.category.value if hasattr(r.category, "value") else str(r.category),
            metadata={
                "elapsed_ms": getattr(r, "elapsed_ms", 0),
                "details": getattr(r, "details", {}),
            },
        ))

    return scores


def memory_metrics_to_scores(metrics: Any) -> list[EvalScore]:
    """Convert SessionMemoryMetrics to EvalScores.

    Args:
        metrics: butler.memory.memory_metrics.SessionMemoryMetrics
    """
    scores: list[EvalScore] = []

    s_w = metrics.writes_successful / max(1, metrics.writes)
    h_1 = metrics.prefetch_hits / max(1, metrics.prefetch_turns)
    e_d = metrics.decay_false_kills / max(1, metrics.decay_evaluations)

    scores.append(EvalScore(
        name="memory.write_survival_rate",
        value=round(s_w, 4),
        comment=f"S_w = {metrics.writes_successful}/{metrics.writes}",
        category="memory_metrics",
    ))
    scores.append(EvalScore(
        name="memory.first_turn_hit_rate",
        value=round(h_1, 4),
        comment=f"H_1 = {metrics.prefetch_hits}/{metrics.prefetch_turns}",
        category="memory_metrics",
    ))
    scores.append(EvalScore(
        name="memory.decay_error_rate",
        value=round(e_d, 4),
        comment=f"E_d = {metrics.decay_false_kills}/{metrics.decay_evaluations}",
        category="memory_metrics",
    ))

    return scores


def corpus_run_to_scores(
    corpus_name: str,
    total: int,
    passed: int,
    intent_accuracy: float = 0.0,
    tool_accuracy: float = 0.0,
    avg_latency_ms: float = 0.0,
) -> list[EvalScore]:
    """Convert corpus test run results to EvalScores."""
    scores: list[EvalScore] = []

    scores.append(EvalScore(
        name=f"corpus.{corpus_name}.pass_rate",
        value=passed / max(1, total),
        comment=f"{passed}/{total} passed",
        category=f"corpus_{corpus_name}",
    ))

    if intent_accuracy > 0:
        scores.append(EvalScore(
            name=f"corpus.{corpus_name}.intent_accuracy",
            value=intent_accuracy,
            category=f"corpus_{corpus_name}",
        ))

    if tool_accuracy > 0:
        scores.append(EvalScore(
            name=f"corpus.{corpus_name}.tool_accuracy",
            value=tool_accuracy,
            category=f"corpus_{corpus_name}",
        ))

    if avg_latency_ms > 0:
        scores.append(EvalScore(
            name=f"corpus.{corpus_name}.avg_latency_ms",
            value=avg_latency_ms,
            category=f"corpus_{corpus_name}",
        ))

    return scores
