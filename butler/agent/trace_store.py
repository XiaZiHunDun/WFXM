from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class TraceSpan:
    span_id: str
    trace_id: str
    name: str  # "llm_call", "tool_call", "guardrail_check"
    start_time: float
    end_time: float = 0.0
    attributes: dict[str, Any] = field(default_factory=dict)
    parent_span_id: str = ""
    status: str = "ok"  # "ok", "error", "cancelled"


@dataclass
class TraceRecord:
    trace_id: str
    task_id: str = ""
    agent_role: str = ""
    task_description: str = ""
    model_provider: str = ""
    model_name: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    turns_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls_count: int = 0
    success: bool = True
    error: str = ""
    guardrail_triggers: int = 0
    spans: list[TraceSpan] = field(default_factory=list)


class TraceStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            from butler.config.settings import settings

            db_path = settings.butler_home / "traces.db"
        self.db_path = str(db_path)
        self._init_db()
        self.auto_cleanup()

    def _init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS traces (
                    trace_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL DEFAULT '',
                    agent_role TEXT NOT NULL DEFAULT '',
                    task_description TEXT NOT NULL DEFAULT '',
                    model_provider TEXT NOT NULL DEFAULT '',
                    model_name TEXT NOT NULL DEFAULT '',
                    start_time REAL NOT NULL,
                    end_time REAL NOT NULL DEFAULT 0,
                    turns_used INTEGER NOT NULL DEFAULT 0,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    tool_calls_count INTEGER NOT NULL DEFAULT 0,
                    success INTEGER NOT NULL DEFAULT 1,
                    error TEXT NOT NULL DEFAULT '',
                    guardrail_triggers INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS spans (
                    span_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    start_time REAL NOT NULL,
                    end_time REAL NOT NULL DEFAULT 0,
                    attributes_json TEXT NOT NULL DEFAULT '{}',
                    parent_span_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'ok',
                    FOREIGN KEY (trace_id) REFERENCES traces(trace_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id);
                CREATE INDEX IF NOT EXISTS idx_spans_name ON spans(name);
                CREATE INDEX IF NOT EXISTS idx_traces_start ON traces(start_time);
                CREATE INDEX IF NOT EXISTS idx_traces_role ON traces(agent_role);
                CREATE INDEX IF NOT EXISTS idx_traces_success ON traces(success);
                PRAGMA foreign_keys = ON;
                """
            )
            conn.commit()
        finally:
            conn.close()

    def save_trace(self, trace: TraceRecord) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            cur = conn.cursor()
            cur.execute(
                """
                INSERT OR REPLACE INTO traces (
                    trace_id, task_id, agent_role, task_description, model_provider, model_name,
                    start_time, end_time, turns_used, input_tokens, output_tokens, tool_calls_count,
                    success, error, guardrail_triggers
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace.trace_id,
                    trace.task_id,
                    trace.agent_role,
                    trace.task_description,
                    trace.model_provider,
                    trace.model_name,
                    trace.start_time,
                    trace.end_time,
                    trace.turns_used,
                    trace.input_tokens,
                    trace.output_tokens,
                    trace.tool_calls_count,
                    1 if trace.success else 0,
                    trace.error,
                    trace.guardrail_triggers,
                ),
            )
            cur.execute("DELETE FROM spans WHERE trace_id = ?", (trace.trace_id,))
            for sp in trace.spans:
                cur.execute(
                    """
                    INSERT OR REPLACE INTO spans (
                        span_id, trace_id, name, start_time, end_time, attributes_json,
                        parent_span_id, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sp.span_id,
                        sp.trace_id,
                        sp.name,
                        sp.start_time,
                        sp.end_time,
                        json.dumps(sp.attributes, ensure_ascii=False),
                        sp.parent_span_id,
                        sp.status,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def get_trace(self, trace_id: str) -> TraceRecord | None:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM traces WHERE trace_id = ?", (trace_id,)).fetchone()
            if row is None:
                return None
            rec = TraceRecord(
                trace_id=row["trace_id"],
                task_id=row["task_id"] or "",
                agent_role=row["agent_role"] or "",
                task_description=row["task_description"] or "",
                model_provider=row["model_provider"] or "",
                model_name=row["model_name"] or "",
                start_time=float(row["start_time"] or 0.0),
                end_time=float(row["end_time"] or 0.0),
                turns_used=int(row["turns_used"] or 0),
                input_tokens=int(row["input_tokens"] or 0),
                output_tokens=int(row["output_tokens"] or 0),
                tool_calls_count=int(row["tool_calls_count"] or 0),
                success=bool(row["success"]),
                error=row["error"] or "",
                guardrail_triggers=int(row["guardrail_triggers"] or 0),
            )
            srows = conn.execute(
                "SELECT * FROM spans WHERE trace_id = ? ORDER BY start_time ASC",
                (trace_id,),
            ).fetchall()
            for sr in srows:
                try:
                    attrs = json.loads(sr["attributes_json"] or "{}")
                except json.JSONDecodeError:
                    attrs = {}
                rec.spans.append(
                    TraceSpan(
                        span_id=sr["span_id"],
                        trace_id=sr["trace_id"],
                        name=sr["name"],
                        start_time=float(sr["start_time"] or 0.0),
                        end_time=float(sr["end_time"] or 0.0),
                        attributes=attrs if isinstance(attrs, dict) else {},
                        parent_span_id=sr["parent_span_id"] or "",
                        status=sr["status"] or "ok",
                    )
                )
            return rec
        finally:
            conn.close()

    def list_traces(
        self,
        limit: int = 50,
        agent_role: Optional[str] = None,
        success: Optional[bool] = None,
    ) -> list[TraceRecord]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            clauses: list[str] = []
            params: list[Any] = []
            if agent_role is not None:
                clauses.append("agent_role = ?")
                params.append(agent_role)
            if success is not None:
                clauses.append("success = ?")
                params.append(1 if success else 0)
            where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
            q = f"SELECT trace_id FROM traces{where} ORDER BY start_time DESC LIMIT ?"
            params.append(limit)
            ids = [r["trace_id"] for r in conn.execute(q, params).fetchall()]
            out: list[TraceRecord] = []
            for tid in ids:
                rec = self.get_trace(tid)
                if rec is not None:
                    out.append(rec)
            return out
        finally:
            conn.close()

    def get_stats(self, since_hours: float = 24) -> dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cutoff = time.time() - float(since_hours) * 3600.0
        try:
            totals = conn.execute(
                """
                SELECT
                  COUNT(*) AS n,
                  SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS succ,
                  AVG(CAST(turns_used AS REAL)) AS avg_turns,
                  AVG(CAST(input_tokens + output_tokens AS REAL)) AS avg_tokens,
                  AVG(CASE WHEN end_time > start_time THEN (end_time - start_time) END) AS avg_dur,
                  SUM(guardrail_triggers) AS gsum
                FROM traces
                WHERE start_time >= ?
                """,
                (cutoff,),
            ).fetchone()
            n = int(totals["n"] or 0)
            succ = int(totals["succ"] or 0)
            success_rate = (succ / n) if n else 0.0
            avg_turns = float(totals["avg_turns"] or 0.0)
            avg_tokens = float(totals["avg_tokens"] or 0.0)
            avg_duration = float(totals["avg_dur"] or 0.0)
            gsum = int(totals["gsum"] or 0)
            guardrail_trigger_rate = (gsum / n) if n else 0.0

            tool_rows = conn.execute(
                """
                SELECT s.attributes_json, s.status, (s.end_time - s.start_time) AS dur
                FROM spans s
                JOIN traces t ON t.trace_id = s.trace_id
                WHERE t.start_time >= ? AND s.name = 'tool_call'
                """,
                (cutoff,),
            ).fetchall()

            distro: dict[str, int] = {}
            for r in tool_rows:
                tool_name = "unknown"
                try:
                    attrs = json.loads(r["attributes_json"] or "{}")
                    if isinstance(attrs, dict):
                        tool_name = str(attrs.get("tool_name") or attrs.get("name") or "unknown")
                except json.JSONDecodeError:
                    tool_name = "unknown"
                distro[tool_name] = distro.get(tool_name, 0) + 1

            return {
                "total_traces": n,
                "success_rate": success_rate,
                "avg_turns": avg_turns,
                "avg_tokens": avg_tokens,
                "tool_call_distribution": distro,
                "avg_duration": avg_duration,
                "guardrail_trigger_rate": guardrail_trigger_rate,
            }
        finally:
            conn.close()

    def get_tool_stats(self, trace_id: str) -> list[dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT span_id, attributes_json, status, start_time, end_time
                FROM spans
                WHERE trace_id = ? AND name = 'tool_call'
                ORDER BY start_time ASC
                """,
                (trace_id,),
            ).fetchall()
            by_tool: dict[str, dict[str, Any]] = {}
            for r in rows:
                try:
                    attrs = json.loads(r["attributes_json"] or "{}")
                except json.JSONDecodeError:
                    attrs = {}
                tname = "unknown"
                if isinstance(attrs, dict):
                    tname = str(attrs.get("tool_name") or attrs.get("name") or "unknown")

                dur = float(r["end_time"] or 0.0) - float(r["start_time"] or 0.0)
                if dur < 0:
                    dur = 0.0
                failed = (r["status"] or "ok") != "ok"
                bucket = by_tool.setdefault(
                    tname,
                    {
                        "name": tname,
                        "call_count": 0,
                        "total_duration": 0.0,
                        "failure_count": 0,
                    },
                )
                bucket["call_count"] += 1
                bucket["total_duration"] += dur
                if failed:
                    bucket["failure_count"] += 1

            out: list[dict[str, Any]] = []
            for tname, b in sorted(by_tool.items()):
                cnt = int(b["call_count"])
                avg_dur = (b["total_duration"] / cnt) if cnt else 0.0
                out.append(
                    {
                        "name": tname,
                        "call_count": cnt,
                        "avg_duration": avg_dur,
                        "failure_count": int(b["failure_count"]),
                    }
                )
            return out
        finally:
            conn.close()

    def cleanup(self, max_age_days: int = 30, max_records: int = 1000) -> dict:
        """Remove old traces. Keeps recent ones within both limits."""
        cutoff = time.time() - max_age_days * 86400
        with sqlite3.connect(self.db_path) as conn:
            # Delete by age
            age_cursor = conn.execute(
                "DELETE FROM spans WHERE trace_id IN (SELECT trace_id FROM traces WHERE start_time < ?)",
                (cutoff,),
            )
            conn.execute("DELETE FROM traces WHERE start_time < ?", (cutoff,))
            deleted_by_age = age_cursor.rowcount

            # Delete by count (keep most recent max_records)
            count_row = conn.execute("SELECT COUNT(*) FROM traces").fetchone()
            total = count_row[0] if count_row else 0
            deleted_by_count = 0
            if total > max_records:
                excess = total - max_records
                old_ids = conn.execute(
                    "SELECT trace_id FROM traces ORDER BY start_time ASC LIMIT ?",
                    (excess,),
                ).fetchall()
                if old_ids:
                    placeholders = ",".join("?" * len(old_ids))
                    ids = [r[0] for r in old_ids]
                    conn.execute(f"DELETE FROM spans WHERE trace_id IN ({placeholders})", ids)
                    conn.execute(f"DELETE FROM traces WHERE trace_id IN ({placeholders})", ids)
                    deleted_by_count = len(old_ids)

        total_deleted = deleted_by_age + deleted_by_count
        if total_deleted > 0:
            logger.info(f"Trace cleanup: removed {total_deleted} records ({deleted_by_age} by age, {deleted_by_count} by count)")
        return {
            "deleted_by_age": deleted_by_age,
            "deleted_by_count": deleted_by_count,
            "total_deleted": total_deleted,
        }

    def auto_cleanup(self) -> None:
        """Run cleanup if DB has grown large. Called on init."""
        try:
            db_file = Path(self.db_path)
            if db_file.exists() and db_file.stat().st_size > 50 * 1024 * 1024:  # 50MB
                self.cleanup(max_age_days=30, max_records=500)
        except Exception as e:
            logger.warning(f"Trace auto-cleanup failed: {e}")


class TraceCollector:
    """Lightweight in-process collector for building a ``TraceRecord``."""

    def __init__(
        self,
        agent_role: str = "",
        task_description: str = "",
        model_provider: str = "",
        model_name: str = "",
    ) -> None:
        self.trace = TraceRecord(
            trace_id=str(uuid.uuid4())[:12],
            agent_role=agent_role,
            task_description=task_description[:200],
            model_provider=model_provider,
            model_name=model_name,
            start_time=time.time(),
        )
        self._current_span: TraceSpan | None = None
        self._span_stack: list[TraceSpan] = []

    def start_span(self, name: str, **attrs: Any) -> TraceSpan:
        parent = self._span_stack[-1].span_id if self._span_stack else ""
        span = TraceSpan(
            span_id=str(uuid.uuid4())[:12],
            trace_id=self.trace.trace_id,
            name=name,
            start_time=time.time(),
            attributes=dict(attrs),
            parent_span_id=parent,
        )
        self._span_stack.append(span)
        self._current_span = span
        return span

    def end_span(self, span: TraceSpan, status: str = "ok", **attrs: Any) -> None:
        if self._span_stack and self._span_stack[-1].span_id == span.span_id:
            self._span_stack.pop()
        else:
            while self._span_stack and self._span_stack[-1].span_id != span.span_id:
                dropped = self._span_stack.pop()
                logger.debug("trace span stack unwind: missing end for %s", dropped.span_id)
            if self._span_stack and self._span_stack[-1].span_id == span.span_id:
                self._span_stack.pop()

        span.end_time = time.time()
        span.status = status
        span.attributes.update(attrs)
        self._current_span = self._span_stack[-1] if self._span_stack else None
        self.trace.spans.append(span)

    def record_llm_call(self, input_tokens: int = 0, output_tokens: int = 0, duration: float = 0.0) -> None:
        self.trace.input_tokens += int(input_tokens)
        self.trace.output_tokens += int(output_tokens)
        end = time.time()
        start = end - max(float(duration), 0.0)
        self.trace.spans.append(
            TraceSpan(
                span_id=str(uuid.uuid4())[:12],
                trace_id=self.trace.trace_id,
                name="llm_call",
                start_time=start,
                end_time=end,
                attributes={"input_tokens": input_tokens, "output_tokens": output_tokens},
            )
        )

    def record_tool_call(
        self,
        tool_name: str,
        args_keys: Any,
        duration: float,
        output_len: int,
        failed: bool = False,
    ) -> None:
        self.trace.tool_calls_count += 1
        end = time.time()
        start = end - max(float(duration), 0.0)
        keys = list(args_keys) if isinstance(args_keys, (list, tuple, set)) else list(args_keys or [])
        self.trace.spans.append(
            TraceSpan(
                span_id=str(uuid.uuid4())[:12],
                trace_id=self.trace.trace_id,
                name="tool_call",
                start_time=start,
                end_time=end,
                attributes={
                    "tool_name": tool_name,
                    "args_keys": keys,
                    "output_len": int(output_len),
                },
                status="error" if failed else "ok",
            )
        )

    def record_guardrail_trigger(self) -> None:
        self.trace.guardrail_triggers += 1
        end = time.time()
        self.trace.spans.append(
            TraceSpan(
                span_id=str(uuid.uuid4())[:12],
                trace_id=self.trace.trace_id,
                name="guardrail_check",
                start_time=end,
                end_time=end,
                attributes={"triggered": True},
                status="ok",
            )
        )

    def finalize(self, success: bool = True, error: str = "", turns_used: int = 0) -> TraceRecord:
        self.trace.end_time = time.time()
        self.trace.success = bool(success)
        self.trace.error = (error or "")[:2000]
        self.trace.turns_used = int(turns_used)
        return self.trace
