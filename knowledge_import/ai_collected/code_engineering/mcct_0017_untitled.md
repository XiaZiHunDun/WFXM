# Code two-pointer technique for three-sum in Python. Compare it with a brute-force approach.
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Code two-pointer technique for three-sum in Python. Compare it with a brute-force approach.

## Conversation
### Turn 1 (user)
Code two-pointer technique for three-sum in Python. Compare it with a brute-force approach.

### Turn 2 (assistant)
## Three Sum: Two-Pointer vs Brute-Force

### Brute-Force — O(n³)

```python
def three_sum_brute(nums: list[int]) -> list[list[int]]:
    """Check every triple. O(n^3) time, O(1) extra space."""
    n = len(nums)
    result = set()
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                if nums[i] + nums[j] + nums[k] == 0:
                    result.add(tuple(sorted((nums[i], nums[j], nums[k]))))
    return [list(t) for t in result]
```

### Two-Pointer — O(n²)

```python
def three_sum_two_pointer(nums: list[int]) -> list[list[int]]:
    """Sort + two-pointer. O(n^2) time, O(1) extra space (ignoring output)."""
    nums.sort()
    n = len(nums)
    result = []

    for i in range(n - 2):
        # Skip duplicate values for the first element
        if i > 0 and nums[i] == nums[i - 1]:
            continue

        left, right = i + 1, n - 1

        while left < right:
            total = nums[i] + nums[left] + nums[right]

            if total < 0:
                left += 1
            elif total > 0:
                right -= 1
            else:
                result.append([nums[i], nums[left], nums[right]])
                # Skip duplicates for second and third elements
                while left < right and nums[left] == nums[left + 1]:
                    left += 1
                while left < right and nums[right] == nums[right - 1]:
                    right -= 1
                left += 1
                right -= 1

    return result
```

### Comparison

| Aspect | Brute-Force | Two-Pointer |
|---|---|---|
| **Time** | O(n³) | O(n²) |
| **Space** | O(n) for the set | O(1) extra |
| **1,000 elements** | ~10⁹ operations | ~10⁶ operations |
| **10,000 elements** | ~10¹² (intractable) | ~10⁸ (~seconds) |

### Why Two-Pointer Works

The key insight after sorting:

1. **Fix** `nums[i]` as the first element.
2. The remaining problem becomes **two-sum on a sorted array** — find `nums[left] + nums[right] == -nums[i]`.
3. If the sum is too small, move `left` right; if too large, move `right` left. Each pair is considered at most once, giving O(n) per fixed element.

Duplicate skipping (the `while` loops after a match and the `if i > 0` check) ensures no repeated triplets without needing a set.

### Quick Verification

```python
print(three_sum_two_pointer([-1, 0, 1, 2, -1, -4]))
# [[-1, -1, 2], [-1, 0, 1]]

print(three_sum_two_pointer([0, 0, 0, 0]))
# [[0, 0, 0]]

print(three_sum_two_pointer([]))
# []
```

The two-pointer approach is the standard solution — it reduces the cubic brute-force to quadratic by exploiting the sorted order to eliminate an entire loop.

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