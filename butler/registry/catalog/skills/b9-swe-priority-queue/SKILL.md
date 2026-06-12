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
2. `patch queue.py` — select entry with minimum `priority` before removing from `_items`.
3. `terminal`: `python -m pytest _swe_test.py -q` until green.

Do not edit `_swe_test.py`. Higher priority means lower numeric priority value.
