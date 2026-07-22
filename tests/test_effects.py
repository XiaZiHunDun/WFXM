"""Unit tests for effects module."""

from __future__ import annotations

import asyncio
import pytest
import time

from butler.core.effects import async_race, async_with_timeout, race, retry_with_backoff, timeout_with_default, with_retry, with_timeout


class TestRetry:
    def test_with_retry_succeeds_on_retry(self):
        counter = [0]

        @with_retry(max_attempts=3, wait_seconds=0.01)
        def flaky_fn():
            counter[0] += 1
            if counter[0] < 3:
                raise ValueError("fail")
            return "success"

        result = flaky_fn()
        assert result == "success"
        assert counter[0] == 3

    def test_with_retry_gives_up_after_max_attempts(self):
        counter = [0]

        @with_retry(max_attempts=2, wait_seconds=0.01)
        def always_fails():
            counter[0] += 1
            raise ValueError("always fail")

        from tenacity import RetryError

        with pytest.raises(RetryError):
            always_fails()
        assert counter[0] == 2

    def test_retry_with_backoff(self):
        counter = [0]

        def flaky_fn():
            counter[0] += 1
            if counter[0] < 2:
                raise ValueError("fail")
            return "ok"

        result = retry_with_backoff(flaky_fn, max_attempts=2, wait_seconds=0.01)
        assert result == "ok"
        assert counter[0] == 2


class TestTimeout:
    def test_with_timeout_succeeds_within_time(self):
        @with_timeout(1.0)
        def fast_fn():
            return "done"

        result = fast_fn()
        assert result == "done"

    def test_with_timeout_returns_default_on_timeout(self):
        @with_timeout(0.1, default="timeout")
        def slow_fn():
            time.sleep(0.5)
            return "done"

        result = slow_fn()
        assert result == "timeout"

    def test_with_timeout_raises_on_timeout(self):
        @with_timeout(0.1, raise_on_timeout=True)
        def slow_fn():
            time.sleep(0.5)
            return "done"

        with pytest.raises(TimeoutError):
            slow_fn()

    def test_timeout_with_default(self):
        def slow_fn():
            time.sleep(0.5)
            return "done"

        result = timeout_with_default(slow_fn, 0.1, default="timed_out")
        assert result == "timed_out"


class TestRace:
    def test_race_returns_first_result(self):
        def fast():
            time.sleep(0.05)
            return "fast"

        def slow():
            time.sleep(0.5)
            return "slow"

        result, index = race(fast, slow)
        assert result == "fast"
        assert index == 0

    def test_race_with_timeout(self):
        def slow():
            time.sleep(0.5)
            return "slow"

        with pytest.raises(RuntimeError):
            race(slow, timeout=0.1)


@pytest.mark.asyncio
class TestAsyncEffects:
    async def test_async_with_timeout_succeeds(self):
        async def fast():
            return "done"

        result = await async_with_timeout(fast(), 1.0)
        assert result == "done"

    async def test_async_with_timeout_returns_default(self):
        async def slow():
            await asyncio.sleep(0.5)
            return "done"

        result = await async_with_timeout(slow(), 0.1, default="timeout")
        assert result == "timeout"

    async def test_async_race(self):
        async def fast():
            await asyncio.sleep(0.05)
            return "fast"

        async def slow():
            await asyncio.sleep(0.5)
            return "slow"

        result = await async_race(fast(), slow())
        assert result == "fast"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])