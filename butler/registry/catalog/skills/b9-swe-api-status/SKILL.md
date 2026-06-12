---
name: b9-swe-api-status
description: SWE-013 — make_response must set status ok/error from HTTP code
version: 1
triggers:
  - SWE-013
  - make_response
  - api/response.py
preferred_tools:
  - read_file
  - patch
  - terminal
---

# SWE-013: API response status field

Issue: `make_response(data, code)` must include `status: "ok"` when `code < 400`, else `status: "error"`.

Workflow:

1. `read_file api/response.py` — locate `make_response`.
2. `patch api/response.py` — add status based on code, e.g.:

```python
    status = "ok" if code < 400 else "error"
    return {"data": data, "code": code, "status": status}
```

3. `terminal`: `python -m pytest _swe_test.py -q` until green.

Do not edit `_swe_test.py`.
