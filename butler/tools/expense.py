"""Personal expense tracker — cross-project income/expense logging.

Records are tenant-scoped, stored under
``~/.butler/tenants/<tenant>/expenses/`` as one JSON file per entry.

Core value is numeric aggregation: monthly totals, category breakdowns,
and period comparisons — not individual record browsing.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from butler.tools.pim_schema import (
    EXPENSE_CATEGORIES as _VALID_CATEGORIES,
    EXPENSE_CATEGORY_LABELS as _CATEGORY_LABELS,
    EXPENSE_DIRECTIONS as _VALID_DIRECTIONS,
    MAX_EXPENSE_DESC_LEN as _MAX_DESC_LEN,
    MAX_EXPENSE_RECORDS as _MAX_RECORDS,
)
from butler.tools.tenant_store import TenantStore

logger = logging.getLogger(__name__)

_CN_TZ = timezone(timedelta(hours=8))

_store = TenantStore("expenses", env_toggle="BUTLER_EXPENSE_ENABLED")


def _expense_enabled() -> bool:
    return _store.enabled()


def _expenses_dir() -> Path:
    return _store.storage_dir()


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

    total = len(_store.load_all())
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
        "description": (description or "").strip()[:_MAX_DESC_LEN],
        "date": record_date,
        "tags": tags_list[:10],
        "created_at": now,
    }
    _store.save(record)

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

    all_records = _store.load_all()

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

    all_records = _store.load_all()
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


def tool_expense_update(
    expense_id: str,
    amount: Any = None,
    description: str = "",
    category: str = "",
    direction: str = "",
    date: str = "",
    tags: Any = None,
    **_: Any,
) -> str:
    if not _expense_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_EXPENSE_ENABLED=0"})

    eid = (expense_id or "").strip()
    if not eid:
        return json.dumps({"ok": False, "error": "expense_id is required"})

    record = _store.find_by_prefix(eid)
    if record is None:
        return json.dumps({"ok": False, "error": f"Record '{eid}' not found"})

    updated_fields: list[str] = []

    if amount is not None:
        try:
            amt = round(float(amount), 2)
        except (TypeError, ValueError):
            return json.dumps({"ok": False, "error": "amount must be a number"})
        if amt <= 0:
            return json.dumps({"ok": False, "error": "amount must be positive"})
        record["amount"] = amt
        updated_fields.append("amount")

    if description and description.strip():
        record["description"] = description.strip()[:_MAX_DESC_LEN]
        updated_fields.append("description")

    if category and category.strip():
        cat = category.strip().lower()
        if cat not in _VALID_CATEGORIES:
            return json.dumps({
                "ok": False,
                "error": f"Invalid category '{category}'. Use: {', '.join(sorted(_VALID_CATEGORIES))}",
            })
        record["category"] = cat
        updated_fields.append("category")

    if direction and direction.strip():
        dirn = direction.strip().lower()
        if dirn not in _VALID_DIRECTIONS:
            return json.dumps({
                "ok": False,
                "error": f"Invalid direction '{direction}'. Use: {', '.join(sorted(_VALID_DIRECTIONS))}",
            })
        record["direction"] = dirn
        updated_fields.append("direction")

    if date and date.strip():
        record["date"] = _parse_date(date)
        updated_fields.append("date")

    if tags is not None:
        tags_list: list[str] = []
        if isinstance(tags, str):
            tags_list = [t.strip() for t in tags.replace("，", ",").split(",") if t.strip()]
        elif isinstance(tags, list):
            tags_list = [str(t).strip() for t in tags if str(t).strip()]
        record["tags"] = tags_list[:10]
        updated_fields.append("tags")

    if updated_fields:
        _store.save(record)

    return json.dumps({
        "ok": True,
        "expense_id": record["id"],
        "updated_fields": updated_fields,
    }, ensure_ascii=False)


def tool_expense_search(
    query: str,
    limit: int = 20,
    **_: Any,
) -> str:
    if not _expense_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_EXPENSE_ENABLED=0"})

    q = (query or "").strip()
    if not q:
        return json.dumps({"ok": False, "error": "query is required"})

    matched = _store.search(q, fields=["description", "tags"])
    matched.sort(key=lambda r: r.get("date", ""), reverse=True)
    limit = max(1, min(int(limit or 20), 50))

    return json.dumps({
        "ok": True,
        "query": q,
        "count": len(matched),
        "records": matched[:limit],
    }, ensure_ascii=False)


def tool_expense_delete(record_id: str, **_: Any) -> str:
    if not _expense_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_EXPENSE_ENABLED=0"})

    rid = (record_id or "").strip()
    if not rid:
        return json.dumps({"ok": False, "error": "record_id is required"})

    if _store.delete(rid):
        return json.dumps({"ok": True, "deleted": rid})

    record = _store.find_by_prefix(rid)
    if record is not None and _store.delete(record["id"]):
        return json.dumps({"ok": True, "deleted": record["id"]})

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
                    "description": (
                        "分类: food/transport/housing/medical/entertainment/"
                        "shopping/education/social/salary/investment/other"
                    ),
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
            "【rollup-only】按 month/week/year 输出 expense_totals 与各 category_breakdown。"
            "场景：问周期总额、分类占比。"
            "禁止返回单笔 transaction 行。"
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
        description=(
            "【transaction-only】按时间倒序输出 ledger rows（amount、category、date）。"
            "场景：问「买了什么」「列流水」。"
            "禁止 period_total 或 category_breakdown。"
        ),
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
        name="expense_update",
        description="修改一条收支记录的金额、描述、分类、方向、日期或标签。",
        schema={
            "type": "object",
            "properties": {
                "expense_id": {"type": "string", "description": "记录 ID（支持前缀匹配）"},
                "amount": {"type": "number", "description": "新金额（正数）"},
                "description": {"type": "string", "description": "新描述"},
                "category": {
                    "type": "string",
                    "enum": list(_VALID_CATEGORIES),
                    "description": "新分类",
                },
                "direction": {
                    "type": "string",
                    "enum": list(_VALID_DIRECTIONS),
                    "description": "新收支方向",
                },
                "date": {"type": "string", "description": "新日期 YYYY-MM-DD"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "替换标签列表",
                },
            },
            "required": ["expense_id"],
        },
        handler=tool_expense_update,
        toolset="expense",
    )

    register(
        name="expense_search",
        description=(
            "【read-only·keyword】按描述关键词检索收支行，返回 record_id 与摘要。"
            "场景：找某笔消费。不删除、不修改。"
        ),
        schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "limit": {"type": "integer", "description": "最多返回条数（默认 20）"},
            },
            "required": ["query"],
        },
        handler=tool_expense_search,
        toolset="expense",
    )

    register(
        name="expense_delete",
        description=(
            "【mutation·purge】按 record_id 永久删除一条收支。"
            "场景：记错账需移除。不执行关键词搜索。"
        ),
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
