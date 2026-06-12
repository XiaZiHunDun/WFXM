---
name: b9-add-missing-method
description: B9 Tier-1 — add Store.get and fix __init__/put on store.py
version: 1
triggers:
  - add_missing_method
  - Store.get
  - store.py
preferred_tools:
  - read_file
  - patch
  - write_file
  - run_pytest
---

# B9: add missing method (Store)

When `test_b9.py` uses `Store().put('a', 1)` then `get('a') == 1` but `store.py` lacks `get`:

1. `read_file test_b9.py` — note required API.
2. `read_file store.py` — only `put()` exists; may overwrite `_data` incorrectly.
3. `patch store.py`:
   - add `__init__` with `self._data = {}`
   - fix `put` to `self._data[k] = v`
   - add `get(self, k)` returning `self._data.get(k)`
4. `run_pytest` until green.

Do not edit `test_b9.py`.
