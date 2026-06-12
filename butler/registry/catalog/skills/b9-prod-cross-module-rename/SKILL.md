---
name: b9-prod-cross-module-rename
description: Prod promoted — rename getData to get_data across pkg module
version: 1
triggers:
  - cross_module_rename
  - getData
  - pkg/client.py
preferred_tools:
  - read_file
  - patch
  - run_pytest
---

# Prod: cross-module method rename

Production failure: test expects `get_data` but `Client` still has `getData`.

1. `read_file pkg/client.py` and `test_b9.py`.
2. `read_file pkg/__init__.py` if exports reference the old name.
3. `patch pkg/client.py` — rename `getData` → `get_data`.
4. `run_pytest` until green.

read_file before patch (READ_STATE). Do not edit `test_b9.py`.
