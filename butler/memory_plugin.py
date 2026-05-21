"""Hermes MemoryProvider backed by Butler's layered memory.

Use with ``memory.provider: butler`` after registering this module as the
Hermes bundled plugin ``plugins/memory/butler`` (thin re-export wrapper),
or instantiate ``ButlerMemoryProvider`` and attach it programmatically.

The Butler orchestrator prefers :class:`~butler.memory.ButlerMemory`
embedded in prompts; this provider mirrors the same stores for prefetch/
tool execution inside the Hermes agent loop without editing core Hermes files.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

# Hermes ``MemoryProvider`` adapter lives in ``plugins/memory/butler/`` only.

from butler.memory import ButlerMemory, ProjectMemory

logger = logging.getLogger(__name__)

_REMEMBER_SCHEMA = {
    "name": "butler_remember",
    "description": (
        "Write into Butler layered memory — owner/profile scope ( ~/.butler ) "
        "or the active project MEMORY.md."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "enum": ["owner_profile", "owner_experience", "project_notes"],
                "description": "owner_profile=user preferences; owner_experience=cross-project log; "
                "project_notes=current project MEMORY.md MarkdownMemory",
            },
            "content": {"type": "string", "description": "Structured fact / preference to persist."},
            "category": {
                "type": "string",
                "description": "Optional category label (recommended for owner_experience).",
            },
            "section": {
                "type": "string",
                "description": "Markdown section header for project_notes when appending bullets.",
                "default": "Notes",
            },
            "action": {
                "type": "string",
                "enum": ["append", "remove", "replace"],
                "description": "project_notes only: append (default), remove, or replace a bullet.",
                "default": "append",
            },
            "old_content": {
                "type": "string",
                "description": "For remove/replace: exact existing bullet body to match.",
            },
        },
        "required": ["scope", "content"],
    },
}

_RECALL_SCHEMA = {
    "name": "butler_recall",
    "description": "Search Butler experience store (FTS) or read recent owner profile snippets.",
    "parameters": {
        "type": "object",
        "properties": {
            "scope": {"type": "string", "enum": ["experience", "profile"], "default": "experience"},
            "query": {"type": "string", "description": "Search query (experience scope)."},
            "limit": {"type": "integer", "description": "Max rows (experience).", "default": 8},
            "project": {
                "type": "string",
                "description": "Optional Butler project filter; defaults to Butler env / active project.",
            },
        },
        "required": [],
    },
}


def _project_root_explicit() -> Path | None:
    raw = os.environ.get("BUTLER_PROJECT_ROOT", "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def _active_project_name() -> str:
    """Resolve current Butler project name (string), never a Project object."""
    pm = None
    try:
        from butler.execution_context import get_current_orchestrator

        orch = get_current_orchestrator()
        pm = getattr(orch, "project_manager", None) if orch is not None else None
    except Exception:
        pm = None
    if pm is None:
        try:
            from butler.project_manager import get_project_manager

            pm = get_project_manager()
        except Exception:
            return ""
    try:
        if hasattr(pm, "resolve_active_project_name"):
            return str(pm.resolve_active_project_name() or "").strip()
        cur = pm.get_current() if hasattr(pm, "get_current") else None
        if cur is not None:
            return str(getattr(cur, "name", "") or "").strip()
        return str(getattr(pm, "current_project", "") or "").strip()
    except Exception:
        return ""


def _project_root_discovery() -> Path | None:
    exp = _project_root_explicit()
    if exp:
        return exp

    """Best-effort: Butler CLI sets ONLY when a managed project exists."""
    try:
        from butler.project_manager import get_project_manager

        pm = get_project_manager()
        if cur := pm.get_current():
            return Path(cur.workspace).resolve()
    except Exception as exc:
        logger.debug("ButlerMemoryProvider project discovery failed: %s", exc)
    return None


class ButlerMemoryService:
    """Butler layered memory (global + project) for prefetch, sync_turn, tools."""

    def __init__(self) -> None:
        self._session_id = ""
        self._hermes_home = ""
        self._user_id = ""
        self._butler_global: ButlerMemory | None = None
        self._project_memory: ProjectMemory | None = None
        self._project_root: Path | None = None

    @property
    def name(self) -> str:
        return "butler"

    def is_available(self) -> bool:
        try:
            from butler.config import get_butler_home

            return bool(get_butler_home())
        except Exception:
            return True

    def initialize(self, session_id: str, **kwargs) -> None:
        self._session_id = session_id or ""
        self._hermes_home = str(kwargs.get("hermes_home", "") or "")
        self._user_id = str(kwargs.get("user_id", "") or "")

        from butler.config import get_butler_settings

        self._reload_butler_global()
        self._project_root = _project_root_discovery()
        self._reload_project_branch()

        logger.debug(
            "ButlerMemoryProvider initialized session=%s hermes_home=%s user=%s root=%s",
            self._session_id,
            self._hermes_home,
            self._user_id,
            self._project_root,
        )

    def _reload_butler_global(self) -> None:
        from butler.config import get_butler_settings
        from butler.project_manager import get_project_manager
        from butler.tenant import resolve_tenant_for_project

        settings = get_butler_settings()
        try:
            project = get_project_manager().get_current()
        except Exception:
            project = None
        tid = resolve_tenant_for_project(project, settings)
        if (
            self._butler_global is None
            or getattr(self._butler_global, "tenant_id", None) != tid
        ):
            self._butler_global = ButlerMemory(settings.butler_home, tenant_id=tid)

    def _reload_project_branch(self) -> None:
        root = self._project_root or _project_root_discovery()
        self._project_root = root
        if root:
            try:
                self._project_memory = ProjectMemory(root)
            except Exception as exc:
                logger.warning("ButlerMemoryProvider ProjectMemory unavailable: %s", exc)
                self._project_memory = None
        else:
            self._project_memory = None

    def system_prompt_block(self) -> str:
        return (
            "**Butler Memory** (`butler`): Use `butler_remember` and `butler_recall` to persist or "
            "search owner/project context layered under Butler v2 stores."
        )

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        del session_id

        ctx_parts: list[str] = []

        root = self._project_root or _project_root_discovery()
        if root != self._project_root:
            self._project_root = root
            self._reload_project_branch()

        self._reload_butler_global()

        try:
            try:
                from butler.project_manager import get_project_manager

                current = get_project_manager().current_project or ""
            except Exception:
                current = ""
            if not current:
                current = self._guess_project_slug(root)
            ctx_parts.append(self._butler_global.get_system_context(current))
        except Exception as exc:
            logger.debug("Butler global memory prefetch skipped: %s", exc)

        if self._project_memory is not None:
            try:
                ctx_parts.append(self._project_memory.get_full_context(max_lines=30))
            except Exception as exc:
                logger.debug("Butler project memory prefetch skipped: %s", exc)

        qbits = ""
        qr = (query or "").strip()
        if qr and self._butler_global is not None:
            pname = ""
            try:
                from butler.project_manager import get_project_manager

                pname = get_project_manager().current_project or ""
            except Exception:
                pname = self._guess_project_slug(root)

            from butler.session_lifecycle import _filter_ephemeral_experience

            hits = _filter_ephemeral_experience(
                self._butler_global.experience.search(
                    qr, project=pname if pname else None, limit=8
                )
            )
            if hits:
                lines = [f"- [{h.get('project', '')}] {h.get('content', '')}".strip() for h in hits]
                qbits = "## Query-aligned Butler experience\n" + "\n".join(lines)

        out = []
        merged = "\n\n".join(p for p in ctx_parts if p and p.strip())
        if merged.strip():
            out.append(merged)
        if qbits:
            out.append(qbits)

        rendered = "\n\n".join(out)
        prefix = "**Butler layered memory**\n\n" if rendered.strip() else ""
        return prefix + rendered if rendered.strip() else ""

    @staticmethod
    def _guess_project_slug(proj_root: Path | None) -> str:
        if proj_root is None:
            try:
                from butler.project_manager import get_project_manager

                return get_project_manager().current_project or ""
            except Exception:
                return ""
        return proj_root.name

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        """Accumulate turn pairs; trigger background extraction when threshold reached."""
        if not user_content and not assistant_content:
            return
        if not hasattr(self, "_turn_buffer"):
            self._turn_buffer: list[dict] = []
        self._turn_buffer.append({"role": "user", "content": user_content})
        self._turn_buffer.append({"role": "assistant", "content": assistant_content})

        if len(self._turn_buffer) >= 8:
            self._trigger_background_extraction()

    def clear_turn_buffer(self) -> None:
        """Discard buffered turns after /new so post-session extraction does not replay old chat."""
        if hasattr(self, "_turn_buffer"):
            self._turn_buffer.clear()

    def _trigger_background_extraction(self) -> None:
        """Run PostSessionProcessor in background thread to avoid blocking."""
        import threading
        messages = list(self._turn_buffer)
        self._turn_buffer.clear()

        def _run():
            import asyncio
            try:
                from butler.post_session import PostSessionProcessor
                processor = PostSessionProcessor()

                from butler.transport.auxiliary_client import auxiliary_llm_call_factory

                processor.set_llm_call(auxiliary_llm_call_factory("post_session"))

                skill_mgr = None
                try:
                    from butler.config import get_butler_settings
                    from butler.skills.manager import SkillManager
                    settings = get_butler_settings()
                    skill_mgr = SkillManager(skills_dir=settings.butler_home / "skills")
                except Exception:
                    pass

                result = asyncio.run(processor.process(
                    messages=messages,
                    butler_memory=self._butler_global,
                    project_memory=self._project_memory,
                    skill_manager=skill_mgr,
                ))
                if result.get("memory_updates") or result.get("skills_extracted"):
                    logger.info(
                        "Background extraction: %d memory updates, %d skills",
                        result.get("memory_updates", 0),
                        result.get("skills_extracted", 0),
                    )
            except Exception as exc:
                logger.warning("Background extraction failed: %s", exc)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [_REMEMBER_SCHEMA, _RECALL_SCHEMA]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        del kwargs
        try:
            if tool_name == "butler_remember":
                return self._remember(args)
            if tool_name == "butler_recall":
                return self._recall(args)
            return json.dumps({"ok": False, "error": f"unknown tool {tool_name}"})
        except Exception as exc:
            logger.error("ButlerMemoryProvider tool failure: %s", exc)
            return json.dumps({"ok": False, "error": str(exc)})

    def _remember(self, args: Dict[str, Any]) -> str:
        if self._butler_global is None:
            return json.dumps({"ok": False, "error": "ButlerMemory not initialized"})

        scope = str(args.get("scope") or "")
        content = str(args.get("content") or "").strip()
        if not content:
            return json.dumps({"ok": False, "error": "content is empty"})

        category = str(args.get("category", "") or "general")

        if scope == "owner_profile":
            ok = self._butler_global.profile.add(content).get("success")
            return json.dumps({"ok": ok, "scope": scope})

        if scope == "owner_experience":
            proj = _active_project_name()

            cat = category or "delegation_note"
            row_id = self._butler_global.experience.add(
                project=proj,
                category=cat,
                content=content,
            )
            from butler.memory.semantic_index import index_experience_row

            index_experience_row(
                getattr(self._butler_global, "semantic", None),
                row_id,
                project=proj,
                category=cat,
                content=content,
            )
            return json.dumps({"ok": True, "id": row_id, "scope": scope})

        if scope == "project_notes":
            if self._project_memory is None:
                self._reload_project_branch()
            if self._project_memory is None:
                return json.dumps(
                    {"ok": False, "error": "No active Butler project path (BUTLER_PROJECT_ROOT unset)."}
                )
            section = str(args.get("section", "Notes") or "Notes")
            action = str(args.get("action", "append") or "append").strip().lower()
            old_content = str(args.get("old_content", "") or "").strip()
            from butler.memory.semantic_project import (
                index_project_memory_bullet,
                invalidate_pending_vector,
                invalidate_project_memory_bullet,
                resolve_project_display_name,
                sync_project_append_vectors,
            )

            sem = getattr(self._butler_global, "semantic", None)
            proj_name = resolve_project_display_name(self._project_memory)
            md = self._project_memory.markdown

            if action == "remove":
                old = old_content or content
                if not md.remove_bullet(section, old):
                    return json.dumps(
                        {"ok": False, "error": f"未找到章节 {section} 中的条目: {old[:80]}"}
                    )
                invalidate_project_memory_bullet(sem, proj_name, section, old)
                invalidate_pending_vector(sem, proj_name, old)
                return json.dumps(
                    {"ok": True, "scope": scope, "action": "remove", "section": section}
                )

            if action == "replace":
                if not old_content:
                    return json.dumps(
                        {"ok": False, "error": "replace 需要 old_content（原条目正文）"}
                    )
                if not md.replace_bullet(section, old_content, content):
                    return json.dumps(
                        {
                            "ok": False,
                            "error": f"未找到章节 {section} 中的条目: {old_content[:80]}",
                        }
                    )
                invalidate_project_memory_bullet(sem, proj_name, section, old_content)
                invalidate_pending_vector(sem, proj_name, old_content)
                index_project_memory_bullet(sem, proj_name, section, content)
                return json.dumps(
                    {
                        "ok": True,
                        "scope": scope,
                        "action": "replace",
                        "section": section,
                    }
                )

            cls_result = md.append(section, content, classification="auto")
            sync_project_append_vectors(
                sem, proj_name, section, content, cls_result
            )

            payload: dict[str, Any] = {
                "ok": True,
                "scope": scope,
                "section": section,
                "classification": cls_result,
                "action": "append",
            }
            if cls_result == "pending":
                payload["hint"] = "已进入 Pending，可用 /记忆待审 与 /批准记忆 写入正式章节"
            return json.dumps(payload)

        return json.dumps({"ok": False, "error": f"invalid scope {scope!r}"})

    def _recall(self, args: Dict[str, Any]) -> str:
        if self._butler_global is None:
            return json.dumps({"ok": False, "error": "ButlerMemory not initialized"})

        scope = str(args.get("scope", "experience") or "experience")
        if scope == "profile":
            text = self._butler_global.profile.read()
            return json.dumps({"ok": True, "profile": text})

        from butler.session_lifecycle import filter_non_conversation_experience

        query = str(args.get("query", "") or "").strip()
        limit = max(1, int(args.get("limit", 8) or 8))
        project = str(args.get("project", "") or "").strip()
        semantic = getattr(self._butler_global, "semantic", None)
        proj_filter: str | None = (project or "").strip() or None
        if proj_filter is None:
            proj_filter = _active_project_name() or None

        from butler.memory.semantic_index import hybrid_experience_search

        if not query:
            recent = self._butler_global.experience.get_recent(limit=limit * 4)
            rows = filter_non_conversation_experience(recent)[:limit]
        else:
            rows = filter_non_conversation_experience(
                hybrid_experience_search(
                    semantic,
                    self._butler_global.experience.search,
                    query,
                    project=proj_filter,
                    limit=limit,
                )
            )
        return json.dumps({"ok": True, "results": rows, "semantic": semantic is not None})

    def on_session_switch(
        self,
        new_session_id: str,
        *,
        parent_session_id: str = "",
        reset: bool = False,
        **kwargs,
    ) -> None:
        del parent_session_id
        del reset
        del kwargs
        self._session_id = new_session_id or ""
        self._reload_project_branch()


# Backward-compatible alias (tests, orchestrator).
ButlerMemoryProvider = ButlerMemoryService

__all__ = ["ButlerMemoryService", "ButlerMemoryProvider"]
