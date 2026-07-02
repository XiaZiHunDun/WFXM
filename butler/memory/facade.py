"""Orchestrator-facing memory facade (tools, prefetch, post-session buffer).

Primary import: ``butler.memory.facade.ButlerMemoryService``.
Legacy path ``butler.memory_plugin`` re-exports the same types.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

# Hermes ``MemoryProvider`` adapter lives in ``plugins/memory/butler/`` only.

from butler.core.best_effort import safe_best_effort
from butler.memory import ButlerMemory, ProjectMemory
from butler.memory.facade_ops import (
    butler_home_configured,
    close_butler_memory,
    discover_project_root,
    emit_recall_metric,
    emit_write_metric,
    manager_current_project,
    owner_write_approval_result,
    prefetch_global_context,
    prefetch_project_context,
    record_recall_telemetry,
    refresh_project_facts,
    resolve_active_project_name,
    strip_private_tags_safe,
)

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
                "description": "append (default); project_notes: remove/replace bullet; "
                "owner_profile: remove by keyword (old_content), replace entry or full profile.",
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
    "description": "Search experience (FTS/hybrid), read owner profile, or project MEMORY+facts (scope=project).",
    "parameters": {
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "enum": ["experience", "profile", "project", "coding", "transcript", "observation", "hybrid"],
                "default": "experience",
            },
            "query": {"type": "string", "description": "Search query (experience scope)."},
            "limit": {"type": "integer", "description": "Max rows (experience).", "default": 8},
            "offset": {
                "type": "integer",
                "description": "Scroll offset (transcript scope).",
                "default": 0,
            },
            "project": {
                "type": "string",
                "description": "Optional Butler project filter; defaults to Butler env / active project.",
            },
        },
        "required": [],
    },
}


def _extract_hit_texts(rows: list[dict]) -> list[str]:
    texts: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in ("content", "text", "bullet", "fact", "preview", "pattern"):
            val = row.get(key)
            if val:
                texts.append(str(val))
    return texts


class ButlerMemoryService:
    """Butler layered memory (global + project) for prefetch, sync_turn, tools."""

    def __init__(self) -> None:
        self._session_id = ""
        self._hermes_home = ""
        self._user_id = ""
        self._butler_global: ButlerMemory | None = None
        self._project_memory: ProjectMemory | None = None
        self._project_root: Path | None = None
        self._orchestrator: Any | None = None

    def link_orchestrator(self, orchestrator: Any) -> None:
        """Use orchestrator-owned memory instances (M1 single-instance binding)."""
        self._orchestrator = orchestrator
        self._reload_butler_global()
        self._reload_project_branch()

    @property
    def name(self) -> str:
        return "butler"

    def is_available(self) -> bool:
        return butler_home_configured()

    def initialize(self, session_id: str, **kwargs) -> None:
        self._session_id = session_id or ""
        self._hermes_home = str(kwargs.get("hermes_home", "") or "")
        self._user_id = str(kwargs.get("user_id", "") or "")


        self._reload_butler_global()
        self._project_root = discover_project_root()
        self._reload_project_branch()

        logger.debug(
            "ButlerMemoryProvider initialized session=%s hermes_home=%s user=%s root=%s",
            self._session_id,
            self._hermes_home,
            self._user_id,
            self._project_root,
        )

    def _reload_butler_global(self) -> None:
        orch = self._orchestrator
        if orch is not None:
            self._butler_global = orch.butler_memory
            return

        from butler.config import get_butler_settings
        from butler.project.manager import get_project_manager
        from butler.tenant import resolve_tenant_for_project

        settings = get_butler_settings()
        project = safe_best_effort(
            lambda: get_project_manager().get_current(),
            label="memory.facade.reload_global_project",
            default=None,
        )
        tid = resolve_tenant_for_project(project, settings)
        if (
            self._butler_global is None
            or getattr(self._butler_global, "tenant_id", None) != tid
        ):
            prev = self._butler_global
            if prev is not None:
                close_butler_memory(prev)
            self._butler_global = ButlerMemory(settings.butler_home, tenant_id=tid)

    def _reload_project_branch(self) -> None:
        orch = self._orchestrator
        if orch is not None:
            self._project_memory = getattr(orch, "_project_memory", None)
            ws = orch._project_workspace() if hasattr(orch, "_project_workspace") else None
            self._project_root = ws.resolve() if ws is not None else None
            return

        root = self._project_root or discover_project_root()
        self._project_root = root
        if root:
            try:
                self._project_memory = ProjectMemory(root)
                refresh_project_facts(self._project_memory)
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
        if self._orchestrator is not None:
            from butler.session.lifecycle import prefetch_turn_memory

            merged = prefetch_turn_memory(self._orchestrator, query, use_cache=False)
            if not merged.strip():
                return ""
            return "**Butler layered memory**\n\n" + merged

        del session_id

        ctx_parts: list[str] = []

        root = self._project_root or discover_project_root()
        if root != self._project_root:
            self._project_root = root
            self._reload_project_branch()

        self._reload_butler_global()

        if self._butler_global is not None:
            ctx_parts.append(
                prefetch_global_context(self._butler_global, root=root)
            )

        if self._project_memory is not None:
            ctx_parts.append(prefetch_project_context(self._project_memory))

        qbits = ""
        qr = (query or "").strip()
        if qr and self._butler_global is not None:
            pname = manager_current_project() or self._guess_project_slug(root)

            from butler.session.lifecycle import _filter_ephemeral_experience

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
            return manager_current_project()
        return proj_root.name

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        """Accumulate turn pairs; incremental post_session via session_lifecycle."""
        if not user_content and not assistant_content:
            return
        if self._orchestrator is not None:
            from butler.session.lifecycle import record_post_session_turn

            record_post_session_turn(
                self._orchestrator,
                self,
                user_content,
                assistant_content,
                session_id=session_id,
            )
            return

        if not hasattr(self, "_turn_buffer"):
            self._turn_buffer: list[dict] = []
        self._turn_buffer.append({"role": "user", "content": user_content})
        self._turn_buffer.append({"role": "assistant", "content": assistant_content})
        if len(self._turn_buffer) >= 8:
            self._trigger_background_extraction_standalone()

    def clear_turn_buffer(self) -> None:
        """Discard buffered turns after /new so post-session extraction does not replay old chat."""
        if hasattr(self, "_turn_buffer"):
            self._turn_buffer.clear()

    def _standalone_orchestrator_view(self) -> Any:
        from types import SimpleNamespace

        return SimpleNamespace(
            butler_memory=self._butler_global,
            _project_memory=self._project_memory,
            _skill_manager=None,
            project_manager=SimpleNamespace(current_project=resolveresolve_active_project_name()),
        )

    def _trigger_background_extraction_standalone(self) -> None:
        """Unlinked provider fallback (tests / legacy) via session_lifecycle runner."""
        from butler.session.lifecycle import run_post_session_extraction

        messages = list(self._turn_buffer)
        self._turn_buffer.clear()
        run_post_session_extraction(
            self._standalone_orchestrator_view(),
            messages,
            background=True,
            session_id=self._session_id,
        )

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
        stripped = strip_private_tags_safe(content)
        if stripped is not None:
            content, fully_private = stripped
            if fully_private:
                return json.dumps(
                    {"ok": True, "skipped": True, "reason": "content entirely <private>"},
                )
        if not content and str(args.get("action", "append") or "append").strip().lower() != "remove":
            return json.dumps({"ok": False, "error": "content is empty"})

        action = str(args.get("action", "append") or "append").strip().lower()
        pending = owner_write_approval_result(args)
        if pending is not None:
            return json.dumps(pending, ensure_ascii=False)

        return self._remember_direct(args)

    def _remember_direct(self, args: Dict[str, Any]) -> str:
        if self._butler_global is None:
            return json.dumps({"ok": False, "error": "ButlerMemory not initialized"})

        scope = str(args.get("scope") or "")
        content = str(args.get("content") or "").strip()
        if not content and str(args.get("action", "append") or "append").strip().lower() != "remove":
            return json.dumps({"ok": False, "error": "content is empty"})

        category = str(args.get("category", "") or "general")

        if scope == "owner_profile":
            action = str(args.get("action", "append") or "append").strip().lower()
            old_content = str(args.get("old_content", "") or "").strip()
            prof = self._butler_global.profile
            if action == "remove":
                key = old_content or content
                result = prof.remove(key)
            elif action == "replace":
                if old_content:
                    rem = prof.remove(old_content)
                    if not rem.get("success"):
                        return json.dumps(
                            {
                                "ok": False,
                                "scope": scope,
                                "error": rem.get("error", "remove failed"),
                            }
                        )
                    result = prof.add(content)
                else:
                    result = prof.replace(content)
            else:
                result = prof.add(content)
            ok = bool(result.get("success"))
            if ok:
                from butler.core.best_effort import safe_best_effort

                safe_best_effort(
                    lambda: self._butler_global.sync_profile_vectors(),
                    label="memory.facade.sync_profile_vectors",
                )
            _emit_write_metric(scope, ok, content=content if ok else "")
            payload: dict[str, Any] = {"ok": ok, "scope": scope, "action": action}
            if not ok:
                payload["error"] = result.get("error", "profile write failed")
            return json.dumps(payload)

        if scope == "owner_experience":
            proj = resolve_active_project_name()

            cat = category or "delegation_note"
            row_id = self._butler_global.add_experience(
                project=proj,
                category=cat,
                content=content,
            )
            _emit_write_metric(scope, True, content=content)
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

            if cls_result != "pending":
                _emit_write_metric(scope, True, content=content)
            else:
                _emit_write_metric(scope, True)
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

        mode = str(args.get("mode") or "full").strip().lower()
        if mode and mode != "full":
            from butler.memory.recall_layers import dispatch_recall_mode

            return dispatch_recall_mode(self, args, mode)

        scope = str(args.get("scope", "experience") or "experience")
        if scope == "profile":
            text = self._butler_global.profile.read()
            return json.dumps({"ok": True, "profile": text})

        if scope == "coding":
            from butler.config import get_butler_home
            from butler.memory.coding_recall import search_coding_experiences

            query = str(args.get("query", "") or "").strip()
            limit = max(1, int(args.get("limit", 8) or 8))
            proj_name = resolve_active_project_name() or str(args.get("project") or "").strip()
            ws = getattr(self._project_memory, "project_dir", None) if self._project_memory else None
            if ws is None and self._project_root:
                ws = self._project_root
            payload = search_coding_experiences(
                query,
                limit=limit,
                project_id=proj_name,
                project_workspace=Path(ws) if ws else None,
                butler_home=get_butler_home(),
            )
            if payload.get("ok") and query:
                record_recall_telemetry(
                    {
                        "mode": "coding-keyword",
                        "fallbacks": 0,
                        "candidates": len(payload.get("results") or []),
                        "query": query,
                        "scope": "coding",
                    }
                )
            emit_recall_metric(
                "coding",
                query,
                len(payload.get("results") or []),
                hit_texts=_extract_hit_texts(payload.get("results") or []),
            )
            return json.dumps(payload, ensure_ascii=False)

        if scope == "transcript":
            from butler.execution_context import get_current_session_key
            from butler.memory.transcript_recall import search_transcript_recall

            query = str(args.get("query", "") or "").strip()
            limit = max(1, int(args.get("limit", 8) or 8))
            offset = max(0, int(args.get("offset") or 0))
            payload = search_transcript_recall(
                query,
                session_key=get_current_session_key() or "",
                limit=limit,
                offset=offset,
            )
            emit_recall_metric(
                "transcript",
                query,
                int(payload.get("count") or len(payload.get("results") or [])),
                hit_texts=_extract_hit_texts(payload.get("results") or []),
            )
            return json.dumps(payload, ensure_ascii=False)

        if scope == "observation":
            from butler.memory.observation_recall import search_observation_recall

            query = str(args.get("query", "") or "").strip()
            limit = max(1, int(args.get("limit", 8) or 8))
            ws = getattr(self._project_memory, "project_dir", None) if self._project_memory else None
            if ws is None and self._project_root:
                ws = self._project_root
            payload = search_observation_recall(
                query,
                project_workspace=Path(ws) if ws else None,
                limit=limit,
            )
            emit_recall_metric(
                "observation",
                query,
                int(payload.get("count") or len(payload.get("results") or [])),
                hit_texts=_extract_hit_texts(payload.get("results") or []),
            )
            return json.dumps(payload, ensure_ascii=False)

        if scope == "hybrid":
            from butler.config import get_butler_home
            from butler.memory.unified_recall import unified_hybrid_search

            query = str(args.get("query", "") or "").strip()
            limit = max(1, int(args.get("limit", 8) or 8))
            proj_name = resolve_active_project_name() or str(args.get("project") or "").strip()
            pm = self._project_memory
            ws = getattr(pm, "project_dir", None) if pm else None
            if ws is None and self._project_root:
                ws = self._project_root
            payload = unified_hybrid_search(
                query,
                butler_memory=self._butler_global,
                project_memory=pm,
                project_name=proj_name,
                project_workspace=Path(ws) if ws else None,
                butler_home=get_butler_home(),
                limit=limit,
            )
            emit_recall_metric(
                "hybrid",
                query,
                len(payload.get("results") or []),
                hit_texts=_extract_hit_texts(payload.get("results") or []),
            )
            return json.dumps(payload, ensure_ascii=False)

        if scope == "project":
            pm = self._project_memory
            if pm is None:
                root = discover_project_root()
                if root:
                    pm = ProjectMemory(root)
                    refresh_project_facts(pm)
            if pm is None:
                return json.dumps({"ok": False, "error": "no active project"})
            query = str(args.get("query", "") or "").strip()
            limit = max(1, int(args.get("limit", 8) or 8))
            proj_name = resolve_active_project_name()
            facts_text = pm.facts_for_prefetch(max_chars=800)
            hits: list[dict[str, Any]] = []
            if query:
                from butler.memory.semantic_config import semantic_memory_enabled
                from butler.memory.semantic_index import SemanticMemoryIndex
                from butler.memory.semantic_project import (
                    prefetch_project_memory_hits,
                    resolve_project_display_name,
                )

                sem = getattr(self._butler_global, "semantic", None)
                if not isinstance(sem, SemanticMemoryIndex):
                    sem = None
                sem_enabled = semantic_memory_enabled()
                display = resolve_project_display_name(pm) or proj_name
                from butler.memory.query_decompose import decompose_query, subquery_enabled

                raw_hits, mode = prefetch_project_memory_hits(
                    pm,
                    query,
                    project_name=display,
                    semantic=sem,
                    limit=limit,
                    semantic_enabled=sem_enabled,
                )
                sub_queries = (
                    decompose_query(query)
                    if subquery_enabled() and query
                    else [query]
                )
                hits = [
                    {
                        "content": h.get("content", ""),
                        "section": h.get("section", ""),
                        "mode": mode,
                        "score": h.get("score"),
                        "source_id": h.get("source_id"),
                    }
                    for h in raw_hits
                    if h.get("content")
                ]
                tel: dict[str, Any] = {
                    "mode": f"project-{mode}",
                    "fallbacks": 1 if sem_enabled and mode in {"keyword", "none"} else 0,
                    "candidates": len(hits),
                    "query": query,
                }
                if len(sub_queries) > 1:
                    tel["sub_queries"] = sub_queries
                    tel["mode"] = f"project-{mode}-subquery"
                record_recall_telemetry(tel)
            emit_recall_metric(
                "project",
                query,
                len(hits),
                hit_texts=_extract_hit_texts(hits) + ([facts_text] if facts_text else []),
            )
            return json.dumps(
                {
                    "ok": True,
                    "scope": "project",
                    "facts": facts_text,
                    "results": hits,
                    "project": proj_name,
                }
            )

        from butler.session.lifecycle import filter_non_conversation_experience

        query = str(args.get("query", "") or "").strip()
        limit = max(1, int(args.get("limit", 8) or 8))
        project = str(args.get("project", "") or "").strip()
        semantic = getattr(self._butler_global, "semantic", None)
        proj_filter: str | None = (project or "").strip() or None
        if proj_filter is None:
            proj_filter = resolve_active_project_name() or None

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
                    experience_store=self._butler_global.experience,
                )
            )
        emit_recall_metric(
            "experience",
            query,
            len(rows),
            hit_texts=_extract_hit_texts(rows),
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
