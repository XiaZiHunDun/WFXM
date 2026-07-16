# Write a Python decorator that retries a function up to N times on exception. Include usage examples 
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Write a Python decorator that retries a function up to N times on exception. Include usage examples and tests.

## Conversation
### Turn 1 (user)
Write a Python decorator that retries a function up to N times on exception. Include usage examples and tests.

### Turn 2 (assistant)
I'll create a retry decorator with examples and tests.
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/retry_decorator.py",
  "content": "import time\nimport functools\nfrom typing import Type\n\n\ndef retry(max_retries: int = 3, delay: float = 0, exceptions: tuple[Type[Exception], ...] = (Exception,)):\n    \"\"\"Decorator that retries a function up to max_retries times on exception.\n\n    Args:\n        max_retries: Maximum number of retry attempts (default 3).\n        delay: Seconds to wait between retries (default 0).\n        exceptions: Tuple of exc
```

### Turn 3 (tool)
File created successfully at: /data/agent/choucisan/retry_decorator.py (file state is current in your context — no need to Read it back)

### Turn 4 (assistant)
**Tool**: `Bash`
```json
{
  "command": "python retry_decorator.py",
  "description": "Run retry decorator tests"
}
```

### Turn 5 (tool)
All tests passed.

### Turn 6 (assistant)
All 6 tests pass. Here's the decorator at `retry_decorator.py`:

**Signature:** `@retry(max_retries=3, delay=0, exceptions=(Exception,))`

- `max_retries` — how many times to retry after the first failure (default 3, so 4 total attempts)
- `delay` — seconds to sleep between retries (default 0)
- `exceptions` — tuple of exception types that trigger a retry; other exceptions propagate immediately

**Key behaviors tested:**
- Returns immediately on success (no unnecessary retries)
- Retries up to N times, then re-raises the last exception
- Only retries the specified exception types, lets others through untouched
- Preserves `__name__` and `__doc__` via `functools.wraps`
- Passes `*args` and `**kwargs` correctly

## Available Tools
- **Bash**: Run a shell command.
- **BashOutput**: Read output from a running background shell command.
- **Edit**: Replace text in an existing file.
- **Glob**: Find files by glob pattern.
- **Grep**: Search file contents by pattern.
- **KillBash**: Stop a running background shell command.
- **LS**: List files and directories.
- **MultiEdit**: Apply multiple text replacements to one file.
- **NotebookEdit**: Edit a Jupyter notebook cell.
- **NotebookRead**: Read a Jupyter notebook.

## Execution Trace