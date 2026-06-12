---
name: b9-swe-priority-queue
description: SWE-015 — PriorityQueue.pop returns highest priority (min number) first
version: 1
triggers:
  - SWE-015
  - PriorityQueue
  - queue.py
preferred_tools:
  - read_file
  - patch
  - terminal
---

# SWE-015: priority queue pop order

Issue: `PriorityQueue.pop()` must return the item with the **lowest** priority number (min-heap behavior).

Workflow:

1. `read_file queue.py` — locate `PriorityQueue.pop`.
2. `patch queue.py` — in `pop()`, keep `self._items.sort()` but change `self._items.pop()[1]` to `self._items.pop(0)[1]`.
3. `terminal`: `python -m pytest _swe_test.py -q` until green.

Do not edit `_swe_test.py`. After ascending sort, index 0 is the lowest priority number (highest priority item). `pop()` without index removes the last element — that is the bug.
