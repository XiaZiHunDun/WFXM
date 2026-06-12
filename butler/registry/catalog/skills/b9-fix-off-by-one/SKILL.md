---
name: b9-fix-off-by-one
description: B9 Tier-1 — fix off-by-one loop bound (range)
version: 1
triggers:
  - fix_off_by_one
  - sum_until
  - loops.py
  - range(n
preferred_tools:
  - read_file
  - patch
  - run_pytest
---

# B9: fix off-by-one loop

When `test_b9.py` expects `sum_until(4) == 6` (sum 0+1+2+3) but implementation uses `range(n + 1)`:

1. `read_file test_b9.py` — note expected sum semantics.
2. `read_file loops.py` — find loop bound.
3. `patch loops.py` — change `range(n + 1)` to `range(n)`.
4. `run_pytest` until green.

Do not edit `test_b9.py`.
