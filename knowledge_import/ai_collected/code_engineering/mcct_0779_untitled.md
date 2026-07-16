# Refactor this code to use Template Method pattern:

```python
def calculate(data):
    total = 0
   
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Refactor this code to use Template Method pattern:

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
Refactor this code to use Template Method pattern:

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


class ItemCalculator(ABC):
    """Template method: defines the calculation skeleton."""

    def calculate(self, data):
        total = 0
        for item in data:
            total += self._adjust(item['value'])
        return total

    @abstractmethod
    def _adjust(self, value):
        """Subclasses provide the type-specific multiplier."""
        ...


class TypeACalculator(ItemCalculator):
    def _adjust(self, value):
        return value * 1.1


class TypeBCalculator(ItemCalculator):
    def _adjust(self, value):
        return value * 0.9


class TypeCCalculator(ItemCalculator):
    def _adjust(self, value):
        return value * 1.05


# --- usage (mixed-type data) ---

_CALCULATORS = {
    'A': TypeACalculator(),
    'B': TypeBCalculator(),
    'C': TypeCCalculator(),
}

def calculate(data):
    total = 0
    for item in data:
        calc = _CALCULATORS.get(item['type'])
        if calc:
            total += calc._adjust(item['value'])
    return total
```

**What changed:**
- `ItemCalculator` is the abstract base with the template method `calculate()` that owns the iteration loop.
- `_adjust()` is the primitive operation each subclass overrides to provide its multiplier.
- The dispatch dict at the bottom preserves the original mixed-type-in-one-list behavior, routing each item to the right subclass.

If your data is already grouped by type (one list per type), you can use the calculators directly without the dispatch dict:

```python
calc_a = TypeACalculator()
calc_a.calculate(type_a_items)  # no branching needed
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