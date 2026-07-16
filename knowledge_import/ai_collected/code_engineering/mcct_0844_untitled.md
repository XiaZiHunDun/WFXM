# Refactor this code to use Adapter pattern:

```python
def calculate(data):
    total = 0
    for ite
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Refactor this code to use Adapter pattern:

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
Refactor this code to use Adapter pattern:

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
```python
from abc import ABC, abstractmethod


class ItemAdapter(ABC):
    @abstractmethod
    def adjusted_value(self, value: float) -> float: ...


class TypeAAdapter(ItemAdapter):
    def adjusted_value(self, value: float) -> float:
        return value * 1.1


class TypeBAdapter(ItemAdapter):
    def adjusted_value(self, value: float) -> float:
        return value * 0.9


class TypeCAdapter(ItemAdapter):
    def adjusted_value(self, value: float) -> float:
        return value * 1.05


ADAPTERS: dict[str, ItemAdapter] = {
    'A': TypeAAdapter(),
    'B': TypeBAdapter(),
    'C': TypeCAdapter(),
}


def calculate(data):
    total = 0
    for item in data:
        adapter = ADAPTERS.get(item['type'])
        if adapter:
            total += adapter.adjusted_value(item['value'])
    return total
```

Each type's pricing logic is now encapsulated in its own adapter class behind a common `adjusted_value` interface. Adding a new type means adding a new class and registering it in `ADAPTERS` — no changes to `calculate`.

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