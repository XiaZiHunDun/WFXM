# Code Kadane's algorithm for maximum subarray in Python. Compare it with a brute-force approach.
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Code Kadane's algorithm for maximum subarray in Python. Compare it with a brute-force approach.

## Conversation
### Turn 1 (user)
Code Kadane's algorithm for maximum subarray in Python. Compare it with a brute-force approach.

### Turn 2 (assistant)
**Tool**: `Write`
```json
{
  "file_path": "/data/agent/choucisan/max_subarray.py",
  "content": "\"\"\"Maximum subarray: Kadane's algorithm vs brute-force.\"\"\"\n\nimport time\n\n\ndef max_subarray_brute(nums: list[int]) -> tuple[int, int, int]:\n    \"\"\"O(n^2) — try every subarray.\"\"\"\n    n = len(nums)\n    best_sum = nums[0]\n    best_l = best_r = 0\n    for i in range(n):\n        s = 0\n        for j in range(i, n):\n            s += nums[j]\n            if s > best_sum:\n                best_sum, best_l, bes
```

### Turn 3 (tool)
File created successfully at: /data/agent/choucisan/max_subarray.py (file state is current in your context — no need to Read it back)

### Turn 4 (assistant)
**Tool**: `Bash`
```json
{
  "command": "python max_subarray.py",
  "description": "Run max subarray comparison script"
}
```

### Turn 5 (tool)
=== Correctness ===
  OK  nums=[1]                                       brute=(0, 0, 1)  kadane=(0, 0, 1)
  OK  nums=[-2, 1, -3, 4, -1, 2, 1, -5, 4]           brute=(3, 6, 6)  kadane=(3, 6, 6)
  OK  nums=[5, 4, -1, 7, 8]                          brute=(0, 4, 23)  kadane=(0, 4, 23)
  OK  nums=[-1, -2, -3]                              brute=(0, 0, -1)  kadane=(0, 0, -1)
  OK  nums=[2, -1, 2, -1, 2, -1, 2]                  brute=(0, 6, 5)  kadane=(0, 6, 5)
  OK  nums=[1, 2, 3, 4, 5]                           brute=(0, 4, 15)  kadane=(0, 4, 15)
  OK  nums=[-2, -3, 4, -1, -2, 1, 5, -3]             brute=(2, 6, 7)  kadane=(2, 6, 7)

All passed: True

=== Performance ===
       n    Brute (ms)   Kadane (ms)   Speedup
----------------------------------------------
   1,000        35.89         0.13    277.5x
   5,000       860.28         0.63   1362.8x
  10,000      2687.74         0.91   2954.9x
  50,000     61901.68         4.60  13470.9x

### Turn 6 (assistant)
Both implementations are in `max_subarray.py`. Here's the comparison:

### Algorithm

| | Brute-force | Kadane's |
|---|---|---|
| **Idea** | Try every `(i, j)` pair, sum each subarray | Track running sum; reset when it drops below the current element |
| **Time** | O(n^2) | O(n) |
| **Space** | O(1) | O(1) |

### Key insight (Kadane's)

At each position `i`, the best subarray ending at `i` is either:
- extend the previous best by `nums[i]`, or
- start fresh at `nums[i]`

Pick whichever is larger. Track the global max across all positions.

### Results

All 7 test cases pass with identical outputs from both methods. Performance at scale:

| n | Brute | Kadane | Speedup |
|---:|---:|---:|---:|
| 1,000 | 35.9 ms | 0.13 ms | 278x |
| 5,000 | 860 ms | 0.63 ms | 1,363x |
| 10,000 | 2,688 ms | 0.91 ms | 2,955x |
| 50,000 | 61,902 ms | 4.60 ms | 13,471x |

The speedup grows quadratically, consistent with the O(n^2) vs O(n) complexity difference.

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