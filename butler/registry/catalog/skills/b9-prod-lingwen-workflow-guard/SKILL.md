---
name: b9-prod-lingwen-workflow-guard
description: LingWen1 prod — fix workflow_guard open-batch detection
version: 1
triggers:
  - LingWen1
  - workflow_guard
  - novel-factory
  - 待修复
preferred_tools:
  - read_file
  - patch
  - run_pytest
---

# LingWen1: scripts/workflow_guard.py

`has_open_completed()` must return `True` when a completed batch `result` contains `待修复` or `未通过`.

1. `read_file scripts/workflow_guard.py` and `test_b9.py`.
2. `patch` the branch under the `待修复` / `未通过` check — change `return False` to `return True`.
3. `run_pytest` until green.

Only edit `scripts/workflow_guard.py`.
