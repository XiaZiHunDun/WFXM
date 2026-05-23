"""Production corpus ops + live archive summarization for wechat_real.lw_real."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

from tests.corpus.harness.gateway_catalog import (
    _LW_REAL_DIR,
    load_production_strict_catalog,
    load_production_utterance_catalog,
    load_reference_strict_catalog,
)
from tests.corpus.harness.gateway_meta import load_gateway_meta

_PRODUCTION_PATH = _LW_REAL_DIR / "production_utterance_catalog.yaml"
_RUNS_DIR = Path(__file__).resolve().parents[1] / "archive" / "runs"
_PROD_ID_RE = re.compile(r"^PROD-(\d+)$")


def production_inventory() -> dict[str, Any]:
    rows = load_production_utterance_catalog()
    promoted = [
        r
        for r in load_reference_strict_catalog()
        if r.get("promoted_from") or str(r.get("source_file", "")).startswith("promoted-from:")
    ]
    return {
        "production_count": len(rows),
        "production_strict_count": len(load_production_strict_catalog()),
        "promoted_count": len(promoted),
        "promoted_from_ids": sorted(
            {str(r.get("promoted_from") or "") for r in promoted if r.get("promoted_from")}
        ),
    }


def next_production_id() -> str:
    nums = []
    for row in load_production_utterance_catalog():
        m = _PROD_ID_RE.match(str(row.get("id", "")))
        if m:
            nums.append(int(m.group(1)))
    n = max(nums, default=0) + 1
    return f"PROD-{n:03d}"


def validate_production_ops() -> list[str]:
    errors: list[str] = []
    meta = load_gateway_meta()
    ops = meta.get("production_ops") or {}
    for key in ("ops_doc", "promote_script", "append_script", "summary_script"):
        rel = ops.get(key)
        if not rel:
            errors.append(f"production_ops.{key} missing in meta.yaml")
            continue
        if not (Path(__file__).resolve().parents[3] / rel).is_file():
            errors.append(f"production_ops.{key} file not found: {rel}")

    ids = [r.get("id") for r in load_production_utterance_catalog()]
    if len(ids) != len(set(ids)):
        errors.append("production catalog: duplicate ids")

    for row in load_reference_strict_catalog():
        pf = row.get("promoted_from")
        if pf and pf not in ids:
            errors.append(f"strict {row.get('id')}: promoted_from unknown {pf}")

    targets = meta.get("targets") or {}
    inv = production_inventory()
    if inv["production_count"] < int(targets.get("production", 0)):
        errors.append(
            f"production count {inv['production_count']} < target {targets['production']}"
        )
    return errors


def iter_archive_records(
    *,
    runs_dir: Path | None = None,
    suite_id: str | None = None,
) -> list[dict[str, Any]]:
    runs_dir = runs_dir or _RUNS_DIR
    if not runs_dir.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(runs_dir.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if suite_id and row.get("suite_id") != suite_id:
                continue
            row["_archive_file"] = path.name
            rows.append(row)
    return rows


def summarize_archive(
    *,
    suite_id: str | None = "wechat_real.lw_real",
    runs_dir: Path | None = None,
) -> dict[str, Any]:
    records = iter_archive_records(runs_dir=runs_dir, suite_id=suite_id)
    total = len(records)
    passed = sum(1 for r in records if r.get("status") == "passed")
    failed = total - passed
    by_fail = Counter(r.get("fail_type") or "—" for r in records if r.get("status") != "passed")
    by_dim = Counter(r.get("dimension") or "—" for r in records)
    by_case_fail = [
        r for r in records if r.get("status") != "passed"
    ]
    run_ids = sorted({str(r.get("run_id", "")) for r in records if r.get("run_id")})
    return {
        "suite_id": suite_id,
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / total, 3) if total else None,
        "run_ids": run_ids,
        "fail_by_type": dict(by_fail),
        "cases_by_dimension": dict(by_dim),
        "failed_cases": by_case_fail[:20],
    }


def format_ops_markdown(summary: dict[str, Any], *, inventory: dict[str, Any] | None = None) -> str:
    inv = inventory or production_inventory()
    lines = [
        "## 微信语料运营快照",
        "",
        "### Production 池",
        "",
        f"| 指标 | 值 |",
        f"|------|-----|",
        f"| production 条数 | {inv['production_count']} |",
        f"| 已升格 (REF-PROMO-*) | {inv['promoted_count']} |",
        "",
    ]
    if inv["promoted_from_ids"]:
        lines.append(f"已升格来源：`{', '.join(inv['promoted_from_ids'][:10])}`")
        if len(inv["promoted_from_ids"]) > 10:
            lines.append(f"… 共 {len(inv['promoted_from_ids'])} 条")
        lines.append("")

    lines.extend(
        [
            "### Live 归档（gateway）",
            "",
            f"| 指标 | 值 |",
            f"|------|-----|",
            f"| 归档条数 | {summary['total']} |",
            f"| 通过 | {summary['passed']} |",
            f"| 失败 | {summary['failed']} |",
            f"| 通过率 | {summary['pass_rate']!s} |",
            f"| run_id | {', '.join(summary['run_ids'][:5]) or '—'} |",
            "",
        ]
    )
    if summary["fail_by_type"]:
        lines.append("### 失败分类")
        lines.append("")
        for k, v in sorted(summary["fail_by_type"].items(), key=lambda x: -x[1]):
            lines.append(f"- **{k}**: {v}")
        lines.append("")

    if summary["failed_cases"]:
        lines.append("### 代表失败用例")
        lines.append("")
        lines.append("| case_id | fail_type | excerpt |")
        lines.append("|---------|-----------|---------|")
        for r in summary["failed_cases"][:10]:
            excerpt = (r.get("response_excerpt") or "")[:80].replace("|", "/")
            lines.append(
                f"| {r.get('case_id', '?')} | {r.get('fail_type', '—')} | {excerpt} |"
            )
        lines.append("")

    return "\n".join(lines)
