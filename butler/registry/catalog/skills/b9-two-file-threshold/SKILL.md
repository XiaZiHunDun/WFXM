---
name: b9-two-file-threshold
description: B9 Tier-1 — fix filter behavior by patching config constant THRESHOLD (not filter.py)
version: 1
triggers:
  - threshold
  - config.py
  - two file patch
  - keep(5)
preferred_tools:
  - read_file
  - patch
  - terminal
  - list_directory
---

# B9: two-file threshold fix

When `test_b9.py` expects `keep(5)` to be False and `keep(15)` True:

1. `read_file test_b9.py` — confirm expected predicate.
2. `read_file config.py` — locate `THRESHOLD` (used by `filter.py`).
3. `patch config.py` — lower `THRESHOLD` so `keep(5)` becomes False (e.g. 10 → 5).
4. `terminal`: `python3 -m pytest test_b9.py -q` until green.

Do not edit `test_b9.py`. Prefer patching the constant in `config.py` over rewriting `filter.py` logic.
