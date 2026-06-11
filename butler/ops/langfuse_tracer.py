"""Optional LangFuse tracing integration (opt-in via BUTLER_LANGFUSE_ENABLED=1).

Provides a thin wrapper that creates LangFuse traces/spans from
AgentLoop callbacks. Zero-cost when disabled: all public functions
are no-ops if langfuse is not installed or env flag is off.

Usage (gateway)::

    from butler.ops.langfuse_tracer import langfuse_callbacks, flush_langfuse
    cbs = langfuse_callbacks(session_key="wechat:u1")
    # merge with existing callbacks ...
    # at turn end:
    flush_langfuse()

Env vars:
    BUTLER_LANGFUSE_ENABLED=1
    LANGFUSE_HOST=http://localhost:3000
    LANGFUSE_PUBLIC_KEY=pk-...
    LANGFUSE_SECRET_KEY=sk-...
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

_langfuse_client: Any = None
_initialised = False
_project_clients: dict[str, Any] = {}


def langfuse_enabled() -> bool:
    return os.getenv("BUTLER_LANGFUSE_ENABLED", "0").strip() in ("1", "true", "yes")


def _get_client(project_id: str = "") -> Any:
    """Get a LangFuse client, optionally for a specific project.

    Multi-project support: if a per-project langfuse.json exists, create
    a dedicated client with that project's API keys.
    """
    if project_id and project_id in _project_clients:
        return _project_clients[project_id]

    if project_id:
        try:
            from butler.config import get_project_langfuse_config

            cfg = get_project_langfuse_config(project_id)
            if cfg and cfg.get("langfuse_public_key"):
                from langfuse import Langfuse  # type: ignore[import-untyped]

                client = Langfuse(
                    host=cfg.get("langfuse_host", os.getenv("LANGFUSE_HOST", "http://localhost:3000")),
                    public_key=cfg["langfuse_public_key"],
                    secret_key=cfg.get("langfuse_secret_key", ""),
                )
                _project_clients[project_id] = client
                logger.info("LangFuse project client for %s initialised", project_id)
                return client
        except ImportError:
            pass
        except Exception as exc:
            logger.debug("LangFuse project client init for %s: %s", project_id, exc)

    global _langfuse_client, _initialised
    if _initialised:
        return _langfuse_client
    _initialised = True
    if not langfuse_enabled():
        return None
    try:
        from langfuse import Langfuse  # type: ignore[import-untyped]

        _langfuse_client = Langfuse(
            host=os.getenv("LANGFUSE_HOST", "http://localhost:3000"),
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
        )
        logger.info("LangFuse tracer initialised (host=%s)", os.getenv("LANGFUSE_HOST"))
    except ImportError:
        logger.debug("langfuse package not installed; tracing disabled")
    except Exception as exc:
        logger.warning("LangFuse init failed: %s", exc)
    return _langfuse_client


def flush_langfuse() -> None:
    """Flush pending events. Call at turn boundary or shutdown."""
    client = _get_client()
    if client is not None:
        try:
            client.flush()
        except Exception as exc:
            logger.debug("LangFuse flush: %s", exc)


def shutdown_langfuse() -> None:
    """Graceful shutdown. Call at process exit."""
    global _langfuse_client, _initialised
    client = _langfuse_client
    if client is not None:
        try:
            client.shutdown()
        except Exception:
            pass
    _langfuse_client = None
    _initialised = False


def _default_project_name() -> str:
    return os.getenv("BUTLER_PROJECT_NAME", "butler-v4")


def _default_tenant() -> str:
    return os.getenv("BUTLER_TENANT", "")


def _detect_session_source(session_key: str) -> str:
    if not session_key:
        return "cli"
    if session_key.startswith("wechat:"):
        return "wechat"
    if session_key.startswith("gateway:"):
        return "gateway"
    return "direct"


class TracingContext:
    """Per-turn tracing context that holds the current trace and spans."""

    def __init__(self, session_key: str = "", metadata: dict[str, Any] | None = None,
                 project_name: str = "", tenant: str = ""):
        self._client = _get_client()
        self._trace: Any = None
        self._llm_span: Any = None
        self._llm_start_time: float = 0.0
        self._tool_spans: dict[str, Any] = {}
        self._session_key = session_key
        self._metadata = metadata or {}

        if project_name or tenant:
            self._metadata.setdefault("project_name", project_name or _default_project_name())
            self._metadata.setdefault("tenant", tenant or _default_tenant())
        else:
            self._metadata.setdefault("project_name", _default_project_name())
            self._metadata.setdefault("tenant", _default_tenant())
        self._metadata.setdefault("session_source", _detect_session_source(session_key))

        if self._client is not None:
            try:
                tags = [f"project:{self._metadata.get('project_name', '')}"]
                if self._metadata.get("tenant"):
                    tags.append(f"tenant:{self._metadata['tenant']}")
                self._trace = self._client.trace(
                    name="butler-turn",
                    session_id=session_key or "cli",
                    metadata=self._metadata,
                    tags=tags,
                )
            except Exception as exc:
                logger.debug("LangFuse trace create: %s", exc)

    @property
    def active(self) -> bool:
        return self._trace is not None

    @property
    def trace_id(self) -> str:
        if self._trace is not None:
            return str(getattr(self._trace, "id", ""))
        return ""

    def on_llm_start(self, messages: list[dict]) -> None:
        if self._trace is None:
            return
        try:
            msg_count = len(messages)
            self._llm_start_time = time.monotonic()
            self._llm_span = self._trace.generation(
                name="llm-call",
                input={"message_count": msg_count, "last_role": messages[-1].get("role", "") if messages else ""},
                metadata={"message_count": msg_count},
            )
        except Exception as exc:
            logger.debug("LangFuse on_llm_start: %s", exc)

    def on_llm_complete(self, response: Any) -> None:
        if self._llm_span is None:
            return
        try:
            elapsed_ms = (time.monotonic() - self._llm_start_time) * 1000.0
            usage = getattr(response, "usage", None)
            usage_dict: dict[str, int] = {}
            if usage is not None:
                usage_dict = {
                    "input": getattr(usage, "prompt_tokens", 0) or 0,
                    "output": getattr(usage, "completion_tokens", 0) or 0,
                    "total": getattr(usage, "total_tokens", 0) or 0,
                }

            content = str(getattr(response, "content", "") or "")
            tool_calls = getattr(response, "tool_calls", None)

            self._llm_span.end(
                output=content[:500] if content else "(tool_calls)" if tool_calls else "(empty)",
                usage=usage_dict or None,
                metadata={
                    "elapsed_ms": round(elapsed_ms, 1),
                    "finish_reason": getattr(response, "finish_reason", ""),
                    "has_tool_calls": bool(tool_calls),
                },
            )
        except Exception as exc:
            logger.debug("LangFuse on_llm_complete: %s", exc)
        finally:
            self._llm_span = None

    def on_llm_error(self, exc: Exception, attempt: int) -> None:
        if self._llm_span is None:
            return
        try:
            self._llm_span.end(
                output=f"ERROR (attempt {attempt}): {type(exc).__name__}: {exc}",
                level="ERROR",
                status_message=str(exc)[:200],
            )
        except Exception as log_exc:
            logger.debug("LangFuse on_llm_error: %s", log_exc)
        finally:
            self._llm_span = None

    def on_tool_start(self, name: str, args: dict) -> None:
        if self._trace is None:
            return
        try:
            span = self._trace.span(
                name=f"tool:{name}",
                input={"tool": name, "args_keys": list(args.keys()) if args else []},
            )
            self._tool_spans[name] = (span, time.monotonic())
        except Exception as exc:
            logger.debug("LangFuse on_tool_start: %s", exc)

    def on_tool_complete(self, name: str, result: str) -> None:
        entry = self._tool_spans.pop(name, None)
        if entry is None:
            return
        span, start_time = entry
        try:
            elapsed_ms = (time.monotonic() - start_time) * 1000.0
            truncated = result[:300] if result else "(empty)"
            span.end(
                output=truncated,
                metadata={"elapsed_ms": round(elapsed_ms, 1), "result_len": len(result or "")},
            )
        except Exception as exc:
            logger.debug("LangFuse on_tool_complete: %s", exc)

    def on_memory_prefetch(self, query: str, hit: bool, result_count: int = 0, chars: int = 0) -> None:
        """M2: trace memory prefetch as a span."""
        if self._trace is None:
            return
        try:
            span = self._trace.span(
                name="memory:prefetch",
                input={"query": query[:120], "hit": hit, "result_count": result_count},
            )
            span.end(
                output=f"hit={hit} results={result_count} chars={chars}",
                metadata={"hit": hit, "result_count": result_count, "chars": chars},
            )
        except Exception as exc:
            logger.debug("LangFuse on_memory_prefetch: %s", exc)

    def on_memory_write(self, scope: str, success: bool) -> None:
        """M2: trace memory write operations."""
        if self._trace is None:
            return
        try:
            span = self._trace.span(
                name=f"memory:write:{scope}",
                input={"scope": scope, "success": success},
            )
            span.end(
                output=f"success={success}",
                metadata={"scope": scope, "success": success},
            )
        except Exception as exc:
            logger.debug("LangFuse on_memory_write: %s", exc)

    def on_gateway_inbound(self, session_key: str, platform: str, text_len: int) -> None:
        """M2: trace gateway inbound message."""
        if self._trace is None:
            return
        try:
            self._trace.span(
                name="gateway:inbound",
                input={"session_key": session_key, "platform": platform, "text_len": text_len},
            ).end(output=f"session={session_key} platform={platform}")
        except Exception as exc:
            logger.debug("LangFuse on_gateway_inbound: %s", exc)

    def on_gateway_outbound(self, session_key: str, out_len: int, elapsed_s: float = 0.0) -> None:
        """M2: trace gateway outbound response."""
        if self._trace is None:
            return
        try:
            self._trace.span(
                name="gateway:outbound",
                input={"session_key": session_key, "out_len": out_len},
            ).end(
                output=f"out_len={out_len} elapsed={elapsed_s:.1f}s",
                metadata={"out_len": out_len, "elapsed_s": round(elapsed_s, 2)},
            )
        except Exception as exc:
            logger.debug("LangFuse on_gateway_outbound: %s", exc)

    def finish(self, result: Optional[Any] = None) -> None:
        """Close the trace with final result metadata."""
        if self._trace is None:
            return
        try:
            meta: dict[str, Any] = {}
            if result is not None:
                meta["status"] = getattr(result, "status", "unknown")
                meta["iterations"] = getattr(result, "iterations", 0)
                meta["total_tokens"] = getattr(result, "total_tokens", 0)
                meta["tool_calls_made"] = getattr(result, "tool_calls_made", 0)
                meta["elapsed_seconds"] = getattr(result, "elapsed_seconds", 0.0)
            self._trace.update(metadata=meta)
        except Exception as exc:
            logger.debug("LangFuse finish: %s", exc)


_thread_local_ctx: dict[str, TracingContext] = {}


def start_trace(session_key: str = "", metadata: dict[str, Any] | None = None,
                 project_name: str = "", tenant: str = "") -> TracingContext:
    """Create a new tracing context for this turn."""
    ctx = TracingContext(session_key=session_key, metadata=metadata,
                         project_name=project_name, tenant=tenant)
    _thread_local_ctx[session_key or "_default"] = ctx
    return ctx


def get_current_trace(session_key: str = "") -> Optional[TracingContext]:
    return _thread_local_ctx.get(session_key or "_default")


def end_trace(session_key: str = "", result: Any = None) -> None:
    ctx = _thread_local_ctx.pop(session_key or "_default", None)
    if ctx is not None:
        ctx.finish(result)


def langfuse_callbacks(session_key: str = "") -> dict[str, Any]:
    """Return a dict of callback functions suitable for merging into LoopCallbacks.

    Returns empty dict if LangFuse is disabled.
    """
    if not langfuse_enabled():
        return {}

    ctx = start_trace(session_key=session_key)
    if not ctx.active:
        return {}

    return {
        "on_llm_start": ctx.on_llm_start,
        "on_llm_complete": ctx.on_llm_complete,
        "on_error": ctx.on_llm_error,
        "on_tool_start": ctx.on_tool_start,
        "on_tool_complete": ctx.on_tool_complete,
    }


class DelegateTracingContext:
    """Nested (or standalone) tracing for delegate sub-agent loops."""

    def __init__(
        self,
        *,
        role: str,
        task: str,
        task_id: str = "",
        parent_session_key: str = "",
        child_session_key: str = "",
        parent_trace_id: str = "",
    ):
        self.role = role
        self.task_id = task_id
        self.child_session_key = child_session_key or task_id or "_delegate"
        self._root: Any = None
        self._delegate_span: Any = None
        self._standalone_trace: Any = None
        self._llm_span: Any = None
        self._llm_start_time: float = 0.0
        self._tool_spans: dict[str, tuple[Any, float]] = {}
        self._trace_id = parent_trace_id or ""
        self._observation_id = ""

        parent_ctx = get_current_trace(parent_session_key) if parent_session_key else None
        parent_trace = getattr(parent_ctx, "_trace", None) if parent_ctx else None

        if parent_trace is not None:
            try:
                self._delegate_span = parent_trace.span(
                    name=f"delegate:{role}",
                    input={
                        "role": role,
                        "task": task[:500],
                        "task_id": task_id,
                        "child_session_key": child_session_key,
                    },
                )
                self._root = self._delegate_span
                self._trace_id = str(getattr(parent_trace, "id", "") or self._trace_id)
                self._observation_id = str(getattr(self._delegate_span, "id", ""))
            except Exception as exc:
                logger.debug("LangFuse delegate nested span: %s", exc)
        else:
            client = _get_client()
            if client is not None:
                try:
                    self._standalone_trace = client.trace(
                        name="delegate-turn",
                        session_id=child_session_key or f"delegate:{role}",
                        metadata={
                            "role": role,
                            "task_id": task_id,
                            "parent_trace_id": parent_trace_id,
                            "parent_session_key": parent_session_key,
                        },
                        tags=[f"delegate:{role}"],
                    )
                    self._root = self._standalone_trace
                    self._trace_id = str(getattr(self._standalone_trace, "id", ""))
                except Exception as exc:
                    logger.debug("LangFuse delegate standalone trace: %s", exc)

    @property
    def active(self) -> bool:
        return self._root is not None

    @property
    def trace_id(self) -> str:
        return self._trace_id

    @property
    def observation_id(self) -> str:
        return self._observation_id

    def on_llm_start(self, messages: list[dict]) -> None:
        if self._root is None:
            return
        try:
            msg_count = len(messages)
            self._llm_start_time = time.monotonic()
            self._llm_span = self._root.generation(
                name="delegate-llm",
                input={
                    "message_count": msg_count,
                    "last_role": messages[-1].get("role", "") if messages else "",
                },
            )
        except Exception as exc:
            logger.debug("LangFuse delegate on_llm_start: %s", exc)

    def on_llm_complete(self, response: Any) -> None:
        if self._llm_span is None:
            return
        try:
            elapsed_ms = (time.monotonic() - self._llm_start_time) * 1000.0
            usage = getattr(response, "usage", None)
            usage_dict: dict[str, int] = {}
            if usage is not None:
                usage_dict = {
                    "input": getattr(usage, "prompt_tokens", 0) or 0,
                    "output": getattr(usage, "completion_tokens", 0) or 0,
                    "total": getattr(usage, "total_tokens", 0) or 0,
                }
            content = str(getattr(response, "content", "") or "")
            tool_calls = getattr(response, "tool_calls", None)
            self._llm_span.end(
                output=content[:500] if content else "(tool_calls)" if tool_calls else "(empty)",
                usage=usage_dict or None,
                metadata={"elapsed_ms": round(elapsed_ms, 1)},
            )
        except Exception as exc:
            logger.debug("LangFuse delegate on_llm_complete: %s", exc)
        finally:
            self._llm_span = None

    def on_llm_error(self, exc: Exception, attempt: int) -> None:
        if self._llm_span is None:
            return
        try:
            self._llm_span.end(
                output=f"ERROR (attempt {attempt}): {type(exc).__name__}: {exc}",
                level="ERROR",
            )
        except Exception as log_exc:
            logger.debug("LangFuse delegate on_llm_error: %s", log_exc)
        finally:
            self._llm_span = None

    def on_tool_start(self, name: str, args: dict) -> None:
        if self._root is None:
            return
        try:
            key = f"{name}:{len(self._tool_spans)}"
            span = self._root.span(
                name=f"tool:{name}",
                input={
                    "tool": name,
                    "args_keys": list(args.keys()) if args else [],
                    "path": str(args.get("path") or args.get("file") or "")[:200],
                },
            )
            self._tool_spans[key] = (span, time.monotonic())
        except Exception as exc:
            logger.debug("LangFuse delegate on_tool_start: %s", exc)

    def on_tool_complete(self, name: str, result: str) -> None:
        matches = [k for k in self._tool_spans if k.startswith(f"{name}:")]
        if not matches:
            return
        key = matches[-1]
        entry = self._tool_spans.pop(key, None)
        if entry is None:
            return
        span, start_time = entry
        try:
            elapsed_ms = (time.monotonic() - start_time) * 1000.0
            lowered = (result or "").lower()
            patch_hint = any(tok in lowered for tok in ("patch", "write_file", "replacements"))
            span.end(
                output=(result or "")[:400],
                metadata={
                    "elapsed_ms": round(elapsed_ms, 1),
                    "result_len": len(result or ""),
                    "patch_like": patch_hint,
                },
            )
        except Exception as exc:
            logger.debug("LangFuse delegate on_tool_complete: %s", exc)

    def finish(
        self,
        *,
        success: bool,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        meta = dict(metadata or {})
        meta["success"] = success
        if self._delegate_span is not None:
            try:
                self._delegate_span.end(
                    output="success" if success else "failed",
                    metadata=meta,
                    level=None if success else "WARNING",
                )
            except Exception as exc:
                logger.debug("LangFuse delegate span end: %s", exc)
        elif self._standalone_trace is not None:
            try:
                self._standalone_trace.update(metadata=meta)
            except Exception as exc:
                logger.debug("LangFuse delegate trace update: %s", exc)


_delegate_ctx_store: dict[str, DelegateTracingContext] = {}


def delegate_run_callbacks(
    *,
    parent_session_key: str = "",
    child_session_key: str = "",
    role: str,
    task: str,
    task_id: str = "",
    parent_trace_id: str = "",
) -> Any | None:
    """Build per-run LoopCallbacks for a delegate sub-agent loop."""
    if not langfuse_enabled():
        return None

    ctx = DelegateTracingContext(
        role=role,
        task=task,
        task_id=task_id,
        parent_session_key=parent_session_key,
        child_session_key=child_session_key,
        parent_trace_id=parent_trace_id,
    )
    if not ctx.active:
        return None

    store_key = child_session_key or task_id or f"delegate:{role}"
    _delegate_ctx_store[store_key] = ctx

    from butler.core.loop_types import LoopCallbacks

    return LoopCallbacks(
        on_llm_start=ctx.on_llm_start,
        on_llm_complete=ctx.on_llm_complete,
        on_error=ctx.on_llm_error,
        on_tool_start=ctx.on_tool_start,
        on_tool_complete=ctx.on_tool_complete,
    )


def finish_delegate_trace(
    child_session_key: str = "",
    *,
    success: bool,
    metadata: dict[str, Any] | None = None,
) -> DelegateTracingContext | None:
    """Close an active delegate tracing context."""
    ctx = _delegate_ctx_store.pop(child_session_key or "", None)
    if ctx is None:
        for key in list(_delegate_ctx_store):
            if key.startswith("delegate:"):
                ctx = _delegate_ctx_store.pop(key, None)
                break
    if ctx is not None:
        ctx.finish(success=success, metadata=metadata)
        flush_langfuse()
    return ctx


def get_delegate_trace(child_session_key: str = "") -> DelegateTracingContext | None:
    return _delegate_ctx_store.get(child_session_key or "")
