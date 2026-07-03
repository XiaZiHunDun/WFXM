"""Local data query tool — run SQL on CSV/JSON/Parquet files via duckdb (optional extra [analytics])."""

from __future__ import annotations

import json
import logging
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


def _strip_sql_comments(sql: str) -> str:
    """Remove SQL comments to prevent keyword check bypass."""
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return sql


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

    normalized = _strip_sql_comments(query)

    if _WRITE_KEYWORDS.search(normalized):
        match = _WRITE_KEYWORDS.search(normalized)
        return json.dumps({"error": f"write operations not allowed: {match.group(1).upper()}"})

    if _DANGEROUS_FUNCTIONS.search(normalized):
        match = _DANGEROUS_FUNCTIONS.search(normalized)
        return json.dumps({
            "error": f"direct file access functions not allowed in SQL: {match.group(1)}",
            "hint": "use the 'file' parameter to specify data source",
        })

    cap = min(max(10, int(max_rows if max_rows is not None else _MAX_ROWS)), 1000)

    target = (file or "").strip()
    if not target:
        return json.dumps({"error": "file parameter is required", "hint": "specify a data file path"})

    from butler.tools.data_query_ops import execute_readonly_duckdb_query

    return execute_readonly_duckdb_query(
        query=query,
        target=target,
        cap=cap,
        max_output_chars=_MAX_OUTPUT_CHARS,
        resolve_path=_resolve_project_path,
        queryable_extensions=_QUERYABLE_EXTENSIONS,
    )


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
