"""Local data query tool — run SQL on CSV/JSON/Parquet files via duckdb (optional extra [analytics])."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAX_ROWS = 200
_MAX_OUTPUT_CHARS = 32_000

_QUERYABLE_EXTENSIONS = frozenset({".csv", ".tsv", ".json", ".jsonl", ".parquet", ".db", ".sqlite"})

_WRITE_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|MERGE|GRANT|REVOKE|EXEC|EXECUTE|CALL|COPY|LOAD|IMPORT|EXPORT)\b",
    re.IGNORECASE,
)

_DANGEROUS_FUNCTIONS = re.compile(
    r"\b(read_csv_auto|read_csv|read_json_auto|read_json|read_parquet|read_text|"
    r"read_blob|read_ndjson|ATTACH|DETACH|read_csv_objects|glob|pragma_|"
    r"query_table|httpfs|s3_|hf_|azure_)\b",
    re.IGNORECASE,
)


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
    """Resolve and validate a data file path within workspace via path_safety."""
    from butler.tools.path_safety import check_tool_path

    safety = check_tool_path(path, for_write=False)
    if not safety.allowed:
        logger.warning("data_query path rejected: %s — %s", path, safety.error)
        return None

    p = safety.path
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

    if _WRITE_KEYWORDS.search(query):
        match = _WRITE_KEYWORDS.search(query)
        return json.dumps({"error": f"write operations not allowed: {match.group(1).upper()}"})

    if _DANGEROUS_FUNCTIONS.search(query):
        match = _DANGEROUS_FUNCTIONS.search(query)
        return json.dumps({
            "error": f"direct file access functions not allowed in SQL: {match.group(1)}",
            "hint": "use the 'file' parameter to specify data source",
        })

    cap = min(max(10, int(max_rows or _MAX_ROWS)), 1000)

    import duckdb  # type: ignore[import-untyped]

    target = (file or "").strip()
    if not target:
        return json.dumps({"error": "file parameter is required", "hint": "specify a data file path"})

    con = None
    try:
        con = duckdb.connect(":memory:", read_only=False)

        if target:
            p = _resolve_project_path(target)
            if p is None:
                return json.dumps({"error": f"file not found or unsupported: {target}"})

            safe_path = str(p)
            ext = p.suffix.lower()
            if ext in (".db", ".sqlite"):
                con.execute("ATTACH ? AS src (TYPE sqlite, READ_ONLY)", [safe_path])
                con.execute("USE src")
            elif ext in (".csv", ".tsv"):
                sep = "\t" if ext == ".tsv" else ","
                con.execute(
                    "CREATE TABLE data AS SELECT * FROM read_csv_auto(?, delim=?)",
                    [safe_path, sep],
                )
            elif ext in (".json", ".jsonl"):
                con.execute(
                    "CREATE TABLE data AS SELECT * FROM read_json_auto(?)",
                    [safe_path],
                )
            elif ext == ".parquet":
                con.execute(
                    "CREATE TABLE data AS SELECT * FROM read_parquet(?)",
                    [safe_path],
                )

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
        logger.warning("data_query execution error: %s", exc)
        return json.dumps({"error": f"query failed: {exc}"})
    finally:
        if con is not None:
            try:
                con.close()
            except Exception as exc:
                logger.debug("tool query data skipped: %s", exc)
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
            "required": ["sql", "file"],
        },
        handler=tool_query_data,
        toolset="analytics",
    )


__all__ = ["register_data_query_tools", "tool_query_data"]
