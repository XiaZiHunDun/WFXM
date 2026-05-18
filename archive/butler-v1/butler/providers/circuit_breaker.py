"""Circuit breaker for LLM providers — automatic failover and rate limiting.

States:
- CLOSED: normal operation, requests pass through
- OPEN: provider is broken, requests short-circuit to fallback
- HALF_OPEN: testing if provider has recovered (limited requests)

Transitions:
- CLOSED → OPEN: failure_count >= failure_threshold within window
- OPEN → HALF_OPEN: after recovery_timeout seconds
- HALF_OPEN → CLOSED: success on test request
- HALF_OPEN → OPEN: failure on test request
"""
from __future__ import annotations

import logging
import time
import threading
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout: float = 60.0  # seconds before trying again
    window_size: float = 120.0  # failure counting window in seconds
    half_open_max_calls: int = 2  # max calls in half-open state


@dataclass
class ProviderHealth:
    provider_name: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    opened_at: float = 0.0
    half_open_calls: int = 0
    total_calls: int = 0
    total_failures: int = 0
    consecutive_failures: int = 0


class CircuitBreakerManager:
    """Manages circuit breakers for all LLM providers."""

    def __init__(self, config: CircuitBreakerConfig | None = None):
        self.config = config or CircuitBreakerConfig()
        self._health: dict[str, ProviderHealth] = {}
        self._fallback_chain: dict[str, list[str]] = {}
        self._lock = threading.Lock()

    def configure_fallback(self, provider: str, fallbacks: list[str]) -> None:
        """Set fallback chain for a provider."""
        with self._lock:
            self._fallback_chain[provider] = fallbacks

    def _get_health(self, provider: str) -> ProviderHealth:
        if provider not in self._health:
            self._health[provider] = ProviderHealth(provider_name=provider)
        return self._health[provider]

    def can_call(self, provider: str) -> bool:
        """Check if a provider can accept calls."""
        with self._lock:
            health = self._get_health(provider)
            now = time.time()

            if health.state == CircuitState.CLOSED:
                return True

            if health.state == CircuitState.OPEN:
                if now - health.opened_at >= self.config.recovery_timeout:
                    health.state = CircuitState.HALF_OPEN
                    health.half_open_calls = 0
                    logger.info(
                        f"Circuit breaker for '{provider}': OPEN → HALF_OPEN (testing recovery)"
                    )
                    return True
                return False

            if health.state == CircuitState.HALF_OPEN:
                return health.half_open_calls < self.config.half_open_max_calls

            return True

    def record_success(self, provider: str) -> None:
        """Record a successful call."""
        with self._lock:
            health = self._get_health(provider)
            health.total_calls += 1
            health.success_count += 1
            health.last_success_time = time.time()
            health.consecutive_failures = 0

            if health.state == CircuitState.HALF_OPEN:
                health.state = CircuitState.CLOSED
                health.failure_count = 0
                logger.info(f"Circuit breaker for '{provider}': HALF_OPEN → CLOSED (recovered)")

    def record_failure(self, provider: str, error: str = "") -> None:
        """Record a failed call. May trigger circuit open."""
        with self._lock:
            health = self._get_health(provider)
            now = time.time()
            health.total_calls += 1
            health.total_failures += 1
            health.failure_count += 1
            health.consecutive_failures += 1
            health.last_failure_time = now

            # Clean old failures outside window
            if now - health.opened_at > self.config.window_size:
                health.failure_count = 1

            if health.state == CircuitState.HALF_OPEN:
                health.state = CircuitState.OPEN
                health.opened_at = now
                logger.warning(
                    f"Circuit breaker for '{provider}': HALF_OPEN → OPEN (still failing: {error})"
                )
            elif health.failure_count >= self.config.failure_threshold:
                health.state = CircuitState.OPEN
                health.opened_at = now
                logger.warning(
                    f"Circuit breaker for '{provider}': CLOSED → OPEN "
                    f"({health.failure_count} failures in {self.config.window_size}s: {error})"
                )

    def get_available_provider(self, preferred: str) -> str | None:
        """Get an available provider, following fallback chain if needed."""
        if self.can_call(preferred):
            return preferred

        with self._lock:
            fallbacks = self._fallback_chain.get(preferred, [])

        for fb in fallbacks:
            if self.can_call(fb):
                logger.info(f"Provider '{preferred}' unavailable, falling back to '{fb}'")
                return fb

        return None

    def get_status(self) -> dict[str, dict]:
        """Get health status of all providers."""
        with self._lock:
            return {
                name: {
                    "state": h.state.value,
                    "failure_count": h.failure_count,
                    "consecutive_failures": h.consecutive_failures,
                    "total_calls": h.total_calls,
                    "total_failures": h.total_failures,
                    "last_failure": h.last_failure_time,
                    "last_success": h.last_success_time,
                }
                for name, h in self._health.items()
            }

    def reset(self, provider: str) -> None:
        """Manually reset a provider's circuit breaker."""
        with self._lock:
            if provider in self._health:
                self._health[provider] = ProviderHealth(provider_name=provider)
                logger.info(f"Circuit breaker for '{provider}' manually reset")


# Module-level singleton
circuit_breaker = CircuitBreakerManager()
