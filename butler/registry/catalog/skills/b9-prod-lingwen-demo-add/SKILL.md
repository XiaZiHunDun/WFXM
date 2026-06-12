---
name: b9-prod-lingwen-demo-add
description: LingWen1 prod — fix demo/hello.py add() operator
version: 1
triggers:
  - LingWen1
  - demo/hello.py
  - lingwen
preferred_tools:
  - read_file
  - patch
  - run_pytest
---

# LingWen1: demo/hello.py add()

`add(a, b)` incorrectly returns `a - b`; test expects `a + b`.

1. `read_file demo/hello.py` and `test_b9.py`.
2. `patch demo/hello.py` — change `return a - b` to `return a + b`.
3. `run_pytest` until green.

Only edit `demo/hello.py`; do not modify `test_b9.py`.
