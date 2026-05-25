"""PR-F4: provider circuit breaker."""

from __future__ import annotations

from butler.transport.fallback import FallbackEntry
from butler.transport.provider_health import (
    filter_fallback_chain,
    is_circuit_open,
    record_provider_failure,
    record_provider_success,
)


def test_circuit_opens_after_failures():
    record_provider_success("p1", "m1")
    for _ in range(5):
        record_provider_failure("p1", "m1")
    assert is_circuit_open("p1", "m1")


def test_filter_fallback_chain_skips_open():
    record_provider_failure("bad", "m")
    for _ in range(5):
        record_provider_failure("bad", "m")
    chain = [
        FallbackEntry(provider="good", model="m", api_key=None, base_url=None),
        FallbackEntry(provider="bad", model="m", api_key=None, base_url=None),
    ]
    filtered = filter_fallback_chain(chain)
    assert filtered[0].provider == "good"
