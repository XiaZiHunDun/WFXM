"""Personal contacts manager — cross-project address book.

Contacts are tenant-scoped, stored under
``~/.butler/tenants/<tenant>/contacts/`` as one JSON file per entry.

Unlike cognitive memory (butler_remember), contacts are structured records
with phone/email/address fields, optimized for name-based lookup.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from butler.tools.tenant_store import TenantStore

logger = logging.getLogger(__name__)

_MAX_CONTACTS = 500
_MAX_PHONES = 5
_MAX_EMAILS = 5
_MAX_TAGS = 10
_MAX_TAG_LEN = 30

_VALID_CATEGORIES = frozenset({
    "personal", "work", "service", "medical", "other",
})
_CATEGORY_LABELS = {
    "personal": "个人", "work": "工作", "service": "服务",
    "medical": "医疗", "other": "其他",
}

_store = TenantStore("contacts", env_toggle="BUTLER_CONTACTS_ENABLED")


def _contacts_enabled() -> bool:
    return _store.enabled()


def _contacts_dir() -> Path:
    return _store.storage_dir()


def _save_contact(contact: dict[str, Any]) -> Path:
    d = _contacts_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{contact['id']}.json"
    path.write_text(json.dumps(contact, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _load_all() -> list[dict[str, Any]]:
    d = _contacts_dir()
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


def _load_contact(cid: str) -> dict[str, Any] | None:
    path = _contacts_dir() / f"{cid}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and data.get("id") == cid else None
    except (json.JSONDecodeError, OSError):
        return None


def _delete_contact(cid: str) -> bool:
    path = _contacts_dir() / f"{cid}.json"
    if path.is_file():
        path.unlink()
        return True
    return False


def _normalize_phones(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        raw = [p.strip() for p in raw.replace("，", ",").replace(";", ",").split(",")]
    if not isinstance(raw, list):
        return []
    phones: list[str] = []
    for p in raw:
        s = str(p).strip()
        if s and s not in phones:
            phones.append(s)
        if len(phones) >= _MAX_PHONES:
            break
    return phones


def _normalize_emails(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        raw = [e.strip() for e in raw.replace("，", ",").replace(";", ",").split(",")]
    if not isinstance(raw, list):
        return []
    emails: list[str] = []
    for e in raw:
        s = str(e).strip()
        if s and s not in emails:
            emails.append(s)
        if len(emails) >= _MAX_EMAILS:
            break
    return emails


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
    return val if val in _VALID_CATEGORIES else "personal"


def _find_by_name(name: str) -> list[dict[str, Any]]:
    """Find contacts by exact or partial name match."""
    q = name.strip().lower()
    if not q:
        return []
    all_contacts = _load_all()
    exact = [c for c in all_contacts if c.get("name", "").lower() == q]
    if exact:
        return exact
    return [c for c in all_contacts if q in c.get("name", "").lower()]


def _check_duplicate(name: str, exclude_id: str = "") -> dict[str, Any] | None:
    """Check if a contact with the same name already exists."""
    q = name.strip().lower()
    for c in _load_all():
        if c.get("name", "").lower() == q and c.get("id") != exclude_id:
            return c
    return None


# ── Tool Handlers ──────────────────────────────────────────────


def tool_contact_add(
    name: str,
    phone: Any = None,
    email: Any = None,
    address: str = "",
    category: str = "",
    tags: Any = None,
    notes: str = "",
    **_: Any,
) -> str:
    if not _contacts_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_CONTACTS_ENABLED=0"})

    name = (name or "").strip()
    if not name:
        return json.dumps({"ok": False, "error": "name is required"})

    total = len(_load_all())
    if total >= _MAX_CONTACTS:
        return json.dumps({
            "ok": False,
            "error": f"Contact limit reached ({_MAX_CONTACTS}). Delete some first.",
        })

    dup = _check_duplicate(name)
    now = time.time()
    cid = uuid.uuid4().hex[:10]

    contact: dict[str, Any] = {
        "id": cid,
        "name": name,
        "phone": _normalize_phones(phone),
        "email": _normalize_emails(email),
        "address": (address or "").strip(),
        "category": _normalize_category(category),
        "tags": _normalize_tags(tags),
        "notes": (notes or "").strip()[:500],
        "created_at": now,
        "updated_at": now,
    }
    _save_contact(contact)

    result: dict[str, Any] = {
        "ok": True,
        "contact_id": cid,
        "name": name,
    }
    if dup:
        result["warning"] = f"已存在同名联系人 [{dup['id'][:4]}] {dup['name']}，如需合并请更新该条目"
    return json.dumps(result, ensure_ascii=False)


def tool_contact_find(
    query: str = "",
    category: str = "",
    limit: int = 20,
    **_: Any,
) -> str:
    if not _contacts_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_CONTACTS_ENABLED=0"})

    q = (query or "").strip().lower()
    all_contacts = _load_all()

    if q:
        matched: list[dict[str, Any]] = []
        for c in all_contacts:
            searchable = " ".join([
                c.get("name", ""),
                " ".join(c.get("phone", [])),
                " ".join(c.get("email", [])),
                c.get("address", ""),
                " ".join(c.get("tags", [])),
                c.get("notes", ""),
            ]).lower()
            if q in searchable:
                matched.append(c)
    else:
        matched = list(all_contacts)

    if category:
        cat = _normalize_category(category)
        matched = [c for c in matched if c.get("category") == cat]

    matched.sort(key=lambda c: c.get("name", "").lower())
    limit = max(1, min(int(limit or 20), 50))

    return json.dumps({
        "ok": True,
        "query": query or "",
        "count": len(matched),
        "contacts": matched[:limit],
    }, ensure_ascii=False)


def tool_contact_update(
    contact_id: str,
    name: str = "",
    phone: Any = None,
    email: Any = None,
    address: str = "",
    category: str = "",
    tags: Any = None,
    notes: str = "",
    **_: Any,
) -> str:
    if not _contacts_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_CONTACTS_ENABLED=0"})

    cid = (contact_id or "").strip()
    if not cid:
        return json.dumps({"ok": False, "error": "contact_id is required"})

    contact = _load_contact(cid)
    if contact is None:
        for c in _load_all():
            if c.get("id", "").startswith(cid):
                contact = c
                cid = c["id"]
                break
    if contact is None:
        return json.dumps({"ok": False, "error": f"Contact '{cid}' not found"})

    changed = False
    if name and name.strip():
        contact["name"] = name.strip()
        changed = True
    if phone is not None:
        contact["phone"] = _normalize_phones(phone)
        changed = True
    if email is not None:
        contact["email"] = _normalize_emails(email)
        changed = True
    if address is not None and address != "":
        contact["address"] = address.strip()
        changed = True
    if category and category.strip():
        new_cat = _normalize_category(category)
        if new_cat != contact.get("category"):
            contact["category"] = new_cat
            changed = True
    if tags is not None:
        contact["tags"] = _normalize_tags(tags)
        changed = True
    if notes is not None and notes != "":
        contact["notes"] = notes.strip()[:500]
        changed = True

    if changed:
        contact["updated_at"] = time.time()
        _save_contact(contact)

    return json.dumps({
        "ok": True,
        "contact_id": cid,
        "updated": changed,
        "name": contact.get("name"),
    }, ensure_ascii=False)


def tool_contact_delete(contact_id: str, **_: Any) -> str:
    if not _contacts_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_CONTACTS_ENABLED=0"})

    cid = (contact_id or "").strip()
    if not cid:
        return json.dumps({"ok": False, "error": "contact_id is required"})

    if _delete_contact(cid):
        return json.dumps({"ok": True, "deleted": cid})

    for c in _load_all():
        if c.get("id", "").startswith(cid):
            if _delete_contact(c["id"]):
                return json.dumps({"ok": True, "deleted": c["id"]})

    return json.dumps({"ok": False, "error": f"Contact '{cid}' not found"})


def tool_contact_list(
    category: str = "",
    limit: int = 30,
    **_: Any,
) -> str:
    if not _contacts_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_CONTACTS_ENABLED=0"})

    all_contacts = _load_all()
    filtered = list(all_contacts)

    if category:
        cat = _normalize_category(category)
        filtered = [c for c in filtered if c.get("category") == cat]

    filtered.sort(key=lambda c: c.get("name", "").lower())
    limit = max(1, min(int(limit or 30), 50))

    cat_counts: dict[str, int] = {}
    for c in all_contacts:
        k = c.get("category", "personal")
        cat_counts[k] = cat_counts.get(k, 0) + 1

    return json.dumps({
        "ok": True,
        "total": len(all_contacts),
        "count": len(filtered),
        "categories": cat_counts,
        "contacts": filtered[:limit],
    }, ensure_ascii=False)


# ── WeChat Display ─────────────────────────────────────────────


def format_contacts_for_wechat(arg: str = "", *, limit: int = 20) -> str:
    if not _contacts_enabled():
        return "通讯录功能未启用 (BUTLER_CONTACTS_ENABLED=0)"

    arg = (arg or "").strip()

    if arg.startswith("添加 ") or arg.startswith("add "):
        rest = arg.split(maxsplit=1)[1] if " " in arg else ""
        if rest:
            raw = tool_contact_add(name=rest)
            data = json.loads(raw)
            if data.get("ok"):
                msg = f"✅ 联系人已添加: {rest} [{data['contact_id'][:4]}]"
                if data.get("warning"):
                    msg += f"\n⚠️ {data['warning']}"
                return msg
            return f"❌ {data.get('error', '添加失败')}"
        return "用法: /通讯录 添加 <姓名>"

    if arg.startswith("找 ") or arg.startswith("查 ") or arg.startswith("find "):
        query = arg.split(maxsplit=1)[1] if " " in arg else ""
        if query:
            return _format_find_result(query, limit=limit)
        return "用法: /通讯录 找 <姓名或关键词>"

    if arg.startswith("删除 ") or arg.startswith("delete "):
        cid = arg.split(maxsplit=1)[1].strip() if " " in arg else ""
        if cid:
            raw = tool_contact_delete(contact_id=cid)
            data = json.loads(raw)
            if data.get("ok"):
                return f"✅ 联系人 [{data['deleted'][:4]}] 已删除"
            return f"❌ {data.get('error', '操作失败')}"
        return "用法: /通讯录 删除 <id>"

    return _format_contact_list(limit=limit)


def _format_contact_list(*, limit: int = 20) -> str:
    all_contacts = _load_all()
    all_contacts.sort(key=lambda c: c.get("name", "").lower())

    if not all_contacts:
        return "📒 通讯录为空\n\n添加: /通讯录 添加 <姓名>\n或对话中说「帮我记一下XX的联系方式」"

    lines = [f"📒 通讯录 ({len(all_contacts)}人)\n"]
    cat_icons = {
        "personal": "👤", "work": "💼", "service": "🔧",
        "medical": "🏥", "other": "📋",
    }

    for c in all_contacts[:limit]:
        icon = cat_icons.get(c.get("category", "personal"), "👤")
        cid = c["id"][:4]
        name = c.get("name", "")
        line = f"{icon} [{cid}] {name}"

        details = []
        phones = c.get("phone", [])
        if phones:
            details.append(f"📞 {phones[0]}")
        emails = c.get("email", [])
        if emails:
            details.append(f"📧 {emails[0]}")
        if details:
            line += f"  {'  '.join(details)}"
        lines.append(line)

    if len(all_contacts) > limit:
        lines.append(f"\n... 还有 {len(all_contacts) - limit} 人")
    lines.append("\n/通讯录 找 <姓名>  查找联系人")
    return "\n".join(lines)


def _format_find_result(query: str, *, limit: int = 20) -> str:
    raw = tool_contact_find(query=query, limit=limit)
    data = json.loads(raw)
    contacts = data.get("contacts", [])
    if not contacts:
        return f"🔍 未找到「{query}」相关联系人"

    lines = [f"🔍 搜索「{query}」找到 {len(contacts)} 人\n"]
    for c in contacts:
        cid = c["id"][:4]
        name = c.get("name", "")
        line = f"[{cid}] {name}"
        details = []
        for p in c.get("phone", []):
            details.append(f"📞{p}")
        for e in c.get("email", []):
            details.append(f"📧{e}")
        if c.get("address"):
            details.append(f"📍{c['address'][:30]}")
        if details:
            line += f"\n   {'  '.join(details)}"
        if c.get("notes"):
            line += f"\n   💬 {c['notes'][:50]}"
        lines.append(line)
    return "\n".join(lines)


# ── Registration ───────────────────────────────────────────────


def register_contact_tools(register: Callable[..., None]) -> None:
    if not _contacts_enabled():
        return

    register(
        name="contact_add",
        description=(
            "添加联系人到主人的通讯录。记录姓名、电话、邮箱、地址等。"
            "用于记录医生、维修工、朋友、同事等联系方式。"
        ),
        schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "联系人姓名"},
                "phone": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "电话号码列表",
                },
                "email": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "邮箱列表",
                },
                "address": {"type": "string", "description": "地址"},
                "category": {
                    "type": "string",
                    "enum": list(_VALID_CATEGORIES),
                    "description": "分类: personal/work/service/medical/other",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "标签列表（如：牙科、装修、大学同学）",
                },
                "notes": {"type": "string", "description": "备注信息"},
            },
            "required": ["name"],
        },
        handler=tool_contact_add,
        toolset="contacts",
    )

    register(
        name="contact_find",
        description="按姓名、电话、标签等关键词搜索联系人。",
        schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词（姓名/电话/标签/备注）"},
                "category": {
                    "type": "string",
                    "enum": list(_VALID_CATEGORIES),
                    "description": "按分类筛选",
                },
                "limit": {"type": "integer", "description": "最多返回条数"},
            },
            "required": ["query"],
        },
        handler=tool_contact_find,
        toolset="contacts",
    )

    register(
        name="contact_update",
        description="更新联系人信息。可修改电话、邮箱、地址、备注等。",
        schema={
            "type": "object",
            "properties": {
                "contact_id": {"type": "string", "description": "联系人 ID（支持前缀匹配）"},
                "name": {"type": "string", "description": "新姓名"},
                "phone": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "新电话列表（替换原有）",
                },
                "email": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "新邮箱列表（替换原有）",
                },
                "address": {"type": "string", "description": "新地址"},
                "category": {
                    "type": "string",
                    "enum": list(_VALID_CATEGORIES),
                    "description": "新分类",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "新标签列表（替换原有）",
                },
                "notes": {"type": "string", "description": "新备注"},
            },
            "required": ["contact_id"],
        },
        handler=tool_contact_update,
        toolset="contacts",
    )

    register(
        name="contact_delete",
        description="删除一个联系人。",
        schema={
            "type": "object",
            "properties": {
                "contact_id": {"type": "string", "description": "联系人 ID（支持前缀匹配）"},
            },
            "required": ["contact_id"],
        },
        handler=tool_contact_delete,
        toolset="contacts",
    )

    register(
        name="contact_list",
        description="列出所有联系人，可按分类筛选。",
        schema={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": list(_VALID_CATEGORIES),
                    "description": "按分类筛选",
                },
                "limit": {"type": "integer", "description": "最多返回条数"},
            },
        },
        handler=tool_contact_list,
        toolset="contacts",
    )
