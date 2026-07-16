# Restructure this code to follow dependency injection:

```python
def calculate(data):
    total = 0

**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Restructure this code to follow dependency injection:

```python
def calculate(data):
    total = 0
    for item in data:
        if item['type'] == 'A':
            total += item['value'] * 1.1
        elif item['type'] == 'B':
            total += item['value'] * 0.9
        elif item['type'] == 'C':
            total += item['value'] * 1.05
    return total
```

## Conversation
### Turn 1 (user)
Restructure this code to follow dependency injection:

```python
def calculate(data):
    total = 0
    for item in data:
        if item['type'] == 'A':
            total += item['value'] * 1.1
        elif item['type'] == 'B':
            total += item['value'] * 0.9
        elif item['type'] == 'C':
            total += item['value'] * 1.05
    return total
```

### Turn 2 (assistant)
Here's the refactored version using dependency injection for the pricing strategies:

```python
from typing import Callable

DEFAULT_STRATEGIES: dict[str, Callable[[float], float]] = {
    'A': lambda v: v * 1.1,
    'B': lambda v: v * 0.9,
    'C': lambda v: v * 1.05,
}

def calculate(data, strategies=None):
    strategies = strategies or DEFAULT_STRATEGIES
    total = 0
    for item in data:
        strategy = strategies.get(item['type'])
        if strategy:
            total += strategy(item['value'])
    return total
```

The key change: pricing logic is no longer buried in conditionals — it's a dictionary of callables that's injected as a parameter. Callers can pass custom strategies or use the defaults:

```python
# default behavior unchanged
calculate(items)

# inject custom strategies (e.g. for testing or new types)
calculate(items, strategies={
    'A': lambda v: v * 2.0,
    'D': lambda v: v * 0.5,
})
```

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