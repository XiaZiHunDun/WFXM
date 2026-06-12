---
name: b9-prod-read-before-edit
description: Prod promoted — read_file before patch (READ_STATE_REQUIRED)
version: 1
triggers:
  - READ_STATE_REQUIRED
  - read before edit
  - greet.py
preferred_tools:
  - read_file
  - patch
  - run_pytest
---

# Prod: read before edit

Production delegate failed with `READ_STATE_REQUIRED` — patch/write without prior read_file.

1. `read_file test_b9.py` — confirm expected behavior.
2. `read_file greet.py` (or target module) — capture exact content for patch old_string.
3. `patch` target file only.
4. `run_pytest` until green.

Never patch or write_file before read_file on the same path.
