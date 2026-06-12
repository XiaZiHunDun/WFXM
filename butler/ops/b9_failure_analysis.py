"""Classify B9 LIVE failures for tuning (no patch vs wrong patch vs verify gap)."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


def classify_b9_failure(
    *,
    task_id: str,
    passed: bool,
    tools_used: list[str] | None,
    failure_reasons: list[str] | None,
) -> str:
    if passed:
        return "passed"
    tools = {str(t).strip().lower() for t in (tools_used or []) if t}
    reasons = " ".join(failure_reasons or []).lower()
    has_patch = "patch" in tools or "write_file" in tools
    has_verify = "terminal" in tools or "run_pytest" in tools or "dev_verify" in tools
    if not has_patch:
        return "no_edit"
    if has_patch and has_verify and ("failed" in reasons or "error" in reasons):
        return "wrong_patch"
    if has_patch and not has_verify:
        return "patch_no_verify"
    if "modulenotfounderror" in reasons or "importerror" in reasons:
        return "import_fix_incomplete"
    if "assert" in reasons:
        return "logic_fix_incomplete"
    return "other_fail"


def analyze_b9_live_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize a B9 LIVE result list (from report.to_dict or audit JSON)."""
    rows: list[dict[str, Any]] = []
    by_class: dict[str, int] = {}
    for r in results:
        cls = classify_b9_failure(
            task_id=str(r.get("task_id") or ""),
            passed=bool(r.get("passed")),
            tools_used=list(r.get("tools_used") or []),
            failure_reasons=list(r.get("failure_reasons") or []),
        )
        by_class[cls] = by_class.get(cls, 0) + 1
        rows.append({
            "task_id": r.get("task_id"),
            "passed": r.get("passed"),
            "classification": cls,
            "tools_used": r.get("tools_used") or [],
            "failure_snippet": (r.get("failure_reasons") or [""])[0][:200],
        })
    return {
        "total": len(results),
        "passed": sum(1 for r in results if r.get("passed")),
        "by_classification": by_class,
        "tasks": rows,
    }


def analyze_probe_tasks(results: list[dict[str, Any]]) -> dict[str, Any]:
    from butler.dev_engine.b9_live_tuning import B9_TUNING_PROBE_TASK_IDS

    wanted = set(B9_TUNING_PROBE_TASK_IDS)
    subset = [r for r in results if r.get("task_id") in wanted]
    return analyze_b9_live_results(subset)


def _failure_signature(text: str) -> str:
    """Normalize failure text into a coarse bucket for mining."""
    t = (text or "").lower()
    code_m = re.search(r"code:\s*([A-Z0-9_]+)", text or "")
    if code_m:
        return f"code:{code_m.group(1)}"
    if "read_state_required" in t or "必须先调用 read_file" in text:
        return "code:READ_STATE_REQUIRED"
    if "not in the allowlist" in t or "terminal command is not" in t:
        return "code:TERMINAL_NOT_ALLOWED"
    if "modulenotfounderror" in t or "no module named" in t:
        m = re.search(r"no module named ['\"]?(\w+)['\"]?", t)
        return f"import:{m.group(1) if m else 'unknown'}"
    if "assert" in t and "==" in text:
        m = re.search(r"assert\s+(.{0,40})==", text)
        return f"assert:{m.group(1).strip() if m else 'expr'}"
    if "assertionerror" in t:
        return "assertionerror"
    if "typeerror" in t:
        return "typeerror"
    if "syntaxerror" in t:
        return "syntaxerror"
    return "other"


def mine_delegate_failure_signatures(
    *,
    limit: int = 200,
    min_count: int = 3,
) -> dict[str, Any]:
    """Mine top B9-benchmark failure signatures from delegate_failures audit."""
    from butler.config import get_butler_home

    path = get_butler_home() / "audit" / "delegate_failures.jsonl"
    if not path.is_file():
        return {"total": 0, "signatures": [], "audit_path": str(path)}

    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        preview = str(rec.get("task_preview") or "")
        if "b9-benchmark" not in preview and "B9L" not in preview:
            continue
        issues = rec.get("issues") or []
        blob = " ".join(str(i) for i in issues) + " " + preview
        sig = _failure_signature(blob)
        rows.append({
            "signature": sig,
            "failure_reason": rec.get("failure_reason"),
            "task_preview": preview[:120],
        })

    counts = Counter(r["signature"] for r in rows)
    top = [
        {"signature": sig, "count": cnt}
        for sig, cnt in counts.most_common()
        if cnt >= min_count
    ]
    return {
        "total": len(rows),
        "signatures": top,
        "audit_path": str(path),
        "samples": rows[-5:],
    }


__all__ = [
    "analyze_b9_live_results",
    "analyze_probe_tasks",
    "classify_b9_failure",
    "mine_delegate_failure_signatures",
]
