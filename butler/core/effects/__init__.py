"""Effect-style utilities for functional programming.

Inspired by Effect-TS/ZIO:
- Result[T, E] monad for error handling
- Maybe[T] monad for optional values
- pipe/compose for function composition
- retry/timeout/race for control flow
- ToolFailure/ToolSuccess for standardized tool error handling
- fold/match for pattern matching on monadic values
- partition_either for splitting Results by variant
"""

from __future__ import annotations

__all__ = [
    # Core types
    "Ok",
    "Err",
    "Result",
    "Some",
    "NoneVal",
    "Maybe",
    "Lazy",
    # Constructors
    "ok",
    "err",
    "some",
    "none",
    # Result operations
    "result_from_fn",
    "async_result_from_fn",
    "result_from_optional",
    "map_error",
    "recover",
    "ensure",
    "deep_map",
    # Maybe operations
    "maybe_from_value",
    "maybe_to_result",
    "with_default",
    "get_or_else",
    # Combinators
    "pipe",
    "compose",
    "lift_result",
    "lift_maybe",
    "tap",
    "constantly",
    "identity",
    "flip",
    "filter_map",
    "find_map",
    "flatten",
    "flatten_result",
    "when",
    "unless",
    # Transformations
    "result_to_maybe",
    "maybe_to_result",
    "option_to_result",
    # Collection
    "collect_results",
    "collect_maybes",
    "partition_results",
    "partition_maybes",
    "partition_either",
    "traverse_result",
    "traverse_maybe",
    "sequence_results",
    "sequence_maybes",
    "deep_sequence",
    # Async helpers
    "async_collect_results",
    "async_collect_maybes",
    "async_pipe",
    "async_traverse_result",
    "async_traverse_maybe",
    # Pattern matching
    "match_result",
    "match_maybe",
    # Iteration
    "while_some",
    # Control flow
    "with_retry",
    "async_with_retry",
    "retry_with_backoff",
    "async_retry_with_backoff",
    "with_timeout",
    "async_with_timeout",
    "timeout_with_default",
    "race",
    "async_race",
    # Tool handling
    "ToolFailure",
    "ToolSuccess",
    "tool_failure",
    "tool_success",
    "tool_result_from_fn",
]

# Lazy-loaded heavy submodules (loaded on first symbol access)
_result_loaded = False
_advanced_loaded = False

# Eager-loaded light submodules (needed for race/retry/timeout functionality)
from .race import async_race, race
from .retry import (
    async_retry_with_backoff,
    async_with_retry,
    retry_with_backoff,
    with_retry,
)
from .timeout import async_with_timeout, timeout_with_default, with_timeout
from .tool_failure import (
    ToolFailure,
    ToolSuccess,
    tool_failure,
    tool_result_from_fn,
    tool_success,
)


def __getattr__(name: str) -> object:
    global _result_loaded, _advanced_loaded

    if not _result_loaded:
        _load_result_symbols()

    if name in _result_symbols:
        return _result_symbols[name]

    if not _advanced_loaded:
        _load_advanced_symbols()

    if name in _advanced_symbols:
        return _advanced_symbols[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_result_symbols: dict[str, object] = {}
_advanced_symbols: dict[str, object] = {}


def _load_result_symbols() -> None:
    global _result_loaded
    from butler.core.effects.result import (
        Err, Maybe, NoneVal, Ok, Result, Some,
        async_collect_maybes, async_collect_results, async_pipe,
        async_result_from_fn, async_traverse_maybe, async_traverse_result,
        collect_maybes, collect_results, compose, constantly, err,
        ensure, filter_map, find_map, flatten, flatten_result,
        get_or_else, identity, lift_maybe, lift_result, map_error,
        maybe_from_value, maybe_to_result, none, ok, option_to_result,
        partition_maybes, partition_results, pipe, recover,
        result_from_fn, result_to_maybe, sequence_maybes, sequence_results,
        some, tap, traverse_maybe, traverse_result, unless, when,
        with_default, flip,
    )
    _result_symbols.update({
        "Err": Err, "Maybe": Maybe, "NoneVal": NoneVal, "Ok": Ok,
        "Result": Result, "Some": Some,
        "async_collect_maybes": async_collect_maybes,
        "async_collect_results": async_collect_results,
        "async_pipe": async_pipe,
        "async_result_from_fn": async_result_from_fn,
        "async_traverse_maybe": async_traverse_maybe,
        "async_traverse_result": async_traverse_result,
        "collect_maybes": collect_maybes,
        "collect_results": collect_results,
        "compose": compose, "constantly": constantly, "err": err,
        "ensure": ensure, "filter_map": filter_map,
        "find_map": find_map, "flatten": flatten,
        "flatten_result": flatten_result, "get_or_else": get_or_else,
        "identity": identity, "lift_maybe": lift_maybe,
        "lift_result": lift_result, "map_error": map_error,
        "maybe_from_value": maybe_from_value,
        "maybe_to_result": maybe_to_result, "none": none, "ok": ok,
        "option_to_result": option_to_result,
        "partition_maybes": partition_maybes,
        "partition_results": partition_results, "pipe": pipe,
        "recover": recover, "result_from_fn": result_from_fn,
        "result_to_maybe": result_to_maybe,
        "sequence_maybes": sequence_maybes,
        "sequence_results": sequence_results, "some": some,
        "tap": tap, "traverse_maybe": traverse_maybe,
        "traverse_result": traverse_result, "unless": unless,
        "when": when, "with_default": with_default, "flip": flip,
    })
    _result_loaded = True


def _load_advanced_symbols() -> None:
    global _advanced_loaded
    from butler.core.effects.advanced import (
        Lazy, deep_map, deep_sequence, match_result, match_maybe,
        partition_either, result_from_optional, while_some,
    )
    _advanced_symbols.update({
        "Lazy": Lazy,
        "deep_map": deep_map,
        "deep_sequence": deep_sequence,
        "match_result": match_result,
        "match_maybe": match_maybe,
        "partition_either": partition_either,
        "result_from_optional": result_from_optional,
        "while_some": while_some,
    })
    _advanced_loaded = True
