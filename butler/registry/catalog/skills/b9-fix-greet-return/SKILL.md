---
name: b9-fix-greet-return
description: B9 Tier-2 prod-shaped — fix greet() return literal
version: 1
triggers:
  - greet
  - verify_fail
  - prod_demo
preferred_tools:
  - read_file
  - patch
  - run_pytest
---

# B9: fix greet return literal

When `greet.py` returns `'hi'` but `test_b9.py` expects `'hello'`:

1. `read_file test_b9.py` — confirm expected literal `'hello'`.
2. `read_file greet.py` — find `return 'hi'`.
3. `patch greet.py` — change return to `'hello'` only.
4. `run_pytest` until green.

Do not edit `test_b9.py`. This is a prod-shaped verify_fail pattern.
