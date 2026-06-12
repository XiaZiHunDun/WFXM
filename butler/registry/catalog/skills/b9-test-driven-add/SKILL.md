---
name: b9-test-driven-add
description: B9 Tier-1 — implement missing function from test_b9.py (test-driven add)
version: 1
triggers:
  - test_driven_add
  - ping
  - pong
  - service.py
preferred_tools:
  - read_file
  - write_file
  - patch
  - run_pytest
  - list_directory
---

# B9: test-driven add (ping → pong)

When `test_b9.py` imports `ping` from `service.py` and expects `'pong'`:

1. `read_file test_b9.py` — note the symbol and expected return value.
2. `read_file service.py` — confirm the function is missing or wrong.
3. `write_file` or `patch service.py` — add:

   ```python
   def ping():
       return 'pong'
   ```

4. `run_pytest` (preferred) or `terminal`: `python3 -m pytest test_b9.py -q` until green.

Do not edit `test_b9.py`. If you see ImportError for `ping`, the implementation file still lacks that function.
