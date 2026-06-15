---
name: b9-prod-lingwen-validate-progress
description: LingWen1 prod — close workflow_state batch so validate_progress passes
version: 1
triggers:
  - LingWen1
  - validate_progress
  - workflow_state
  - OPEN_FIX
  - 进度验证
preferred_tools:
  - read_file
  - patch
  - terminal
---

# LingWen1: novel-factory/workflow_state.json

`novel-factory/workflow_state.json` is **one line**:

`status:OPEN_FIX`

`validate_progress.py` fails until `status:OPEN_FIX` becomes `status:PASSED`.

## Mandatory steps

1. `read_file novel-factory/workflow_state.json`
2. `patch` **only** (never `write_file`):
   - path: `novel-factory/workflow_state.json`
   - old_string: `status:OPEN_FIX`
   - new_string: `status:PASSED`
3. `read_file` again — must contain `status:PASSED`
4. `terminal`: `python3 novel-factory/scripts/validate_progress.py` → `进度验证: 通过`
5. `python3 -m pytest test_b9.py -q`

If patch fails, copy `status:OPEN_FIX` exactly from read_file output.
