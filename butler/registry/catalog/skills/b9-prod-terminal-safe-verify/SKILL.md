---
name: b9-prod-terminal-safe-verify
description: Prod — avoid terminal semicolons; prefer read_file idempotent verify
version: 1
triggers:
  - Shell metacharacters
  - TOOL_ERROR
  - terminal
  - python3 -c
  - lingwen-prod-sample
preferred_tools:
  - read_file
  - patch
  - terminal
---

# Prod: terminal-safe verify (LingWen / patch-only)

Production delegate failed when `terminal` rejected shell metacharacters (e.g. `;` in `python3 -c "..."`).

## Rules

1. **Prefer read_file** to confirm state (docstring present, `return a + b` in source, constant values).
2. If task is **idempotent** and file already correct → report **VERIFIED** in headline; **no patch, no terminal**.
3. **terminal** only for single commands **without** `;`, `&&`, `|`, `cd`, or `bash -c`:
   - OK: `python3 novel-factory/scripts/validate_progress.py`
   - BAD: `python3 -c "import x; assert y"`
4. Under `lingwen-prod-sample`: **patch only** — `write_file` / `delete_file` denied.

## constants.py example

1. `read_file constants.py`
2. If module docstring missing → `patch` to prepend one-line docstring before `MAX_RETRIES`.
3. If docstring exists and `MAX_RETRIES == 3` → VERIFIED (no terminal).

## demo/hello.py example

1. `read_file demo/hello.py`
2. Confirm `return a + b` in `add()` → VERIFIED. No terminal, no edits.
