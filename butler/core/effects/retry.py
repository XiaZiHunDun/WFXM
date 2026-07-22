"""Effect-style retry utilities using tenacity."""

from __future__ import annotations

from typing import Callable, TypeVar

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
)

T = TypeVar("T")


def with_retry(
    *,
    max_attempts: int = 3,
    wait_seconds: float = 1.0,
    exponential_backoff: bool = True,
    retry_on: type[Exception] | tuple[type[Exception], ...] = Exception,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorate a function to retry on failure with configurable backoff."""
    if exponential_backoff:
        wait = wait_exponential(multiplier=wait_seconds, min=wait_seconds, max=10)
    else:
        wait = wait_fixed(wait_seconds)

    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait,
        retry=retry_if_exception_type(retry_on),
    )


def retry_with_backoff(
    fn: Callable[..., T],
    *,
    max_attempts: int = 3,
    wait_seconds: float = 1.0,
) -> T:
    """Run a function with exponential backoff retry."""
    return with_retry(
        max_attempts=max_attempts,
        wait_seconds=wait_seconds,
        exponential_backoff=True,
    )(fn)()