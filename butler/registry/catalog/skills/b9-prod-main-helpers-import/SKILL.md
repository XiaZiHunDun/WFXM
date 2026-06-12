---
name: b9-prod-main-helpers-import
description: Prod promoted — fix main.py import to match helpers.py
version: 1
triggers:
  - main.py
  - helpers.py
  - production import
preferred_tools:
  - list_directory
  - read_file
  - patch
  - run_pytest
---

# Prod: main.py helpers import

Production failure: `main.py` imports `helper` but file is `helpers.py`.

1. `list_directory .` — confirm `helpers.py` exists.
2. `read_file main.py` — find wrong `from helper import ...`.
3. `patch main.py` — `from helpers import run` (match filename).
4. `run_pytest` — prefer over raw terminal in benchmark workspace.

Do not use paths outside the bound workspace.
