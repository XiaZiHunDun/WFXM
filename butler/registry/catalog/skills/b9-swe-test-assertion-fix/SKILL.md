---
name: b9-swe-test-assertion-fix
description: SWE-012 — test_fix; wrong empty-list assertion in test_sorter.py
version: 1
triggers:
  - SWE-012
  - test_fix
  - test_sorter.py
  - sort_items
preferred_tools:
  - read_file
  - patch
  - terminal
---

# SWE-012: Fix test assertion (not implementation)

Issue: `sort_items([])` should return `[]` but `test_sort_empty` wrongly expects `None`.

Workflow:

1. `read_file test_sorter.py` and `sorter.py` — implementation is already correct.
2. `patch test_sorter.py` only in `test_sort_empty`:

```python
    assert sort_items([]) == []
```

3. `terminal`: `python -m pytest _swe_test.py -q` until green.

Do not patch `sorter.py`. Do not edit `_swe_test.py`.
