"""Result and Maybe monads for functional error handling.

Inspired by Effect-TS/ZIO and Rust's Result type.

This is a shim file for backward compatibility.
The actual implementation is split into:
- result_monad.py: Result type (Ok/Err) and basic operations
- maybe_monad.py: Maybe type (Some/NoneVal) and basic operations
- combinators.py: Function combinators and utilities
"""

from __future__ import annotations

from butler.core.effects.result_monad import (
    Err,
    Ok,
    Result,
    async_result_from_fn,
    err,
    ok,
    result_from_fn,
)
from butler.core.effects.maybe_monad import (
    Maybe,
    NoneVal,
    Some,
    maybe_from_value,
    none,
    some,
)
from butler.core.effects.combinators import (
    async_collect_maybes,
    async_collect_results,
    async_pipe,
    async_traverse_maybe,
    async_traverse_result,
    collect_maybes,
    collect_results,
    compose,
    constantly,
    ensure,
    filter_map,
    find_map,
    flatten,
    flatten_result,
    flip,
    get_or_else,
    identity,
    lift_maybe,
    lift_result,
    map_error,
    maybe_to_result,
    option_to_result,
    partition_maybes,
    partition_results,
    pipe,
    recover,
    result_to_maybe,
    sequence_maybes,
    sequence_results,
    tap,
    traverse_maybe,
    traverse_result,
    unless,
    when,
    with_default,
)


__all__ = [
    # Result types
    "Ok",
    "Err",
    "Result",
    "ok",
    "err",
    "result_from_fn",
    "async_result_from_fn",
    # Maybe types
    "Some",
    "NoneVal",
    "Maybe",
    "some",
    "none",
    "maybe_from_value",
    # Pipe and Compose
    "pipe",
    "compose",
    "lift_result",
    "lift_maybe",
    "collect_results",
    "collect_maybes",
    # Async helpers
    "async_collect_results",
    "async_collect_maybes",
    "async_pipe",
    # Function combinators
    "identity",
    "constantly",
    "flip",
    "tap",
    "when",
    "unless",
    # Transformations
    "result_to_maybe",
    "maybe_to_result",
    "option_to_result",
    # Filter and find
    "filter_map",
    "find_map",
    "partition_results",
    "partition_maybes",
    # Traverse and sequence
    "traverse_result",
    "traverse_maybe",
    "async_traverse_result",
    "async_traverse_maybe",
    "sequence_results",
    "sequence_maybes",
    # Result utilities
    "map_error",
    "recover",
    "ensure",
    # Maybe utilities
    "with_default",
    "get_or_else",
    "flatten",
    "flatten_result",
]
