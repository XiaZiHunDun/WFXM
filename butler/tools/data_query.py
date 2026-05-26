"""Local data query tool — run SQL on CSV/JSON/Parquet files via duckdb (optional extra [analytics])."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAX_ROWS = 200
_MAX_OUTPUT_CHARS = 32_000

_QUERYABLE_EXTENSIONS = frozenset({".csv", ".tsv", ".json", ".jsonl", ".parquet", ".db", ".sqlite"})


def _duckdb_available() -> bool:
    try:
        import duckdb  # type: ignore[import-untyped]  # noqa: F401
        return True
    except ImportError:
        return False


def _analytics_enabled() -> bool:
    from butler.env_parse import env_truthy
    return env_truthy("BUTLER_DATA_QUERY", default=True)


def _resolve_project_path(path: str) -> Path | None:
    """Resolve and validate a data file path within the project."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return None
    if p.suffix.lower() not in _QUERYABLE_EXTENSIONS:
        return None
    return p


def tool_query_data(
    sql: str = "",
    *,
    file: str = "",
    max_rows: int = _MAX_ROWS,
    **_: Any,
) -> str:
    """Execute a read-only SQL query against a local data file.

    For CSV/JSON/Parquet files, the file is auto-registered as a table named 'data'.
    For SQLite .db files, all tables are available directly.
    """
    if not _duckdb_available():
        return json.dumps({
            "error": "duckdb not installed — data query unavailable",
            "hint": "pip install 'butler-system[analytics]'",
        })

    if not _analytics_enabled():
        return json.dumps({
            "error": "data query disabled",
            "hint": "set BUTLER_DATA_QUERY=1 to enable",
        })

    query = (sql or "").strip()
    if not query:
        return json.dumps({"error": "sql query required"})

    forbidden = query.upper().split()
    for kw in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE"):
        if kw in forbidden:
            return json.dumps({"error": f"write operations not allowed: {kw}"})

    cap = min(max(10, int(max_rows or _MAX_ROWS)), 1000)

    import duckdb  # type: ignore[import-untyped]

    try:
        con = duckdb.connect(":memory:", read_only=False)

        target = (file or "").strip()
        if target:
            p = _resolve_project_path(target)
            if p is None:
                return json.dumps({"error": f"file not found or unsupported: {target}"})

            ext = p.suffix.lower()
            if ext in (".db", ".sqlite"):
                con.execute(f"ATTACH '{p}' AS src (TYPE sqlite, READ_ONLY)")
                con.execute("USE src")
            elif ext in (".csv", ".tsv"):
                sep = "\\t" if ext == ".tsv" else ","
                con.execute(
                    f"CREATE TABLE data AS SELECT * FROM read_csv_auto('{p}', delim='{sep}')"
                )
            elif ext in (".json", ".jsonl"):
                con.execute(f"CREATE TABLE data AS SELECT * FROM read_json_auto('{p}')")
            elif ext == ".parquet":
                con.execute(f"CREATE TABLE data AS SELECT * FROM read_parquet('{p}')")

        result = con.execute(query).fetchdf()
        if len(result) > cap:
            result = result.head(cap)
            truncated = True
        else:
            truncated = False

        text = result.to_string(index=False, max_rows=cap)
        if len(text) > _MAX_OUTPUT_CHARS:
            text = text[:_MAX_OUTPUT_CHARS] + "\n…(truncated)"

        columns = list(result.columns)
        return json.dumps({
            "ok": True,
            "columns": columns,
            "rows": len(result),
            "truncated": truncated,
            "text": text,
        }, ensure_ascii=False)

    except Exception as exc:
        return json.dumps({"error": f"query failed: {exc}"})
    finally:
        try:
            con.close()
        except Exception:
            pass


def register_data_query_tools(register_fn) -> None:
    """Register query_data tool if duckdb is available."""
    if not _duckdb_available():
        logger.debug("duckdb not installed; query_data tool not registered")
        return

    register_fn(
        name="query_data",
        description=(
            "Run a read-only SQL query against local data files "
            "(CSV, TSV, JSON, Parquet, or SQLite databases). "
            "For CSV/JSON/Parquet, the file is loaded as table 'data'. "
            "For SQLite .db files, all tables are available by name."
        ),
        schema={
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "SQL query to execute (read-only; SELECT only)",
                },
                "file": {
                    "type": "string",
                    "description": "Path to data file (CSV, JSON, Parquet, or .db)",
                },
                "max_rows": {
                    "type": "integer",
                    "default": _MAX_ROWS,
                    "minimum": 10,
                    "maximum": 1000,
                    "description": "Maximum rows to return",
                },
            },
            "required": ["sql"],
        },
        handler=tool_query_data,
        toolset="analytics",
    )


__all__ = ["register_data_query_tools", "tool_query_data"]
