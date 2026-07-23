"""Effect-style utilities for functional programming.

Inspired by Effect-TS/ZIO:
- Result[T, E] monad for error handling
- Maybe[T] monad for optional values
- pipe/compose for function composition
- retry/timeout/race for control flow
"""

from __future__ import annotations

from .race import async_race, race
from .retry import (
    async_retry_with_backoff,
    async_with_retry,
    retry_with_backoff,
    with_retry,
)
from .result import (
    Err,
    Maybe,
    NoneVal,
    Ok,
    Result,
    Some,
    async_result_from_fn,
    collect_maybes,
    collect_results,
    compose,
    err,
    lift_maybe,
    lift_result,
    maybe_from_value,
    none,
    ok,
    pipe,
    result_from_fn,
    some,
)
from .timeout import async_with_timeout, timeout_with_default, with_timeout

__all__ = [
    "async_race",
    "async_retry_with_backoff",
    "async_with_retry",
    "async_result_from_fn",
    "async_with_timeout",
    "collect_maybes",
    "collect_results",
    "compose",
    "Err",
    "err",
    "lift_maybe",
    "lift_result",
    "maybe_from_value",
    "Maybe",
    "none",
    "NoneVal",
    "Ok",
    "ok",
    "pipe",
    "race",
    "retry_with_backoff",
    "result_from_fn",
    "Result",
    "Some",
    "some",
    "timeout_with_default",
    "with_retry",
    "with_timeout",
]