# Implement Boyer-Moore majority vote algorithm in Python. Analyze its time and space complexity.
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Implement Boyer-Moore majority vote algorithm in Python. Analyze its time and space complexity.

## Conversation
### Turn 1 (user)
Implement Boyer-Moore majority vote algorithm in Python. Analyze its time and space complexity.

### Turn 2 (assistant)
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/boyer_moore.py",
  "content": "\"\"\"\nBoyer-Moore Majority Vote Algorithm\n\nFinds the element that appears more than ⌊n/2⌋ times in a sequence (if one exists).\nTwo-pass approach: first pass finds a candidate, second pass verifies it.\n\"\"\"\n\n\ndef majority_element(nums: list[int]) -> int | None:\n    \"\"\"Return the majority element, or None if none exists.\n\n    Time:  O(n) — two linear passes\n    Space: O(1) — only two extra variables\n    \"\"\
```

### Turn 3 (tool)
File created successfully at: /data/agent/choucisan/boyer_moore.py (file state is current in your context — no need to Read it back)

### Turn 4 (assistant)
## Boyer-Moore Majority Vote Algorithm

### Implementation

```python
def majority_element(nums: list[int]) -> int | None:
    # Pass 1: find candidate
    candidate = None
    count = 0
    for num in nums:
        if count == 0:
            candidate = num
            count = 1
        elif num == candidate:
            count += 1
        else:
            count -= 1

    # Pass 2: verify candidate
    if candidate is not None and nums.count(candidate) > len(nums) // 2:
        return candidate
    return None
```

### How It Works

**Pass 1 — Find Candidate:**
- Track a `candidate` and a `count`
- If `count == 0`, adopt the current element as the new candidate
- If the current element matches the candidate, increment count
- Otherwise, decrement count (effectively "cancelling" a pair of different elements)

The intuition: if an element truly appears > n/2 times, it can survive all cancellations.

**Pass 2 — Verify:**
- The first pass only guarantees a candidate, not that it's a majority
- A second pass counts occurrences to confirm

### Complexity Analysis

| Metric | Complexity | Explanation |
|--------|-----------|-------------|
| **Time** | **O(n)** | Two linear passes over the array |
| **Space** | **O(1)** | Only two variables (`candidate`, `count`) |

### Key Properties

- **Optimal** — any majority-finding algorithm must read all n elements (Ω(n) lower bound), so this is asymptotically optimal in both time and space
- **Online** — the first pass processes elements one at a time, so it works with streams
- **Does not sort** — unlike median-based approaches, no ordering is required
- **Generalizes** — can be extended to find elements appearing > ⌊n/3⌋ times (at most 2 candidates) with the same O(n) / O(1) bounds

### Example Trace

For `[3, 3, 4, 2, 3, 3, 3, 2, 3]`:

| Step | Element | Candidate | Count |
|------|---------|-----------|-------|
| 1 | 3 | 3 | 1 |
| 2 | 3 | 3 | 2 |
| 3 | 4 | 3 | 1 |
| 4 | 2 | 3 | 0 |
| 5 | 3 | 3 | 1 |
| 6 | 3 | 3 | 2 |
| 7 | 3 | 3 | 3 |
| 8 | 2 | 3 | 2 |
| 9 | 3 | 3 | 3 |

Candidate = 3, verified count = 6 > 9/2 → **3 is the majority element**.

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