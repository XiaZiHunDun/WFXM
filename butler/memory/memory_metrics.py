"""Memory effectiveness metrics — runtime measurement of memory capability.

Formal model (v4-memory-theory.md §6):
  Layer 2: Runtime metrics — per-session memory effectiveness tracking
  Layer 3: Comparative benchmarks — standardized memory tasks (MB1-MB7)

Metrics collected:
  - P_r: Retrieval precision (prefetch ∩ LLM_used / prefetch)
  - R_r: Retrieval recall (prefetch ∩ relevant / relevant)
  - S_w: Write survival rate (write → recall success / writes)
  - S_f: Fact survival rate (post-compact facts / pre-compact facts)
  - E_d: Decay false-kill rate (important ∧ rank < θ / important)
  - H_1: First-turn hit rate (turns where prefetch hits relevant)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAX_WRITE_PROBES = 64
_PROBE_MIN_LEN = 8


def _normalize_probe_text(content: str) -> str:
    return " ".join((content or "").strip().lower().split())


def _probe_match_token(content: str) -> str:
    norm = _normalize_probe_text(content)
    if len(norm) < _PROBE_MIN_LEN:
        return ""
    return norm[:80]


@dataclass
class MemoryOpRecord:
    """Single memory operation event."""

    op_type: str  # "write", "recall", "prefetch", "fact_extract", "rerank"
    scope: str = ""
    query: str = ""
    result_count: int = 0
    hit: bool = False
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionMemoryMetrics:
    """Per-session memory effectiveness metrics."""

    session_id: str = ""
    start_time: float = field(default_factory=time.time)

    writes: int = 0
    writes_successful: int = 0
    write_probes: int = 0
    write_probes_recalled: int = 0
    recalls: int = 0
    recalls_with_hits: int = 0

    prefetch_turns: int = 0
    prefetch_hits: int = 0

    facts_pre_compact: int = 0
    facts_post_compact: int = 0

    decay_evaluations: int = 0
    decay_false_kills: int = 0

    retrieval_total: int = 0
    retrieval_relevant: int = 0
    retrieval_used_by_llm: int = 0

    ops: list[MemoryOpRecord] = field(default_factory=list)
    _pending_write_probes: list[dict[str, Any]] = field(default_factory=list)

    @property
    def write_survival_rate(self) -> float:
        """S_w: write probes later matched on recall / total write probes (D2-4)."""
        if self.write_probes > 0:
            return self.write_probes_recalled / self.write_probes
        if self.writes == 0:
            return 1.0
        return self.writes_successful / self.writes

    @property
    def first_turn_hit_rate(self) -> float:
        """H_1: prefetch turns with at least one relevant hit."""
        if self.prefetch_turns == 0:
            return 1.0
        return self.prefetch_hits / self.prefetch_turns

    @property
    def fact_survival_rate(self) -> float:
        """S_f: post-compact facts / pre-compact facts."""
        if self.facts_pre_compact == 0:
            return 1.0
        return self.facts_post_compact / self.facts_pre_compact

    @property
    def decay_error_rate(self) -> float:
        """E_d: important memories killed by decay / evaluated."""
        if self.decay_evaluations == 0:
            return 0.0
        return self.decay_false_kills / self.decay_evaluations

    @property
    def retrieval_precision(self) -> float:
        """P_r: prefetch ∩ LLM_used / prefetch."""
        if self.retrieval_total == 0:
            return 1.0
        return self.retrieval_used_by_llm / self.retrieval_total

    @property
    def retrieval_recall(self) -> float:
        """R_r: prefetch ∩ relevant / relevant."""
        if self.retrieval_relevant == 0:
            return 1.0
        return min(self.retrieval_total, self.retrieval_relevant) / self.retrieval_relevant

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "start_time": self.start_time,
            "writes": self.writes,
            "writes_successful": self.writes_successful,
            "write_probes": self.write_probes,
            "write_probes_recalled": self.write_probes_recalled,
            "recalls": self.recalls,
            "recalls_with_hits": self.recalls_with_hits,
            "prefetch_turns": self.prefetch_turns,
            "prefetch_hits": self.prefetch_hits,
            "facts_pre_compact": self.facts_pre_compact,
            "facts_post_compact": self.facts_post_compact,
            "decay_evaluations": self.decay_evaluations,
            "decay_false_kills": self.decay_false_kills,
            "retrieval_total": self.retrieval_total,
            "retrieval_relevant": self.retrieval_relevant,
            "retrieval_used_by_llm": self.retrieval_used_by_llm,
            "computed": {
                "write_survival_rate": round(self.write_survival_rate, 4),
                "first_turn_hit_rate": round(self.first_turn_hit_rate, 4),
                "fact_survival_rate": round(self.fact_survival_rate, 4),
                "decay_error_rate": round(self.decay_error_rate, 4),
                "retrieval_precision": round(self.retrieval_precision, 4),
                "retrieval_recall": round(self.retrieval_recall, 4),
            },
        }


@dataclass
class AggregateMemoryMetrics:
    """Aggregated metrics across sessions."""

    total_sessions: int = 0
    total_writes: int = 0
    total_writes_successful: int = 0
    total_write_probes: int = 0
    total_write_probes_recalled: int = 0
    total_recalls: int = 0
    total_recalls_with_hits: int = 0
    total_prefetch_turns: int = 0
    total_prefetch_hits: int = 0
    total_facts_pre: int = 0
    total_facts_post: int = 0
    total_decay_evals: int = 0
    total_decay_kills: int = 0

    @property
    def write_survival_rate(self) -> float:
        if self.total_write_probes > 0:
            return self.total_write_probes_recalled / self.total_write_probes
        if self.total_writes == 0:
            return 1.0
        return self.total_writes_successful / self.total_writes

    @property
    def first_turn_hit_rate(self) -> float:
        if self.total_prefetch_turns == 0:
            return 1.0
        return self.total_prefetch_hits / self.total_prefetch_turns

    @property
    def fact_survival_rate(self) -> float:
        if self.total_facts_pre == 0:
            return 1.0
        return self.total_facts_post / self.total_facts_pre

    @property
    def decay_error_rate(self) -> float:
        if self.total_decay_evals == 0:
            return 0.0
        return self.total_decay_kills / self.total_decay_evals

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_sessions": self.total_sessions,
            "total_writes": self.total_writes,
            "total_writes_successful": self.total_writes_successful,
            "total_write_probes": self.total_write_probes,
            "total_write_probes_recalled": self.total_write_probes_recalled,
            "total_recalls": self.total_recalls,
            "total_recalls_with_hits": self.total_recalls_with_hits,
            "total_prefetch_turns": self.total_prefetch_turns,
            "total_prefetch_hits": self.total_prefetch_hits,
            "computed": {
                "write_survival_rate": round(self.write_survival_rate, 4),
                "first_turn_hit_rate": round(self.first_turn_hit_rate, 4),
                "fact_survival_rate": round(self.fact_survival_rate, 4),
                "decay_error_rate": round(self.decay_error_rate, 4),
            },
        }


class MemoryMetricsCollector:
    """Singleton collector for memory effectiveness events."""

    _instance: MemoryMetricsCollector | None = None

    def __init__(self) -> None:
        self._sessions: dict[str, SessionMemoryMetrics] = {}
        self._current_session: str = ""

    @classmethod
    def get_instance(cls) -> MemoryMetricsCollector:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def start_session(self, session_id: str) -> None:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionMemoryMetrics(session_id=session_id)
        self._current_session = session_id

    def _current(self) -> SessionMemoryMetrics | None:
        return self._sessions.get(self._current_session)

    def on_write(self, scope: str, success: bool, *, content: str = "") -> None:
        m = self._current()
        if m is None:
            return
        m.writes += 1
        if success:
            m.writes_successful += 1
            if content:
                self.register_write_probe(content, scope)
        m.ops.append(MemoryOpRecord(
            op_type="write", scope=scope, hit=success,
        ))

    def register_write_probe(self, content: str, scope: str = "") -> None:
        """D2-4: register a write for later recall-survival matching."""
        m = self._current()
        if m is None:
            return
        token = _probe_match_token(content)
        if not token:
            return
        m.write_probes += 1
        m._pending_write_probes.append(
            {"token": token, "scope": scope, "recalled": False}
        )
        if len(m._pending_write_probes) > _MAX_WRITE_PROBES:
            m._pending_write_probes.pop(0)

    def check_recall_survival(self, hit_texts: list[str]) -> int:
        """D2-4: mark write probes recalled when hit texts contain probe token."""
        m = self._current()
        if m is None or not hit_texts:
            return 0
        blob = _normalize_probe_text(" ".join(str(t) for t in hit_texts if t))
        if not blob:
            return 0
        matched = 0
        for probe in m._pending_write_probes:
            if probe.get("recalled"):
                continue
            token = str(probe.get("token") or "")
            if token and token in blob:
                probe["recalled"] = True
                m.write_probes_recalled += 1
                matched += 1
        return matched

    def on_recall(
        self,
        scope: str,
        query: str,
        result_count: int,
        *,
        hit_texts: list[str] | None = None,
    ) -> None:
        m = self._current()
        if m is None:
            return
        m.recalls += 1
        if result_count > 0:
            m.recalls_with_hits += 1
        if hit_texts:
            self.check_recall_survival(hit_texts)
        m.ops.append(MemoryOpRecord(
            op_type="recall", scope=scope, query=query,
            result_count=result_count, hit=result_count > 0,
        ))

    def on_prefetch(self, query: str, hit: bool, result_count: int = 0) -> None:
        m = self._current()
        if m is None:
            return
        m.prefetch_turns += 1
        if hit:
            m.prefetch_hits += 1
        m.ops.append(MemoryOpRecord(
            op_type="prefetch", query=query, result_count=result_count, hit=hit,
        ))

    def on_fact_extraction(self, pre_count: int, post_count: int) -> None:
        m = self._current()
        if m is None:
            return
        m.facts_pre_compact += pre_count
        m.facts_post_compact += post_count
        m.ops.append(MemoryOpRecord(
            op_type="fact_extract",
            metadata={"pre": pre_count, "post": post_count},
        ))

    def on_retrieval(self, total_returned: int, relevant: int = 0, used_by_llm: int = 0) -> None:
        """Track P_r / R_r retrieval precision/recall."""
        m = self._current()
        if m is None:
            return
        m.retrieval_total += total_returned
        m.retrieval_relevant += relevant
        m.retrieval_used_by_llm += used_by_llm
        m.ops.append(MemoryOpRecord(
            op_type="retrieval",
            metadata={"total": total_returned, "relevant": relevant, "used": used_by_llm},
        ))

    def on_decay_evaluation(self, total_important: int, killed: int) -> None:
        m = self._current()
        if m is None:
            return
        m.decay_evaluations += total_important
        m.decay_false_kills += killed
        m.ops.append(MemoryOpRecord(
            op_type="rerank",
            metadata={"important": total_important, "killed": killed},
        ))

    def get_session_metrics(self, session_id: str = "") -> dict[str, Any]:
        sid = session_id or self._current_session
        m = self._sessions.get(sid)
        if m is None:
            return {"error": f"No metrics for session {sid!r}"}
        return m.to_dict()

    def get_aggregate(self) -> AggregateMemoryMetrics:
        agg = AggregateMemoryMetrics(total_sessions=len(self._sessions))
        for m in self._sessions.values():
            agg.total_writes += m.writes
            agg.total_writes_successful += m.writes_successful
            agg.total_write_probes += m.write_probes
            agg.total_write_probes_recalled += m.write_probes_recalled
            agg.total_recalls += m.recalls
            agg.total_recalls_with_hits += m.recalls_with_hits
            agg.total_prefetch_turns += m.prefetch_turns
            agg.total_prefetch_hits += m.prefetch_hits
            agg.total_facts_pre += m.facts_pre_compact
            agg.total_facts_post += m.facts_post_compact
            agg.total_decay_evals += m.decay_evaluations
            agg.total_decay_kills += m.decay_false_kills
        return agg

    def export_json(self) -> str:
        return json.dumps(
            {
                "sessions": {
                    sid: m.to_dict() for sid, m in self._sessions.items()
                },
                "aggregate": self.get_aggregate().to_dict(),
            },
            ensure_ascii=False,
            indent=2,
        )

    def save_to_file(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.export_json(), encoding="utf-8")

    def load_from_file(self, path: Path) -> None:
        path = Path(path)
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for sid, sdata in data.get("sessions", {}).items():
                m = SessionMemoryMetrics(session_id=sid)
                m.start_time = sdata.get("start_time", m.start_time)
                m.writes = sdata.get("writes", 0)
                m.writes_successful = sdata.get("writes_successful", 0)
                m.write_probes = sdata.get("write_probes", 0)
                m.write_probes_recalled = sdata.get("write_probes_recalled", 0)
                m.recalls = sdata.get("recalls", 0)
                m.recalls_with_hits = sdata.get("recalls_with_hits", 0)
                m.prefetch_turns = sdata.get("prefetch_turns", 0)
                m.prefetch_hits = sdata.get("prefetch_hits", 0)
                m.facts_pre_compact = sdata.get("facts_pre_compact", 0)
                m.facts_post_compact = sdata.get("facts_post_compact", 0)
                m.decay_evaluations = sdata.get("decay_evaluations", 0)
                m.decay_false_kills = sdata.get("decay_false_kills", 0)
                self._sessions[sid] = m
        except Exception as exc:
            logger.warning("Failed to load memory metrics: %s", exc)


def get_collector() -> MemoryMetricsCollector:
    return MemoryMetricsCollector.get_instance()
