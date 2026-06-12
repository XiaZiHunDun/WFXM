---
name: b9-fix-operator
description: B9 Tier-2 — fix mul() using + instead of *
version: 1
triggers:
  - pytest_fix_impl
  - calc.py
  - wrong operator
preferred_tools:
  - read_file
  - patch
  - run_pytest
---

# B9: fix operator in calc.py

When `test_b9.py` expects multiplication but `calc.py` uses addition:

1. `read_file test_b9.py` — confirm `mul(a, b)` expects product.
2. `read_file calc.py` — find `return a + b` inside `mul`.
3. `patch calc.py` — replace `a + b` with `a * b`.
4. `run_pytest` until green.

Patch implementation only; never edit `test_b9.py`.
