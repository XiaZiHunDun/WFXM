---
name: b9-trim-return
description: B9 Tier-1 — trim padded f-string return with strip()
version: 1
triggers:
  - prod_no_test
  - formatter.py
  - label(
  - strip()
preferred_tools:
  - read_file
  - patch
  - run_pytest
---

# B9: trim return value

When `test_b9.py` expects `label('ok') == 'ok'` but `formatter.py` returns a padded f-string:

1. `read_file test_b9.py` — confirm exact expected string.
2. `read_file formatter.py` — find return with extra spaces/padding.
3. `patch formatter.py` — append `.strip()` on the f-string return expression.
4. `run_pytest` until green.

Do not edit `test_b9.py`. Avoid only reading files without patching.
