# Convert this code to use dataclasses instead of the current approach:

```python
def calculate(data)
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Convert this code to use dataclasses instead of the current approach:

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
Convert this code to use dataclasses instead of the current approach:

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
  "file_path": "/data/agent/choucisan/calculator.py",
  "content": "from dataclasses import dataclass\n\n\n@dataclass\nclass Item:\n    type: str\n    value: float\n\n    @property\n    def adjusted_value(self) -> float:\n        multipliers = {\"A\": 1.1, \"B\": 0.9, \"C\": 1.05}\n        return self.value * multipliers.get(self.type, 1.0)\n\n\ndef calculate(data: list[Item]) -> float:\n    return sum(item.adjusted_value for item in data)\n"
}
```

### Turn 3 (tool)
File created successfully at: /data/agent/choucisan/calculator.py (file state is current in your context — no need to Read it back)

### Turn 4 (assistant)
Created `calculator.py`. Key changes:

- **`Item` dataclass** with `type` and `value` fields, replacing bare dictionaries
- **`adjusted_value` property** encapsulates the multiplier logic per item type
- **`calculate`** is now a simple `sum()` over the adjusted values

Usage:

```python
data = [Item("A", 100), Item("B", 200), Item("C", 50)]
result = calculate(data)
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