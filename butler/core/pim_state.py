"""PIM state machine — tracks tenant-level PIM index snapshots.

After each successful PIM tool call, the snapshot is updated with
current counts and last-modified timestamps per domain. This bridges
the theoretical model's PIMState tuple to runtime observability.

Theoretical baseline: S = (SessionKey, LoopState, QueueState, MemoryState, PIMState, Role)
PIMState = (I_contacts, I_expenses, I_memos, I_habits, I_reminders)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PIM_TOOL_DOMAIN: dict[str, str] = {
    "contact_add": "contacts",
    "contact_find": "contacts",
    "contact_update": "contacts",
    "contact_delete": "contacts",
    "contact_list": "contacts",
    "memo_add": "memos",
    "memo_list": "memos",
    "memo_search": "memos",
    "memo_update": "memos",
    "memo_delete": "memos",
    "expense_add": "expenses",
    "expense_summary": "expenses",
    "expense_list": "expenses",
    "expense_update": "expenses",
    "expense_search": "expenses",
    "expense_delete": "expenses",
    "habit_create": "habits",
    "habit_checkin": "habits",
    "habit_stats": "habits",
    "habit_list": "habits",
    "habit_update": "habits",
    "habit_delete": "habits",
    "set_reminder": "reminders",
    "list_reminders": "reminders",
    "reminder_list_active": "reminders",
    "cancel_reminder": "reminders",
}


@dataclass
class DomainIndex:
    count: int = 0
    last_modified: float = 0.0
    last_tool: str = ""


@dataclass
class PIMState:
    """Snapshot of per-tenant PIM indices."""

    contacts: DomainIndex = field(default_factory=DomainIndex)
    memos: DomainIndex = field(default_factory=DomainIndex)
    expenses: DomainIndex = field(default_factory=DomainIndex)
    habits: DomainIndex = field(default_factory=DomainIndex)
    reminders: DomainIndex = field(default_factory=DomainIndex)
    snapshot_ts: float = 0.0

    def update_domain(self, domain: str, *, tool_name: str, count: int | None = None) -> None:
        idx = getattr(self, domain, None)
        if idx is None:
            return
        idx.last_modified = time.time()
        idx.last_tool = tool_name
        if count is not None:
            idx.count = count
        self.snapshot_ts = time.time()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary_line(self) -> str:
        parts: list[str] = []
        for name in ("contacts", "memos", "expenses", "habits", "reminders"):
            idx: DomainIndex = getattr(self, name)
            if idx.count > 0 or idx.last_modified > 0:
                parts.append(f"{name}={idx.count}")
        return ", ".join(parts) if parts else "(empty)"


def _state_path() -> Path:
    import os

    from butler.config import get_butler_home
    from butler.tenant import DEFAULT_TENANT, tenant_root

    tenant_id = os.getenv("BUTLER_TENANT", DEFAULT_TENANT)
    root = tenant_root(get_butler_home(), tenant_id)
    return root / "_pim_state.json"


def load_pim_state() -> PIMState:
    path = _state_path()
    if not path.is_file():
        return PIMState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        state = PIMState()
        for domain in ("contacts", "memos", "expenses", "habits", "reminders"):
            d = data.get(domain)
            if isinstance(d, dict):
                setattr(state, domain, DomainIndex(
                    count=d.get("count", 0),
                    last_modified=d.get("last_modified", 0.0),
                    last_tool=d.get("last_tool", ""),
                ))
        state.snapshot_ts = data.get("snapshot_ts", 0.0)
        return state
    except Exception as exc:
        logger.debug("load_pim_state failed: %s", exc)
        return PIMState()


def save_pim_state(state: PIMState) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from butler.io.atomic_write import atomic_write_text

        atomic_write_text(path, json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
    except Exception as exc:
        logger.debug("save_pim_state failed: %s", exc)


def _refresh_domain_count(state: PIMState, domain: str) -> None:
    """Refresh actual record count from TenantStore."""
    try:
        if domain == "contacts":
            from butler.tools.contacts import _store
            state.contacts.count = _store.count()
        elif domain == "memos":
            from butler.tools.memo import _store
            state.memos.count = _store.count()
        elif domain == "expenses":
            from butler.tools.expense import _store
            state.expenses.count = _store.count()
        elif domain == "habits":
            from butler.tools.habits import _store
            state.habits.count = _store.count()
        elif domain == "reminders":
            from butler.tools.reminder import _reminder_store
            state.reminders.count = _reminder_store.count()
    except Exception as exc:
        logger.debug("_refresh_domain_count(%s) failed: %s", domain, exc)


def on_pim_tool_success(tool_name: str) -> None:
    """Called after a PIM tool completes successfully. Updates PIMState snapshot."""
    domain = _PIM_TOOL_DOMAIN.get(tool_name)
    if not domain:
        return
    try:
        state = load_pim_state()
        _refresh_domain_count(state, domain)
        state.update_domain(domain, tool_name=tool_name)
        save_pim_state(state)
    except Exception as exc:
        logger.debug("on_pim_tool_success(%s) skipped: %s", tool_name, exc)
