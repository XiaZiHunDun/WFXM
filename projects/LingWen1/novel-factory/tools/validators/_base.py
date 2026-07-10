"""Shared CLI + jsonschema runner for novel-factory Agent output validators.

Each agent (灵感/作家/审核) ships a sibling ``*.schema.json`` plus a thin
``validate_<agent>.py`` that delegates here. This base module owns:

  - schema lookup (default root = directory of this file)
  - Draft 2020-12 validator construction
  - error flattening with path-qualified messages
  - exit-code formatting (0 ok / 1 validation errors / 2 missing schema or dep)

Per-file load failures (YAML parse error, broken markdown, missing required
field before validation) are returned as errors rather than raised, so a
single bad file in a batch doesn't mask the others.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

import jsonschema

SCHEMA_ROOT = Path(__file__).resolve().parent

LoadFn = Callable[[Path], Any]


class ValidationFailure(Exception):
    """Raised when a single file cannot even be loaded (parse / IO / structure)."""


def run_validator(
    schema_name: str,
    paths: Sequence[Path],
    *,
    load_fn: LoadFn,
    schema_root: Path = SCHEMA_ROOT,
) -> list[str]:
    """Validate ``paths`` against ``<schema_root>/<schema_name>.schema.json``.

    Returns flat error list (``"<path>: <msg>"`` per failure). Empty list = OK.
    Raises SystemExit(2) only when schema file is missing (config bug).
    """
    schema_path = schema_root / f"{schema_name}.schema.json"
    if not schema_path.is_file():
        raise SystemExit(f"[validator] missing schema: {schema_path}")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    all_errors: list[str] = []
    for p in paths:
        try:
            data = load_fn(p)
        except ValidationFailure as exc:
            all_errors.append(f"{p}: {exc}")
        except Exception as exc:
            all_errors.append(f"{p}: 解析失败: {exc}")
            continue
        for e in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
            path_repr = "/".join(str(x) for x in e.absolute_path) or "(root)"
            all_errors.append(f"{p}: {path_repr}: {e.message}")
    return all_errors


def format_cli_errors(errors: list[str], *, quiet_success: bool, n_files: int) -> int:
    """Standard exit-code formatter; returns 0/1 for ``sys.exit(...)``."""
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        print(
            f"\n✗ {len(errors)} error(s) across {n_files} file(s)",
            file=sys.stderr,
        )
        return 1
    if not quiet_success:
        print(f"✓ {n_files} file(s) validated")
    return 0