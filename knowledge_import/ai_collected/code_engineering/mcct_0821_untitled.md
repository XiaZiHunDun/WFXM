# Refactor this code to be more SOLID-compliant:

```python
def calculate(data):
    total = 0
    for
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Refactor this code to be more SOLID-compliant:

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
Refactor this code to be more SOLID-compliant:

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
Here's a SOLID-compliant refactoring using the Strategy pattern:

```python
from abc import ABC, abstractmethod
from typing import Dict


class PriceCalculator(ABC):
    @abstractmethod
    def calculate(self, value: float) -> float:
        pass


class TypeACalculator(PriceCalculator):
    def calculate(self, value: float) -> float:
        return value * 1.1


class TypeBCalculator(PriceCalculator):
    def calculate(self, value: float) -> float:
        return value * 0.9


class TypeCCalculator(PriceCalculator):
    def calculate(self, value: float) -> float:
        return value * 1.05


_calculators: Dict[str, PriceCalculator] = {
    'A': TypeACalculator(),
    'B': TypeBCalculator(),
    'C': TypeCCalculator(),
}


def register_calculator(item_type: str, calculator: PriceCalculator):
    """Register a new calculator for an item type."""
    _calculators[item_type] = calculator


def calculate(data):
    total = 0
    for item in data:
        calculator = _calculators.get(item['type'])
        if calculator:
            total += calculator.calculate(item['value'])
    return total
```

**SOLID improvements:**

- **S** (Single Responsibility): Each calculator class handles one discount logic
- **O** (Open/Closed): New types added via `register_calculator()` without modifying existing code
- **D** (Dependency Inversion): `calculate()` depends on the `PriceCalculator` abstraction, not concrete implementations

Want me to add this to a file in your project?

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