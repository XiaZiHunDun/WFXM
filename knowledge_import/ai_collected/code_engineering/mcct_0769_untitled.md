# Restructure this code to follow open/closed principle:

```python
def calculate(data):
    total = 0
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Restructure this code to follow open/closed principle:

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
Restructure this code to follow open/closed principle:

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
Let me check if this code exists in the repo.
**Tool**: `Grep`
```json
{
  "pattern": "if item\\['type'\\] == 'A'"
}
```

### Turn 3 (tool)
Found 13 files
mimo-claude-code-traces/scripts/generate_questions.py
mimo-claude-code-traces/output/traces/debugging/ebb128b9.jsonl
mimo-claude-code-traces/output/traces/refactoring/4cfac59a.jsonl
mimo-claude-code-traces/output/traces/refactoring/b306c128.jsonl
mimo-claude-code-traces/output/traces/refactoring/a2020518.jsonl
mimo-claude-code-traces/output/traces/refactoring/11ac78a4.jsonl
mimo-claude-code-traces/output/traces/refactoring/0450e9be.jsonl
mimo-claude-code-traces/output/traces/debugging/79f08c23.jsonl
mimo-claude-code-traces/output/traces/refactoring/40c03e97.jsonl
mimo-claude-code-traces/output/traces/refactoring/73e6bcee.jsonl
mimo-claude-code-traces/output/traces/refactoring/0a0ada8b.jsonl
mimo-claude-code-traces/data/all_questions.jsonl
mimo-claude-code-traces/data/questions.jsonl

### Turn 4 (assistant)
This code doesn't exist as source in the repo (only in trace data), so I'll provide the refactored version directly.

The issue: adding a new type (e.g., `'D'`) requires modifying `calculate()`. With OCP, you extend behavior by adding new code, not changing existing code.

```python
# Extension point: register new types here without touching calculate()
ADJUSTMENTS = {
    'A': lambda value: value * 1.1,
    'B': lambda value: value * 0.9,
    'C': lambda value: value * 1.05,
}

def calculate(data):
    total = 0
    for item in data:
        adjust = ADJUSTMENTS.get(item['type'])
        if adjust is None:
            raise ValueError(f"Unknown item type: {item['type']}")
        total += adjust(item['value'])
    return total
```

To add a new type, you only add an entry to `ADJUSTMENTS` — `calculate()` stays unchanged:

```python
ADJUSTMENTS['D'] = lambda value: value * 1.2  # no other code touched
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