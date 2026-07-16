# Refactor this code to be more modular:

```python
def calculate(data):
    total = 0
    for item in
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Refactor this code to be more modular:

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
Refactor this code to be more modular:

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
Here's a more modular version using a dictionary-based strategy pattern:

```python
MULTIPLIERS = {
    'A': 1.1,
    'B': 0.9,
    'C': 1.05,
}

def calculate(data):
    total = 0
    for item in data:
        multiplier = MULTIPLIERS.get(item['type'], 1.0)
        total += item['value'] * multiplier
    return total
```

**What changed:**
- **Multiplier config extracted** to `MULTIPLIERS` dict — adding/removing types is now a one-line change instead of editing control flow
- **`if/elif` chain replaced** with a dict lookup + `.get()` default of `1.0` for unknown types
- **Easier to extend** — new types just need a new key/value pair; no branching logic to maintain

If you want even more flexibility (e.g., custom per-type logic beyond simple multiplication), you can swap the dict values for callables:

```python
STRATEGIES = {
    'A': lambda v: v * 1.1,
    'B': lambda v: v * 0.9,
    'C': lambda v: v * 1.05,
}

def calculate(data):
    return sum(
        STRATEGIES.get(item['type'], lambda v: v)(item['value'])
        for item in data
    )
```

This version trades a bit of readability for full extensibility — each type can have arbitrary computation, not just a multiplier.

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