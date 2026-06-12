---
name: b9-fix-exception-handler
description: B9 Tier-1 — narrow bare except so ValueError propagates
version: 1
triggers:
  - fix_exception_handler
  - bare except
  - parser.py
  - pytest.raises
preferred_tools:
  - read_file
  - patch
  - run_pytest
---

# B9: fix exception handler

When `test_b9.py` expects `pytest.raises(ValueError)` but `parser.py` uses bare `except: return None`:

1. `read_file test_b9.py` — confirm `ValueError` must propagate.
2. `read_file parser.py` — find bare `except:` swallowing errors.
3. `patch parser.py` — replace with `except ValueError:\n        raise` (or re-raise after handling).
4. `run_pytest` until green.

Do not edit `test_b9.py`. If test says DID NOT RAISE, the handler still swallows `ValueError`.
