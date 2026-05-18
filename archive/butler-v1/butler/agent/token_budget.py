"""Token budget controller — tracks and limits token consumption.

Supports:
- Per-task budget (max tokens for a single agent execution)
- Per-day budget (rolling 24h limit across all tasks)
- Per-project budget (optional, for cost allocation)
- Cost estimation before execution
"""
from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Approximate costs per million tokens (USD) — update as pricing changes
_COST_PER_M_TOKENS: dict[str, dict[str, float]] = {
    "claude": {"input": 3.0, "output": 15.0},
    "openai": {"input": 2.5, "output": 10.0},
    "deepseek": {"input": 0.14, "output": 0.28},
    "minimax": {"input": 0.1, "output": 0.1},
    "qwen": {"input": 0.3, "output": 0.6},
    "glm": {"input": 0.5, "output": 0.5},
    "_default": {"input": 1.0, "output": 2.0},
}


@dataclass
class BudgetConfig:
    max_tokens_per_task: int = 500_000
    max_tokens_per_day: int = 5_000_000
    max_cost_per_day_usd: float = 10.0
    warn_at_percent: float = 0.8  # warn when 80% consumed


@dataclass
class UsageRecord:
    task_id: str
    provider: str
    input_tokens: int
    output_tokens: int
    timestamp: float
    estimated_cost_usd: float = 0.0


class TokenBudgetController:
    """Tracks token usage and enforces budget limits."""

    def __init__(self, db_path: str | Path | None = None, config: BudgetConfig | None = None):
        self.config = config or BudgetConfig()
        if db_path is None:
            from butler.config.settings import settings

            db_path = settings.butler_home / "token_usage.db"
        self.db_path = str(db_path)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS token_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT '',
                    project TEXT NOT NULL DEFAULT '',
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_cost_usd REAL NOT NULL DEFAULT 0.0,
                    timestamp REAL NOT NULL
                )
            """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_usage_time ON token_usage(timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_usage_task ON token_usage(task_id)"
            )

    def record_usage(
        self,
        task_id: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        project: str = "",
    ) -> None:
        cost = self.estimate_cost(provider, input_tokens, output_tokens)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO token_usage (task_id, provider, project, input_tokens, output_tokens, estimated_cost_usd, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (task_id, provider, project, input_tokens, output_tokens, cost, time.time()),
            )

    def check_task_budget(self, task_id: str) -> tuple[bool, str]:
        """Check if task has exceeded its token budget. Returns (ok, message)."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(input_tokens + output_tokens), 0) FROM token_usage WHERE task_id = ?",
                (task_id,),
            ).fetchone()

        total = row[0] if row else 0
        limit = self.config.max_tokens_per_task

        if total >= limit:
            return False, f"任务 token 预算已耗尽 ({total:,}/{limit:,})"

        if total >= limit * self.config.warn_at_percent:
            pct = total / limit * 100
            return True, f"警告：任务已消耗 {pct:.0f}% token 预算 ({total:,}/{limit:,})"

        return True, ""

    def check_daily_budget(self) -> tuple[bool, str]:
        """Check if daily budget is exceeded. Returns (ok, message)."""
        cutoff = time.time() - 86400
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(input_tokens + output_tokens), 0), COALESCE(SUM(estimated_cost_usd), 0) "
                "FROM token_usage WHERE timestamp >= ?",
                (cutoff,),
            ).fetchone()

        total_tokens = row[0] if row else 0
        total_cost = row[1] if row else 0.0

        if total_tokens >= self.config.max_tokens_per_day:
            return False, f"每日 token 预算已耗尽 ({total_tokens:,}/{self.config.max_tokens_per_day:,})"

        if total_cost >= self.config.max_cost_per_day_usd:
            return False, f"每日费用上限已达 (${total_cost:.2f}/${self.config.max_cost_per_day_usd:.2f})"

        if total_tokens >= self.config.max_tokens_per_day * self.config.warn_at_percent:
            pct = total_tokens / self.config.max_tokens_per_day * 100
            return True, f"警告：今日已消耗 {pct:.0f}% token 预算"

        return True, ""

    @staticmethod
    def estimate_cost(provider: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost in USD."""
        rates = _COST_PER_M_TOKENS.get(provider, _COST_PER_M_TOKENS["_default"])
        return (
            input_tokens / 1_000_000 * rates["input"]
            + output_tokens / 1_000_000 * rates["output"]
        )

    def get_daily_summary(self) -> dict:
        """Get today's usage summary."""
        cutoff = time.time() - 86400
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(DISTINCT task_id), "
                "COALESCE(SUM(input_tokens), 0), "
                "COALESCE(SUM(output_tokens), 0), "
                "COALESCE(SUM(estimated_cost_usd), 0) "
                "FROM token_usage WHERE timestamp >= ?",
                (cutoff,),
            ).fetchone()

            per_provider = conn.execute(
                "SELECT provider, SUM(input_tokens), SUM(output_tokens), SUM(estimated_cost_usd) "
                "FROM token_usage WHERE timestamp >= ? GROUP BY provider",
                (cutoff,),
            ).fetchall()

        return {
            "tasks": row[0],
            "input_tokens": row[1],
            "output_tokens": row[2],
            "total_tokens": row[1] + row[2],
            "estimated_cost_usd": round(row[3], 4),
            "budget_remaining_tokens": max(0, self.config.max_tokens_per_day - row[1] - row[2]),
            "budget_remaining_usd": round(max(0, self.config.max_cost_per_day_usd - row[3]), 4),
            "per_provider": {
                p: {"input": int(i), "output": int(o), "cost_usd": round(c, 4)}
                for p, i, o, c in per_provider
            },
        }

    def cleanup_old_records(self, days: int = 90) -> int:
        """Delete usage records older than N days."""
        cutoff = time.time() - days * 86400
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM token_usage WHERE timestamp < ?", (cutoff,))
            return cursor.rowcount


# Module-level singleton
budget_controller = TokenBudgetController.__new__(TokenBudgetController)
budget_controller.config = BudgetConfig()
budget_controller.db_path = ""
budget_controller._initialized = False


def get_budget_controller() -> TokenBudgetController:
    global budget_controller
    if not budget_controller._initialized:
        budget_controller = TokenBudgetController()
        budget_controller._initialized = True
    return budget_controller
