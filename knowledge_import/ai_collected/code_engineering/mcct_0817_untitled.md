# Improve the performance of this code by using indexing:

```python
def calculate(data):
    total = 
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Improve the performance of this code by using indexing:

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
Improve the performance of this code by using indexing:

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
Use a dictionary lookup instead of chained `if/elif` comparisons:

```python
MULTIPLIERS = {'A': 1.1, 'B': 0.9, 'C': 1.05}

def calculate(data):
    total = 0
    for item in data:
        mult = MULTIPLIERS.get(item['type'])
        if mult is not None:
            total += item['value'] * mult
    return total
```

The `if/elif` chain is O(n) per item in the number of type branches. A dict lookup is O(1). For large datasets this eliminates repeated string comparisons on every iteration. The dict is defined at module level so it's built once.

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