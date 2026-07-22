# ADR: Effects Integration for Tool Dispatch

## Status

Accepted

## Context

The `butler.core.effects` module provides functional programming tools (`with_retry`, `with_timeout`, `race`) to improve resilience. This ADR documents how these effects are integrated into the tool dispatch pipeline.

## Decision

### 1. Retry Integration

**Scope**: Regular tool calls and MCP tool calls.

**Retry Conditions**:
- `max_attempts`: 2 (initial + 1 retry)
- `wait_seconds`: 0.1
- `retry_on`: `(OSError, ConnectionError)` — only network-related errors

**Idempotency Safety**: Tools with side effects are excluded from retry via `NO_RETRY_TOOLS`:

```python
NO_RETRY_TOOLS = frozenset({
    "write_file",      # File write
    "patch",           # File modification
    "delete_file",     # File deletion
    "terminal",        # Arbitrary command execution
    "opencode_task",   # Task creation
    "delegate_task",   # Task delegation
    "run_workflow",    # Workflow execution
    "mcp_install",     # MCP server installation
    "mcp_remove",      # MCP server removal
})
```

**RetryError Unwrapping**: `tenacity.RetryError` wraps the last exception. Extract the original exception for user-facing error messages:

```python
except RetryError as exc:
    original_exc = getattr(exc, 'last_attempt', None)
    if original_exc is not None:
        original_exc = getattr(original_exc, 'exception', None)
    final_exc = original_exc if original_exc is not None else exc
```

### 2. Integration Points

#### Shared Helper (`registry_invoke_ops.py`)

```python
def call_tool_with_retry(
    name: str,
    fn: Callable[[], Any],
    *,
    max_attempts: int = 2,
    wait_seconds: float = 0.1,
    retry_on: tuple[type[Exception], ...] = (OSError, ConnectionError),
) -> Any:
    """
    Call a tool function with retry logic, respecting NO_RETRY_TOOLS.
    
    - If tool is in NO_RETRY_TOOLS: direct call, no retry
    - Otherwise: wrap with with_retry and unwrap RetryError
    """
    if name in NO_RETRY_TOOLS:
        return fn()
    
    @with_retry(max_attempts=max_attempts, wait_seconds=wait_seconds, retry_on=retry_on)
    def _call_with_retry() -> Any:
        return fn()
    
    try:
        return _call_with_retry()
    except RetryError as exc:
        original_exc = getattr(exc, 'last_attempt', None)
        if original_exc is not None:
            original_exc = getattr(original_exc, 'exception', None)
        raise original_exc if original_exc is not None else exc
```

#### Regular Tools (`registry_invoke_ops.py`)

```python
result = call_tool_with_retry(name, lambda: handler(**merged))
```

#### MCP Tools (`registry.py::_dispatch_mcp_tool`)

```python
result = call_tool_with_retry(name, lambda: dispatch_mcp_tool(name, args))
```

### 3. Error Handling

- **Retryable errors** (`OSError`, `ConnectionError`): Retried up to `max_attempts`, then `RetryError` is caught and unwrapped.
- **Non-retryable errors** (`ValueError`, `TypeError`, `KeyError`): Propagate without retry (programming errors should surface).
- **Side-effect tools**: Always run without retry, even on `OSError`.

## Consequences

- **Benefits**: Network-related transient errors are automatically retried, improving reliability.
- **Safety**: Side-effect tools cannot be accidentally retried, preventing data corruption.
- **User Experience**: Error messages show the original exception rather than internal `RetryError`.
- **Maintenance**: New tools with side effects must be added to `NO_RETRY_TOOLS`.

## Testing

Integration tests are in `tests/test_retry_integration.py`:
- `test_retry_on_network_error`: Verifies retry behavior
- `test_no_retry_on_non_network_error`: Verifies non-retry behavior
- `test_retry_exhausted_returns_error`: Verifies error handling
- `test_no_retry_for_side_effect_tools`: Verifies idempotency safety
- `test_no_retry_tools_contains_side_effect_tools`: Verifies `NO_RETRY_TOOLS` completeness