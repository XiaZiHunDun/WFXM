"""Effect-style retry utilities using tenacity."""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from tenacity import (
    AsyncRetrying,
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


def async_with_retry(
    *,
    max_attempts: int = 3,
    wait_seconds: float = 1.0,
    exponential_backoff: bool = True,
    retry_on: type[Exception] | tuple[type[Exception], ...] = Exception,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorate an async function to retry on failure with configurable backoff."""
    if exponential_backoff:
        wait = wait_exponential(multiplier=wait_seconds, min=wait_seconds, max=10)
    else:
        wait = wait_fixed(wait_seconds)

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(max_attempts),
                wait=wait,
                retry=retry_if_exception_type(retry_on),
            ):
                with attempt:
                    return await fn(*args, **kwargs)

        return wrapped

    return decorator


async def async_retry_with_backoff(
    fn: Callable[..., Any],
    *,
    max_attempts: int = 3,
    wait_seconds: float = 1.0,
) -> Any:
    """Run an async function with exponential backoff retry."""
    return await async_with_retry(
        max_attempts=max_attempts,
        wait_seconds=wait_seconds,
        exponential_backoff=True,
    )(fn)()
