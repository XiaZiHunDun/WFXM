"""Best-effort PIM state persistence helpers (P0-A)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.core.pim_state import DomainIndex
from butler.io.atomic_write import atomic_write_text
from butler.tools.contacts import _store
from butler.tools.memo import _store
from butler.tools.expense import _store
from butler.tools.habits import _store
from butler.tools.reminder import _reminder_store
from butler.core.pim_state import load_pim_state, save_pim_state


def load_pim_state_from_file(path: Path, *, empty_state: Any) -> Any:
    if not path.is_file():
        return empty_state()

    def _run() -> Any:
        data = json.loads(path.read_text(encoding="utf-8"))
        state = empty_state()
        for domain in ("contacts", "memos", "expenses", "habits", "reminders"):
            d = data.get(domain)
            if isinstance(d, dict):

                setattr(
                    state,
                    domain,
                    DomainIndex(
                        count=d.get("count", 0),
                        last_modified=d.get("last_modified", 0.0),
                        last_tool=d.get("last_tool", ""),
                    ),
                )
        state.snapshot_ts = data.get("snapshot_ts", 0.0)
        return state

    result = safe_best_effort(_run, label="pim_state.load", default=None)
    return result if result is not None else empty_state()


def save_pim_state_to_file(path: Path, state: Any) -> None:
    def _run() -> None:

        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            path,
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
        )

    safe_best_effort(_run, label="pim_state.save", default=None)


def refresh_domain_count_safe(state: Any, domain: str) -> None:
    def _run() -> None:
        if domain == "contacts":

            state.contacts.count = _store.count()
        elif domain == "memos":

            state.memos.count = _store.count()
        elif domain == "expenses":

            state.expenses.count = _store.count()
        elif domain == "habits":

            state.habits.count = _store.count()
        elif domain == "reminders":

            state.reminders.count = _reminder_store.count()

    safe_best_effort(_run, label=f"pim_state.refresh.{domain}", default=None)


def update_pim_state_for_tool_safe(tool_name: str, *, domain: str) -> None:
    def _run() -> None:

        state = load_pim_state()
        refresh_domain_count_safe(state, domain)
        state.update_domain(domain, tool_name=tool_name)
        save_pim_state(state)

    safe_best_effort(
        _run,
        label=f"pim_state.on_tool_success.{tool_name}",
        default=None,
    )
