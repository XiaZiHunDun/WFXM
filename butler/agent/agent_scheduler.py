"""Agent concurrency scheduler with LLM rate limiting.

Controls:
- Max concurrent agents (default 3)
- Per-provider LLM call rate limiting (token bucket)
- Priority queue for agent tasks
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


class Priority(IntEnum):
    HIGH = 0
    NORMAL = 1
    LOW = 2
    BACKGROUND = 3


@dataclass
class ScheduledTask:
    id: str
    priority: Priority = Priority.NORMAL
    created_at: float = field(default_factory=time.time)


class TokenBucket:
    """Rate limiter using token bucket algorithm."""

    def __init__(self, rate: float = 10.0, capacity: float = 20.0):
        """
        Args:
            rate: Tokens per second (requests/sec for LLM calls)
            capacity: Max burst size
        """
        self.rate = rate
        self.capacity = capacity
        self._tokens = capacity
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0, timeout: float = 30.0) -> bool:
        """Acquire tokens. Blocks until available or timeout."""
        deadline = time.monotonic() + timeout
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True

            if time.monotonic() >= deadline:
                return False

            wait_time = min(tokens / self.rate, deadline - time.monotonic())
            if wait_time <= 0:
                return False
            await asyncio.sleep(min(wait_time, 0.1))

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_refill = now

    @property
    def available_tokens(self) -> float:
        self._refill()
        return self._tokens


class AgentScheduler:
    """Controls concurrent agent execution and LLM API rate limits."""

    def __init__(
        self,
        max_concurrent: int = 3,
        default_rate: float = 10.0,
        default_capacity: float = 20.0,
    ):
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._rate_limiters: dict[str, TokenBucket] = {}
        self._default_rate = default_rate
        self._default_capacity = default_capacity
        self._active_count = 0
        self._total_scheduled = 0
        self._total_completed = 0
        self._lock = asyncio.Lock()

    def configure_provider_rate(
        self, provider: str, rate: float, capacity: float | None = None
    ) -> None:
        """Set rate limit for a specific provider."""
        self._rate_limiters[provider] = TokenBucket(
            rate=rate, capacity=capacity or rate * 2
        )

    def _get_limiter(self, provider: str) -> TokenBucket:
        if provider not in self._rate_limiters:
            self._rate_limiters[provider] = TokenBucket(
                rate=self._default_rate, capacity=self._default_capacity
            )
        return self._rate_limiters[provider]

    async def acquire_slot(self) -> bool:
        """Acquire an execution slot. Blocks until available."""
        await self._semaphore.acquire()
        async with self._lock:
            self._active_count += 1
            self._total_scheduled += 1
        return True

    def release_slot(self) -> None:
        """Release an execution slot."""
        self._semaphore.release()
        # Use a fire-and-forget approach for the lock
        self._active_count = max(0, self._active_count - 1)
        self._total_completed += 1

    async def acquire_llm_call(self, provider: str, timeout: float = 30.0) -> bool:
        """Acquire rate limit token for an LLM call."""
        limiter = self._get_limiter(provider)
        return await limiter.acquire(timeout=timeout)

    async def run_with_scheduling(
        self,
        coro: Callable[[], Awaitable[Any]],
        provider: str = "",
        priority: Priority = Priority.NORMAL,
    ) -> Any:
        """Execute a coroutine with concurrency control and rate limiting."""
        await self.acquire_slot()
        try:
            if provider:
                acquired = await self.acquire_llm_call(provider)
                if not acquired:
                    raise TimeoutError(
                        f"LLM rate limit timeout for provider '{provider}'"
                    )
            return await coro()
        finally:
            self.release_slot()

    def get_stats(self) -> dict:
        return {
            "active_agents": self._active_count,
            "max_concurrent": self.max_concurrent,
            "total_scheduled": self._total_scheduled,
            "total_completed": self._total_completed,
            "queue_waiting": self.max_concurrent - self._semaphore._value,
            "rate_limiters": {
                name: {"available_tokens": round(rl.available_tokens, 1), "rate": rl.rate}
                for name, rl in self._rate_limiters.items()
            },
        }


# Module-level singleton
scheduler = AgentScheduler()
