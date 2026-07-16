# Restructure this code to follow composition over inheritance:

```python
def calculate(data):
    to
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Restructure this code to follow composition over inheritance:

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
Restructure this code to follow composition over inheritance:

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
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/strategies.py",
  "content": "from typing import Callable\n\n\nclass PricingStrategy:\n    def __init__(self, multiplier: float):\n        self.multiplier = multiplier\n\n    def apply(self, value: float) -> float:\n        return value * self.multiplier\n\n\nSTRATEGIES: dict[str, PricingStrategy] = {\n    'A': PricingStrategy(1.1),\n    'B': PricingStrategy(0.9),\n    'C': PricingStrategy(1.05),\n}\n\n\ndef calculate(data: list[dict], strategies: dict[str
```

### Turn 3 (tool)
File created successfully at: /data/agent/choucisan/strategies.py (file state is current in your context — no need to Read it back)

### Turn 4 (assistant)
The refactoring extracts each type's pricing logic into a composable `PricingStrategy` object, then looks it up at runtime:

- **`PricingStrategy`** — a simple callable that holds a multiplier and applies it to a value.
- **`STRATEGIES` dict** — maps type codes (`'A'`, `'B'`, `'C'`) to strategy instances. Adding a new type means adding one dict entry; `calculate` never changes.
- **`calculate`** accepts an optional `strategies` argument, so callers can inject custom strategies at test time or for different business contexts.

New types are added without touching `calculate`:

```python
STRATEGIES['D'] = PricingStrategy(2.0)
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