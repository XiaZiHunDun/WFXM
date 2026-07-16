# Restructure this code to follow separation of concerns:

```python
def calculate(data):
    total = 
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Restructure this code to follow separation of concerns:

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
Restructure this code to follow separation of concerns:

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
Here's the restructured code separating the pricing rules from the calculation logic:

```python
MULTIPLIERS = {
    'A': 1.1,
    'B': 0.9,
    'C': 1.05,
}

def calculate(data):
    total = 0
    for item in data:
        multiplier = MULTIPLIERS.get(item['type'], 1)
        total += item['value'] * multiplier
    return total
```

Changes:
- **Pricing rules** (`MULTIPLIERS`) are now a standalone data mapping, easy to extend or configure externally
- **Calculation logic** (`calculate`) only handles iteration and accumulation, with no embedded business rules
- Adding a new type just requires a dict entry instead of a new `elif` branch

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