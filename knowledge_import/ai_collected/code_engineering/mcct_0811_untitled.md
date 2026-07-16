# Restructure this code to follow single responsibility:

```python
def calculate(data):
    total = 0
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Restructure this code to follow single responsibility:

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
Restructure this code to follow single responsibility:

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
def get_multiplier(item_type):
    multipliers = {'A': 1.1, 'B': 0.9, 'C': 1.05}
    return multipliers.get(item_type, 1.0)

def calculate_item(item):
    return item['value'] * get_multiplier(item['type'])

def calculate(data):
    return sum(calculate_item(item) for item in data)
```

Each function now has one job: `get_multiplier` maps types to rates, `calculate_item` computes a single item's value, and `calculate` aggregates. Adding a new type only requires updating the `multipliers` dict.

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