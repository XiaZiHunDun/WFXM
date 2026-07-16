# Code binary search on a rotated sorted array in Python. Compare it with a brute-force approach.
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Code binary search on a rotated sorted array in Python. Compare it with a brute-force approach.

## Conversation
### Turn 1 (user)
Code binary search on a rotated sorted array in Python. Compare it with a brute-force approach.

### Turn 2 (assistant)
Here's a Python implementation of both approaches:

**Binary Search on Rotated Sorted Array — O(log n)**

```python
def search_rotated(nums: list[int], target: int) -> int:
    lo, hi = 0, len(nums) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if nums[mid] == target:
            return mid
        # Left half is sorted
        if nums[lo] <= nums[mid]:
            if nums[lo] <= target < nums[mid]:
                hi = mid - 1
            else:
                lo = mid + 1
        # Right half is sorted
        else:
            if nums[mid] < target <= nums[hi]:
                lo = mid + 1
            else:
                hi = mid - 1
    return -1
```

**Brute-Force Linear Scan — O(n)**

```python
def search_brute(nums: list[int], target: int) -> int:
    for i, v in enumerate(nums):
        if v == target:
            return i
    return -1
```

**Key comparison:**

| | Binary Search | Brute Force |
|---|---|---|
| Time | O(log n) | O(n) |
| Space | O(1) | O(1) |
| Requires sorted input | Yes (rotated sorted) | No |
| Practical wins at | n > ~16 | Small n, unsorted data |

The binary search exploits the invariant that **at least one half of a rotated sorted array is always sorted**. At each step it checks which half is sorted, then narrows the search to the half that could contain the target. The brute-force approach ignores all structure and scans every element.

For `n = 1_000_000`, binary search does ~20 comparisons vs up to 1,000,000 for brute force.

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