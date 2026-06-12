---
name: b9-extract-constant
description: B9 Tier-1 — extract shared constant to constants.py and fix app import
version: 1
triggers:
  - extract_constant
  - MAX_RETRIES
  - constants.py
preferred_tools:
  - read_file
  - write_file
  - patch
  - run_pytest
  - list_directory
---

# B9: extract constant

When `test_b9.py` imports `MAX_RETRIES` from `app.py` but the constant should live in `constants.py`:

1. `read_file test_b9.py` — confirm expected symbol and value.
2. `read_file app.py` — locate `MAX_RETRIES = …` definition.
3. `write_file constants.py` — e.g. `MAX_RETRIES = 3`.
4. `patch app.py` — replace inline definition with `from constants import MAX_RETRIES`.
5. `run_pytest` until green.

Do not edit `test_b9.py`.
