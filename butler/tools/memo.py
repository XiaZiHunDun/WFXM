"""Personal memo system — cross-project structured notes for daily life.

Memos are owner-level (tenant-scoped), not project-scoped. They persist
under ``~/.butler/tenants/<tenant>/memos/`` as one JSON file per entry.

Unlike ``butler_remember`` (cognitive memory the butler learns), memos are
explicit items the owner asks the butler to track — appointments, shopping
lists, health notes, etc.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from butler.tools.pim_schema import (
    MAX_ACTIVE_MEMOS as _MAX_ACTIVE,
    MAX_MEMO_CONTENT_LEN as _MAX_CONTENT_LEN,
    MAX_MEMO_TAGS as _MAX_TAGS,
    MAX_TAG_LEN as _MAX_TAG_LEN,
    MEMO_CATEGORIES as _VALID_CATEGORIES,
    MEMO_CATEGORY_LABELS as _CATEGORY_LABELS,
    MEMO_PRIORITIES as _VALID_PRIORITIES,
    MEMO_PRIORITY_RANK as _PRIORITY_RANK,
    MEMO_STATUSES as _VALID_STATUSES,
)
from butler.tools.tenant_store import TenantStore

logger = logging.getLogger(__name__)

_STATUS_LABELS = {"active": "活跃", "done": "已完成", "archived": "已归档"}

_base_store = TenantStore(
    "memos", env_toggle="BUTLER_MEMO_ENABLED", skip_files=frozenset({"index.json"}),
)


class _MemosStore(TenantStore):
    def storage_dir(self) -> Path:
        return _memos_dir()


_store = _MemosStore(
    "memos", env_toggle="BUTLER_MEMO_ENABLED", skip_files=frozenset({"index.json"}),
)


def _memo_enabled() -> bool:
    return _store.enabled()


def _memos_dir() -> Path:
    return _base_store.storage_dir()


def _normalize_tags(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        raw = [t.strip() for t in raw.replace("，", ",").split(",")]
    if not isinstance(raw, list):
        return []
    tags: list[str] = []
    for t in raw:
        s = str(t).strip()[:_MAX_TAG_LEN]
        if s and s not in tags:
            tags.append(s)
        if len(tags) >= _MAX_TAGS:
            break
    return tags


def _normalize_category(raw: Any) -> str:
    val = str(raw or "").strip().lower()
    return val if val in _VALID_CATEGORIES else "general"


def _normalize_status(raw: Any) -> str:
    val = str(raw or "").strip().lower()
    return val if val in _VALID_STATUSES else "active"


def _normalize_priority(raw: Any) -> str:
    val = str(raw or "").strip().lower()
    return val if val in _VALID_PRIORITIES else "normal"


def _sort_memos(memos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(memos, key=lambda m: (
        _PRIORITY_RANK.get(m.get("priority", "normal"), 2),
        -m.get("created_at", 0),
    ))


# ── Tool Handlers ──────────────────────────────────────────────


def tool_memo_add(
    content: str,
    category: str = "",
    tags: Any = None,
    priority: str = "",
    due_date: str = "",
    **_: Any,
) -> str:
    if not _memo_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_MEMO_ENABLED=0"})

    content = (content or "").strip()
    if not content:
        return json.dumps({"ok": False, "error": "content is required"})
    content = content[:_MAX_CONTENT_LEN]

    active_count = sum(1 for m in _store.load_all() if m.get("status") == "active")
    if active_count >= _MAX_ACTIVE:
        return json.dumps({
            "ok": False,
            "error": f"Active memo limit reached ({_MAX_ACTIVE}). Complete or archive some first.",
        })

    now = time.time()
    mid = uuid.uuid4().hex[:10]
    memo: dict[str, Any] = {
        "id": mid,
        "content": content,
        "category": _normalize_category(category),
        "tags": _normalize_tags(tags),
        "status": "active",
        "priority": _normalize_priority(priority),
        "due_date": (due_date or "").strip(),
        "created_at": now,
        "updated_at": now,
        "source": "tool",
    }
    _store.save(memo)

    result: dict[str, Any] = {
        "ok": True,
        "memo_id": mid,
        "content": content,
        "category": memo["category"],
    }
    if memo["due_date"]:
        result["due_date"] = memo["due_date"]
        result["suggestion"] = (
            f"备忘已创建。建议设置提醒: "
            f"set_reminder(message='{content[:50]}', when='{memo['due_date']}')"
        )
    return json.dumps(result, ensure_ascii=False)


def tool_memo_list(
    status: str = "active",
    category: str = "",
    limit: int = 20,
    **_: Any,
) -> str:
    if not _memo_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_MEMO_ENABLED=0"})

    all_memos = _store.load_all()
    target_status = _normalize_status(status) if status else "active"

    filtered = [m for m in all_memos if m.get("status") == target_status]
    if category:
        cat = _normalize_category(category)
        if cat != "general" or category.strip().lower() == "general":
            filtered = [m for m in filtered if m.get("category") == cat]

    filtered = _sort_memos(filtered)
    limit = max(1, min(int(limit or 20), 50))
    active_total = sum(1 for m in all_memos if m.get("status") == "active")
    done_total = sum(1 for m in all_memos if m.get("status") == "done")

    return json.dumps({
        "ok": True,
        "count": len(filtered),
        "active_total": active_total,
        "done_total": done_total,
        "memos": filtered[:limit],
    }, ensure_ascii=False)


def tool_memo_search(
    query: str = "",
    limit: int = 20,
    **_: Any,
) -> str:
    if not _memo_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_MEMO_ENABLED=0"})

    q = (query or "").strip().lower()
    if not q:
        return tool_memo_list()

    all_memos = _store.load_all()
    matched: list[dict[str, Any]] = []
    for m in all_memos:
        text = (m.get("content", "") + " " + " ".join(m.get("tags", []))).lower()
        if q in text:
            matched.append(m)

    matched = _sort_memos(matched)
    limit = max(1, min(int(limit or 20), 50))

    return json.dumps({
        "ok": True,
        "query": query,
        "count": len(matched),
        "memos": matched[:limit],
    }, ensure_ascii=False)


def tool_memo_update(
    memo_id: str,
    content: str = "",
    status: str = "",
    priority: str = "",
    tags: Any = None,
    due_date: str = "",
    **_: Any,
) -> str:
    if not _memo_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_MEMO_ENABLED=0"})

    mid = (memo_id or "").strip()
    if not mid:
        return json.dumps({"ok": False, "error": "memo_id is required"})

    memo = _store.find_by_prefix(mid)
    if memo is None:
        return json.dumps({"ok": False, "error": f"Memo '{mid}' not found"})
    mid = memo["id"]

    changed = False
    if content and content.strip():
        memo["content"] = content.strip()[:_MAX_CONTENT_LEN]
        changed = True
    if status and status.strip():
        new_status = _normalize_status(status)
        if new_status != memo.get("status"):
            memo["status"] = new_status
            changed = True
    if priority and priority.strip():
        new_pri = _normalize_priority(priority)
        if new_pri != memo.get("priority"):
            memo["priority"] = new_pri
            changed = True
    if tags is not None:
        memo["tags"] = _normalize_tags(tags)
        changed = True
    if due_date is not None and due_date != "":
        memo["due_date"] = due_date.strip()
        changed = True

    if changed:
        memo["updated_at"] = time.time()
        _store.save(memo)

    return json.dumps({
        "ok": True,
        "memo_id": mid,
        "updated": changed,
        "status": memo.get("status"),
    }, ensure_ascii=False)


def tool_memo_delete(memo_id: str, **_: Any) -> str:
    if not _memo_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_MEMO_ENABLED=0"})

    mid = (memo_id or "").strip()
    if not mid:
        return json.dumps({"ok": False, "error": "memo_id is required"})

    memo = _store.find_by_prefix(mid)
    if memo is not None and _store.delete(memo["id"]):
        return json.dumps({"ok": True, "deleted": memo["id"]})

    return json.dumps({"ok": False, "error": f"Memo '{mid}' not found"})


# ── WeChat Display ─────────────────────────────────────────────


def format_memos_for_wechat(arg: str = "", *, limit: int = 15) -> str:
    if not _memo_enabled():
        return "备忘录功能未启用 (BUTLER_MEMO_ENABLED=0)"

    arg = (arg or "").strip()

    if arg.startswith("搜索 ") or arg.startswith("search "):
        query = arg.split(maxsplit=1)[1] if " " in arg else ""
        return _format_search_result(query, limit=limit)

    if arg.startswith("添加 ") or arg.startswith("add "):
        content = arg.split(maxsplit=1)[1] if " " in arg else ""
        if content:
            raw = tool_memo_add(content=content, source="slash")
            data = json.loads(raw)
            if data.get("ok"):
                return f"✅ 备忘已添加 [{data['memo_id']}]\n{content}"
            return f"❌ {data.get('error', '添加失败')}"
        return "用法: /备忘 添加 <内容>"

    if arg.startswith("完成 ") or arg.startswith("done "):
        mid = arg.split(maxsplit=1)[1].strip() if " " in arg else ""
        if mid:
            raw = tool_memo_update(memo_id=mid, status="done")
            data = json.loads(raw)
            if data.get("ok"):
                return f"✅ 备忘 [{data['memo_id']}] 已标记完成"
            return f"❌ {data.get('error', '操作失败')}"
        return "用法: /备忘 完成 <id>"

    return _format_memo_list(limit=limit)


def _format_memo_list(*, limit: int = 15) -> str:
    all_memos = _store.load_all()
    active = _sort_memos([m for m in all_memos if m.get("status") == "active"])
    done_count = sum(1 for m in all_memos if m.get("status") == "done")

    if not active:
        return "📋 备忘录为空\n\n添加: /备忘 添加 <内容>\n或对话中说「帮我记一下…」"

    lines = [f"📋 备忘录 ({len(active)}条活跃)\n"]
    pri_icons = {"urgent": "🔴", "high": "🟠", "normal": "⚪", "low": "🔵"}

    for m in active[:limit]:
        icon = pri_icons.get(m.get("priority", "normal"), "⚪")
        mid = m["id"][:4]
        content = m.get("content", "")[:60]
        line = f"{icon} [{mid}] {content}"

        meta = []
        cat = m.get("category", "general")
        if cat != "general":
            meta.append(_CATEGORY_LABELS.get(cat, cat))
        if m.get("due_date"):
            meta.append(f"截止: {m['due_date'][:10]}")
        tags = m.get("tags", [])
        if tags:
            meta.append(", ".join(tags[:3]))
        if meta:
            line += f"\n   {' | '.join(meta)}"
        lines.append(line)

    if len(active) > limit:
        lines.append(f"\n... 还有 {len(active) - limit} 条")
    footer_parts = []
    if done_count:
        footer_parts.append(f"✅ 已完成: {done_count}条")
    footer_parts.append("/备忘 搜索 <关键词>")
    lines.append(f"\n{'  |  '.join(footer_parts)}")
    return "\n".join(lines)


def _format_search_result(query: str, *, limit: int = 15) -> str:
    if not query:
        return "用法: /备忘 搜索 <关键词>"
    raw = tool_memo_search(query=query, limit=limit)
    data = json.loads(raw)
    memos = data.get("memos", [])
    if not memos:
        return f"🔍 未找到「{query}」相关备忘"

    lines = [f"🔍 搜索「{query}」找到 {len(memos)} 条\n"]
    for m in memos:
        status_icon = "✅" if m.get("status") == "done" else "⚪"
        mid = m["id"][:4]
        content = m.get("content", "")[:60]
        lines.append(f"{status_icon} [{mid}] {content}")
    return "\n".join(lines)


# ── Registration ───────────────────────────────────────────────


def register_memo_tools(register: Callable[..., None]) -> None:
    if not _memo_enabled():
        return

    register(
        name="memo_add",
        description=(
            "为主人创建备忘录条目。用于记录日常事务、约会、购物清单、健康信息等。"
            "用户说「帮我记一下…」「别忘了…」时应使用此工具。"
            "如果有明确时间点且需要推送提醒，应配合 set_reminder 使用。"
            "注意：定时推送提醒请用 set_reminder，个人偏好请用 butler_remember。"
        ),
        schema={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "备忘内容"},
                "category": {
                    "type": "string",
                    "enum": list(_VALID_CATEGORIES),
                    "description": "分类: general/health/finance/travel/shopping/social/work",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选标签列表",
                },
                "priority": {
                    "type": "string",
                    "enum": list(_VALID_PRIORITIES),
                    "description": "优先级: low/normal/high/urgent",
                },
                "due_date": {
                    "type": "string",
                    "description": "可选截止日期 (ISO8601 或自然语言如 '周六 14:00')",
                },
            },
            "required": ["content"],
        },
        handler=tool_memo_add,
        toolset="memo",
    )

    register(
        name="memo_list",
        description="列出主人的备忘录。可按状态和分类筛选。",
        schema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": list(_VALID_STATUSES),
                    "description": "筛选状态: active(默认)/done/archived",
                },
                "category": {
                    "type": "string",
                    "enum": list(_VALID_CATEGORIES),
                    "description": "筛选分类",
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回条数 (默认 20, 上限 50)",
                },
            },
        },
        handler=tool_memo_list,
        toolset="memo",
    )

    register(
        name="memo_search",
        description="按关键词搜索备忘录内容和标签。用户说「查看/搜索XX备忘」时使用。注意：修改备忘请用 memo_update（需要 memo_id）。",
        schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "limit": {"type": "integer", "description": "最多返回条数"},
            },
            "required": ["query"],
        },
        handler=tool_memo_search,
        toolset="memo",
    )

    register(
        name="memo_update",
        description="更新备忘录的状态、内容或优先级。标记完成用 status='done'。需要 memo_id 参数；若不知 memo_id，先用 memo_search 查找。",
        schema={
            "type": "object",
            "properties": {
                "memo_id": {"type": "string", "description": "备忘 ID（支持前缀匹配）"},
                "content": {"type": "string", "description": "新内容"},
                "status": {
                    "type": "string",
                    "enum": list(_VALID_STATUSES),
                    "description": "新状态",
                },
                "priority": {
                    "type": "string",
                    "enum": list(_VALID_PRIORITIES),
                    "description": "新优先级",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "替换标签列表",
                },
                "due_date": {"type": "string", "description": "新截止日期"},
            },
            "required": ["memo_id"],
        },
        handler=tool_memo_update,
        toolset="memo",
    )

    register(
        name="memo_delete",
        description="永久删除一条备忘录。",
        schema={
            "type": "object",
            "properties": {
                "memo_id": {"type": "string", "description": "备忘 ID（支持前缀匹配）"},
            },
            "required": ["memo_id"],
        },
        handler=tool_memo_delete,
        toolset="memo",
    )
