---
name: b9-swe-event-unsubscribe
description: SWE-014 — EventBus.on must return unsubscribe callable
version: 1
triggers:
  - SWE-014
  - EventBus
  - unsubscribe
  - events.py
preferred_tools:
  - read_file
  - patch
  - terminal
---

# SWE-014: EventBus.on returns unsubscribe

Issue: `EventBus.on(event, callback)` must return a callable `unsubscribe()` that removes the callback from `self._listeners[event]`.

Workflow:

1. `read_file events.py` — locate `EventBus.on`.
2. `patch events.py` — after appending callback, define and return unsubscribe:

```python
        def unsubscribe():
            try:
                self._listeners[event].remove(callback)
            except (KeyError, ValueError):
                pass
        return unsubscribe
```

3. `terminal`: `python -m pytest _swe_test.py -q` until green.

Do not change `_swe_test.py`. Do not `write_file` the whole `events.py` — `patch` inside `on()` only. The return value of `on()` must be callable.
