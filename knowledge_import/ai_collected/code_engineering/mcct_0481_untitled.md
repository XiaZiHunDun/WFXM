# The following Python code has a logic error bug. Find and fix it:

```python
def process(data):
    
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
The following Python code has a logic error bug. Find and fix it:

```python
def process(data):
    result = []
    for i in range(len(data)):
        if data[i] > 0:
            result.append(data[i] * 2)
    return result
# Bug: should handle logic error
```

## Conversation
### Turn 1 (user)
The following Python code has a logic error bug. Find and fix it:

```python
def process(data):
    result = []
    for i in range(len(data)):
        if data[i] > 0:
            result.append(data[i] * 2)
    return result
# Bug: should handle logic error
```

### Turn 2 (assistant)
The code works but has a couple of issues:

1. **No input validation** — passing `None` causes a crash
2. **Index-based iteration** is unidiomatic; direct iteration is clearer

Let me fix it:

```python
def process(data):
    if data is None:
        return []
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
    return result
```

Changes:
- Added a `None` check to prevent `TypeError` when iterating
- Replaced `for i in range(len(data))` with `for item in data` — cleaner and avoids potential `IndexError` if the list were modified during iteration

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