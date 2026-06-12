---
name: b9-fix-import
description: B9 Tier-2 — fix wrong import module name to match helpers.py
version: 1
triggers:
  - multi_file_import
  - wrong import
  - helpers.py
  - main.py
preferred_tools:
  - list_directory
  - read_file
  - patch
  - run_pytest
---

# B9: fix import module name

When `main.py` imports from `helper` but the file is `helpers.py`:

1. `list_directory .` — confirm `helpers.py` exists (not `helper.py`).
2. `read_file main.py` — find `from helper import ...`.
3. `patch main.py` — change to `from helpers import run` (module name must match filename).
4. `run_pytest` until green.

Do not rename files; fix the import line only.
