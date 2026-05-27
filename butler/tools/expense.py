"""Personal expense tracker — cross-project income/expense logging.

Records are tenant-scoped, stored under
``~/.butler/tenants/<tenant>/expenses/`` as one JSON file per entry.

Core value is numeric aggregation: monthly totals, category breakdowns,
and period comparisons — not individual record browsing.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_CN_TZ = timezone(timedelta(hours=8))
_MAX_RECORDS = 5000

_VALID_DIRECTIONS = frozenset({"income", "expense"})
_VALID_CATEGORIES = frozenset({
    "food", "transport", "housing", "medical", "entertainment",
    "shopping", "education", "social", "salary", "investment", "other",
})
_CATEGORY_LABELS = {
    "food": "餐饮", "transport": "交通", "housing": "住房",
    "medical": "医疗", "entertainment": "娱乐", "shopping": "购物",
    "education": "教育", "social": "社交", "salary": "薪资",
    "investment": "投资", "other": "其他",
}
_DIR_LABELS = {"income": "收入", "expense": "支出"}


from butler.tools.tenant_store import TenantStore

_store = TenantStore("expenses", env_toggle="BUTLER_EXPENSE_ENABLED")


def _expense_enabled() -> bool:
    return _store.enabled()


def _expenses_dir() -> Path:
    return _store.storage_dir()


def _save_record(record: dict[str, Any]) -> Path:
    d = _expenses_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{record['id']}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _load_all() -> list[dict[str, Any]]:
    d = _expenses_dir()
    if not d.is_dir():
        return []
    result: list[dict[str, Any]] = []
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "id" in data:
                result.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return result


def _delete_record(rid: str) -> bool:
    path = _expenses_dir() / f"{rid}.json"
    if path.is_file():
        path.unlink()
        return True
    return False


def _normalize_category(raw: Any) -> str:
    val = str(raw or "").strip().lower()
    return val if val in _VALID_CATEGORIES else "other"


def _normalize_direction(raw: Any) -> str:
    val = str(raw or "").strip().lower()
    return val if val in _VALID_DIRECTIONS else "expense"


def _today_str() -> str:
    return datetime.now(_CN_TZ).strftime("%Y-%m-%d")


def _parse_date(raw: str) -> str:
    """Accept YYYY-MM-DD or return today."""
    s = (raw or "").strip()
    if not s:
        return _today_str()
    try:
        datetime.strptime(s[:10], "%Y-%m-%d")
        return s[:10]
    except ValueError:
        return _today_str()


def _month_range(year: int, month: int) -> tuple[str, str]:
    start = f"{year:04d}-{month:02d}-01"
    if month == 12:
        end = f"{year + 1:04d}-01-01"
    else:
        end = f"{year:04d}-{month + 1:02d}-01"
    return start, end


def _filter_by_period(
    records: list[dict[str, Any]],
    start: str,
    end: str,
) -> list[dict[str, Any]]:
    return [r for r in records if start <= r.get("date", "") < end]


# ── Tool Handlers ──────────────────────────────────────────────


def tool_expense_add(
    amount: Any,
    description: str = "",
    category: str = "",
    direction: str = "expense",
    date: str = "",
    tags: Any = None,
    **_: Any,
) -> str:
    if not _expense_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_EXPENSE_ENABLED=0"})

    try:
        amt = round(float(amount), 2)
    except (TypeError, ValueError):
        return json.dumps({"ok": False, "error": "amount must be a number"})
    if amt <= 0:
        return json.dumps({"ok": False, "error": "amount must be positive"})

    total = len(_load_all())
    if total >= _MAX_RECORDS:
        return json.dumps({
            "ok": False,
            "error": f"Record limit reached ({_MAX_RECORDS}). Delete old records first.",
        })

    now = time.time()
    rid = uuid.uuid4().hex[:10]
    record_date = _parse_date(date)
    cat = _normalize_category(category)
    dirn = _normalize_direction(direction)

    tags_list: list[str] = []
    if tags:
        if isinstance(tags, str):
            tags_list = [t.strip() for t in tags.replace("，", ",").split(",") if t.strip()]
        elif isinstance(tags, list):
            tags_list = [str(t).strip() for t in tags if str(t).strip()]

    record: dict[str, Any] = {
        "id": rid,
        "amount": amt,
        "direction": dirn,
        "category": cat,
        "description": (description or "").strip()[:200],
        "date": record_date,
        "tags": tags_list[:10],
        "created_at": now,
    }
    _save_record(record)

    return json.dumps({
        "ok": True,
        "record_id": rid,
        "amount": amt,
        "direction": dirn,
        "category": cat,
        "date": record_date,
    }, ensure_ascii=False)


def tool_expense_summary(
    period: str = "month",
    year: int = 0,
    month: int = 0,
    **_: Any,
) -> str:
    if not _expense_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_EXPENSE_ENABLED=0"})

    now_cn = datetime.now(_CN_TZ)
    y = int(year) if year else now_cn.year
    m = int(month) if month else now_cn.month

    all_records = _load_all()

    if period == "year":
        start = f"{y:04d}-01-01"
        end = f"{y + 1:04d}-01-01"
        label = f"{y}年"
    elif period == "week":
        today = now_cn.date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=7)
        start = week_start.isoformat()
        end = week_end.isoformat()
        label = f"本周 ({start} ~ {(week_end - timedelta(days=1)).isoformat()})"
    else:
        start, end = _month_range(y, m)
        label = f"{y}年{m}月"

    filtered = _filter_by_period(all_records, start, end)

    total_income = 0.0
    total_expense = 0.0
    cat_totals: dict[str, float] = {}

    for r in filtered:
        amt = r.get("amount", 0)
        dirn = r.get("direction", "expense")
        cat = r.get("category", "other")
        if dirn == "income":
            total_income += amt
        else:
            total_expense += amt
            cat_totals[cat] = cat_totals.get(cat, 0) + amt

    cat_breakdown = sorted(cat_totals.items(), key=lambda x: -x[1])

    return json.dumps({
        "ok": True,
        "period": label,
        "record_count": len(filtered),
        "total_income": round(total_income, 2),
        "total_expense": round(total_expense, 2),
        "net": round(total_income - total_expense, 2),
        "category_breakdown": [
            {"category": c, "label": _CATEGORY_LABELS.get(c, c), "amount": round(a, 2)}
            for c, a in cat_breakdown
        ],
    }, ensure_ascii=False)


def tool_expense_list(
    limit: int = 20,
    category: str = "",
    direction: str = "",
    **_: Any,
) -> str:
    if not _expense_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_EXPENSE_ENABLED=0"})

    all_records = _load_all()
    filtered = list(all_records)

    if category:
        cat = _normalize_category(category)
        filtered = [r for r in filtered if r.get("category") == cat]
    if direction:
        dirn = _normalize_direction(direction)
        filtered = [r for r in filtered if r.get("direction") == dirn]

    filtered.sort(key=lambda r: r.get("date", ""), reverse=True)
    limit = max(1, min(int(limit or 20), 50))

    return json.dumps({
        "ok": True,
        "total": len(all_records),
        "count": len(filtered),
        "records": filtered[:limit],
    }, ensure_ascii=False)


def tool_expense_delete(record_id: str, **_: Any) -> str:
    if not _expense_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_EXPENSE_ENABLED=0"})

    rid = (record_id or "").strip()
    if not rid:
        return json.dumps({"ok": False, "error": "record_id is required"})

    if _delete_record(rid):
        return json.dumps({"ok": True, "deleted": rid})

    for r in _load_all():
        if r.get("id", "").startswith(rid):
            if _delete_record(r["id"]):
                return json.dumps({"ok": True, "deleted": r["id"]})

    return json.dumps({"ok": False, "error": f"Record '{rid}' not found"})


# ── WeChat Display ─────────────────────────────────────────────


def format_expense_for_wechat(arg: str = "", *, limit: int = 15) -> str:
    if not _expense_enabled():
        return "记账功能未启用 (BUTLER_EXPENSE_ENABLED=0)"

    arg = (arg or "").strip()

    if arg.startswith("本周") or arg == "week":
        return _format_summary("week")
    if arg.startswith("本月") or arg == "month" or not arg:
        return _format_summary("month")
    if arg.startswith("本年") or arg.startswith("年度") or arg == "year":
        return _format_summary("year")

    if arg.startswith("记 ") or arg.startswith("add "):
        return _handle_quick_add(arg)

    if arg.startswith("明细") or arg.startswith("list"):
        return _format_recent(limit=limit)

    return _format_summary("month")


def _handle_quick_add(arg: str) -> str:
    """Parse quick-add: /记账 记 午饭 35 or /记账 记 35 午饭"""
    parts = arg.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        return "用法: /记账 记 <描述> <金额>\n示例: /记账 记 午饭 35"

    rest = parts[1].strip()
    tokens = rest.split()
    amount = None
    desc_parts = []

    for t in tokens:
        try:
            amount = float(t.replace("元", "").replace("块", ""))
        except ValueError:
            desc_parts.append(t)

    if amount is None:
        return "❌ 请包含金额，示例: /记账 记 午饭 35"

    desc = " ".join(desc_parts) or "日常支出"
    raw = tool_expense_add(amount=amount, description=desc)
    data = json.loads(raw)
    if data.get("ok"):
        return f"✅ 已记录: {desc} ¥{data['amount']:.2f} ({data['date']})"
    return f"❌ {data.get('error', '记录失败')}"


def _format_summary(period: str) -> str:
    raw = tool_expense_summary(period=period)
    data = json.loads(raw)

    if data.get("record_count", 0) == 0:
        if period == "month":
            return "💰 本月暂无记录\n\n记一笔: /记账 记 <描述> <金额>\n或对话中说「午饭花了35元」"
        return f"💰 {data.get('period', '')} 暂无记录"

    lines = [f"💰 {data['period']} 收支汇总\n"]

    if data.get("total_income", 0) > 0:
        lines.append(f"📈 收入: ¥{data['total_income']:,.2f}")
    lines.append(f"📉 支出: ¥{data['total_expense']:,.2f}")

    net = data.get("net", 0)
    if data.get("total_income", 0) > 0:
        icon = "✅" if net >= 0 else "⚠️"
        lines.append(f"{icon} 结余: ¥{net:,.2f}")

    lines.append(f"📊 共 {data['record_count']} 笔\n")

    breakdown = data.get("category_breakdown", [])
    if breakdown:
        lines.append("分类明细:")
        for item in breakdown[:8]:
            bar_len = min(int(item["amount"] / max(breakdown[0]["amount"], 1) * 10), 10)
            bar = "█" * bar_len
            lines.append(f"  {item['label']}: ¥{item['amount']:,.2f}  {bar}")

    lines.append("\n/记账 明细  查看最近记录")
    return "\n".join(lines)


def _format_recent(*, limit: int = 15) -> str:
    raw = tool_expense_list(limit=limit)
    data = json.loads(raw)
    records = data.get("records", [])

    if not records:
        return "💰 暂无记录"

    lines = [f"💰 最近 {len(records)} 笔记录\n"]
    for r in records:
        dirn_icon = "📈" if r.get("direction") == "income" else "📉"
        cat = _CATEGORY_LABELS.get(r.get("category", "other"), "其他")
        desc = r.get("description", "")[:30]
        lines.append(
            f"{dirn_icon} {r.get('date', '')} ¥{r.get('amount', 0):.2f} "
            f"[{cat}] {desc}"
        )

    lines.append(f"\n共 {data['total']} 条  |  /记账 本月  查看汇总")
    return "\n".join(lines)


# ── Registration ───────────────────────────────────────────────


def register_expense_tools(register: Callable[..., None]) -> None:
    if not _expense_enabled():
        return

    register(
        name="expense_add",
        description=(
            "记一笔收支。支出说「午饭花了35」，收入用 direction='income'。"
            "日期默认今天，可指定 date='2026-05-20'。"
        ),
        schema={
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "金额（正数）"},
                "description": {"type": "string", "description": "描述"},
                "category": {
                    "type": "string",
                    "enum": list(_VALID_CATEGORIES),
                    "description": "分类: food/transport/housing/medical/entertainment/shopping/education/social/salary/investment/other",
                },
                "direction": {
                    "type": "string",
                    "enum": ["income", "expense"],
                    "description": "收支方向: income(收入) / expense(支出，默认)",
                },
                "date": {
                    "type": "string",
                    "description": "日期 YYYY-MM-DD（默认今天）",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选标签",
                },
            },
            "required": ["amount"],
        },
        handler=tool_expense_add,
        toolset="expense",
    )

    register(
        name="expense_summary",
        description=(
            "查看收支汇总统计。可按月/周/年查看，含分类明细。"
            "「这个月花了多少」「本周支出」「交通费花了多少」。"
        ),
        schema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["month", "week", "year"],
                    "description": "统计周期: month(默认)/week/year",
                },
                "year": {"type": "integer", "description": "年份（默认今年）"},
                "month": {"type": "integer", "description": "月份（默认当月）"},
            },
        },
        handler=tool_expense_summary,
        toolset="expense",
    )

    register(
        name="expense_list",
        description="列出最近的收支明细记录。",
        schema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "最多返回条数"},
                "category": {
                    "type": "string",
                    "enum": list(_VALID_CATEGORIES),
                    "description": "按分类筛选",
                },
                "direction": {
                    "type": "string",
                    "enum": ["income", "expense"],
                    "description": "按收支方向筛选",
                },
            },
        },
        handler=tool_expense_list,
        toolset="expense",
    )

    register(
        name="expense_delete",
        description="删除一条收支记录。",
        schema={
            "type": "object",
            "properties": {
                "record_id": {"type": "string", "description": "记录 ID（支持前缀匹配）"},
            },
            "required": ["record_id"],
        },
        handler=tool_expense_delete,
        toolset="expense",
    )
