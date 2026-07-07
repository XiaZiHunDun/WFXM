"""Local data query best-effort helpers (P0-A)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def apply_statement_timeout_safe(con: Any, *, timeout_seconds: int) -> None:
    def _run() -> None:
        con.execute(f"SET statement_timeout='{timeout_seconds}s'")

    safe_best_effort(_run, label="data_query.statement_timeout", default=None)


def close_duckdb_connection_safe(con: Any) -> None:
    def _run() -> None:
        con.close()

    safe_best_effort(_run, label="data_query.close", default=None)


def execute_readonly_duckdb_query(
    *,
    query: str,
    target: str,
    cap: int,
    max_output_chars: int,
    resolve_path: Any,
    queryable_extensions: frozenset[str],
) -> str:
    import duckdb

    con = None
    try:
        con = duckdb.connect(":memory:")
        apply_statement_timeout_safe(con, timeout_seconds=30)

        p = resolve_path(target)
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
        elif ext not in queryable_extensions:
            return json.dumps({"error": f"file not found or unsupported: {target}"})

        result = con.execute(query).fetchdf()
        if len(result) > cap:
            result = result.head(cap)
            truncated = True
        else:
            truncated = False

        text = result.to_string(index=False, max_rows=cap)
        if len(text) > max_output_chars:
            text = text[:max_output_chars] + "\n…(truncated)"

        columns = list(result.columns)
        return json.dumps(
            {
                "ok": True,
                "columns": columns,
                "rows": len(result),
                "truncated": truncated,
                "text": text,
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.warning("data_query execution error: %s", exc)
        err_msg = str(exc)
        if len(err_msg) > 200:
            err_msg = err_msg[:200] + "…"
        return json.dumps({"error": f"query failed: {err_msg}"})
    finally:
        if con is not None:
            close_duckdb_connection_safe(con)
