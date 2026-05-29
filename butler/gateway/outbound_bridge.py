"""Thread-safe WeChat (and native gateway) outbound UX: typing, ack, milestones."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

logger = logging.getLogger(__name__)

_thread_bridge = threading.local()

MILESTONE_TOOLS = frozenset(
    {"delegate_task", "run_workflow", "write_file", "patch", "terminal"}
)


class _TypingAdapter(Protocol):
    async def send_typing(self, chat_id: str, metadata: Optional[dict[str, Any]] = None) -> None: ...
    async def stop_typing(self, chat_id: str) -> None: ...
    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Any: ...


def _env_bool(name: str, default: bool) -> bool:
    from butler.env_parse import env_truthy

    return env_truthy(name, default=default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def set_current_bridge(bridge: GatewayOutboundBridge | None) -> None:
    _thread_bridge.bridge = bridge


def get_current_bridge() -> GatewayOutboundBridge | None:
    return getattr(_thread_bridge, "bridge", None)


def get_gateway_bridge_optional() -> GatewayOutboundBridge | None:
    return get_current_bridge()


@dataclass
class GatewayOutboundBridge:
    """Coordinates typing refresh and at-most-one ack per inbound turn."""

    adapter: _TypingAdapter
    chat_id: str
    loop: asyncio.AbstractEventLoop
    typing_enabled: bool = field(default_factory=lambda: _env_bool("BUTLER_GATEWAY_TYPING_ENABLED", True))
    typing_refresh_seconds: float = field(
        default_factory=lambda: _env_float("BUTLER_GATEWAY_TYPING_REFRESH_SECONDS", 4.0)
    )
    ack_enabled: bool = field(default_factory=lambda: _env_bool("BUTLER_GATEWAY_PROGRESS_ACK_ENABLED", True))
    ack_seconds: float = field(
        default_factory=lambda: _env_float("BUTLER_GATEWAY_PROGRESS_ACK_SECONDS", 30.0)
    )
    max_ack_messages: int = field(default_factory=lambda: int(
        os.getenv("BUTLER_GATEWAY_PROGRESS_MAX_ACK_MESSAGES", "1") or "1"
    ))

    _started_at: float = field(default=0.0, init=False)
    _final_sent: bool = field(default=False, init=False)
    _ack_sent: bool = field(default=False, init=False)
    _completion_push_sent: bool = field(default=False, init=False)
    _delegate_push_count: int = field(default=0, init=False)
    _pending_delegate_report: Any = field(default=None, init=False)
    _timeout_notified: bool = field(default=False, init=False)
    _typing_task: asyncio.Task[None] | None = field(default=None, init=False)
    _ack_task: asyncio.Task[None] | None = field(default=None, init=False)
    _closed: bool = field(default=False, init=False)
    _task_milestone_sent: bool = field(default=False, init=False)
    _milestone_task: asyncio.Task[None] | None = field(default=None, init=False)

    delegate_role: str = field(default="", init=False)
    workflow_name: str = field(default="", init=False)
    workflow_step: str = field(default="", init=False)
    workflow_step_index: int = field(default=0, init=False)
    workflow_step_total: int = field(default=0, init=False)
    last_tool_name: str = field(default="", init=False)
    _last_turn_elapsed: float = field(default=0.0, init=False)
    _outbound_events: list[Any] = field(default_factory=list, init=False)
    _stream_preview: str = field(default="", init=False)
    _stream_chars: int = field(default=0, init=False)
    workflow_step_phase: str = field(default="", init=False)

    @property
    def turn_started_at(self) -> float:
        return self._started_at

    @property
    def ack_sent(self) -> bool:
        return self._ack_sent

    @property
    def completion_push_sent(self) -> bool:
        return self._completion_push_sent

    @property
    def delegate_push_count(self) -> int:
        return self._delegate_push_count

    @property
    def timeout_notified(self) -> bool:
        return self._timeout_notified

    def set_pending_delegate_report(self, report: Any) -> None:
        self._pending_delegate_report = report

    def take_pending_delegate_report(self) -> Any:
        report = self._pending_delegate_report
        self._pending_delegate_report = None
        return report

    @classmethod
    def for_event(
        cls,
        adapter: Any,
        *,
        chat_id: str,
        loop: asyncio.AbstractEventLoop,
        ensure_typing: Callable[[], Any] | None = None,
    ) -> GatewayOutboundBridge:
        bridge = cls(adapter=adapter, chat_id=chat_id, loop=loop)
        bridge._ensure_typing = ensure_typing  # type: ignore[attr-defined]
        return bridge

    async def start_turn(self) -> None:
        self._started_at = time.monotonic()
        self._final_sent = False
        self._ack_sent = False
        self._completion_push_sent = False
        self._delegate_push_count = 0
        self._pending_delegate_report = None
        self._timeout_notified = False
        self._closed = False
        self._task_milestone_sent = False
        self.delegate_role = ""
        self.workflow_name = ""

        ensure = getattr(self, "_ensure_typing", None)
        if callable(ensure):
            try:
                await ensure()
            except Exception as exc:
                logger.debug("typing ticket ensure failed: %s", exc)

        if self.typing_enabled:
            await self._safe_send_typing()
            self._typing_task = asyncio.create_task(
                self._typing_refresh_loop(),
                name=f"butler-typing-{self.chat_id[:8]}",
            )

        if self.ack_enabled and self.ack_seconds > 0 and self.max_ack_messages > 0:
            self._ack_task = asyncio.create_task(
                self._ack_timer(),
                name=f"butler-ack-{self.chat_id[:8]}",
            )

        try:
            from butler.gateway.task_milestone import task_milestone_enabled

            if task_milestone_enabled():
                self._milestone_task = asyncio.create_task(
                    self._milestone_timer(),
                    name=f"butler-milestone-{self.chat_id[:8]}",
                )
        except Exception as exc:
            logger.debug("start turn skipped: %s", exc)
    async def end_turn(self) -> None:
        if self._closed:
            return
        self._closed = True
        for task in (self._typing_task, self._ack_task, self._milestone_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._typing_task = None
        self._ack_task = None
        self._milestone_task = None
        if self.typing_enabled:
            await self._safe_stop_typing()

    def mark_final_sent(self) -> None:
        self._final_sent = True

    def emit_threadsafe(self, fn: Callable[[], None]) -> None:
        if self._closed:
            return
        try:
            self.loop.call_soon_threadsafe(fn)
        except RuntimeError:
            logger.debug("outbound bridge loop closed; drop event")

    def record_outbound_event(self, event: Any) -> None:
        try:
            payload = event.to_dict() if hasattr(event, "to_dict") else dict(event)
        except Exception:
            return
        self._outbound_events.append(payload)
        if len(self._outbound_events) > 24:
            self._outbound_events.pop(0)
        if payload.get("kind") == "thread_item":
            try:
                from butler.gateway.item_event_sink import record_thread_item

                record_thread_item(payload)
            except Exception as exc:
                logger.debug("record outbound event skipped: %s", exc)
    def recent_outbound_events(self) -> list[dict[str, Any]]:
        return list(self._outbound_events)

    def append_stream_preview(self, delta: str) -> None:
        if self._closed or not delta:
            return
        from butler.env_parse import env_truthy

        if not env_truthy("BUTLER_GATEWAY_STREAM_PREVIEW", default=False):
            return

        def _apply() -> None:
            self._stream_chars += len(delta)
            combined = (self._stream_preview + delta)[-400:]
            self._stream_preview = combined
            from butler.gateway.outbound_events import stream_event
            from butler.gateway.progressive_stream import maybe_schedule_progressive_reply

            self.record_outbound_event(stream_event(phase="delta", chars=len(delta)))
            maybe_schedule_progressive_reply(self, combined)

        self.emit_threadsafe(_apply)

    def notify_delegate_start(self, role: str, *, preview: str = "") -> None:
        role = str(role or "").strip()
        if not role:
            return
        self.flush_pending_delegate_completion()
        self.delegate_role = role
        from butler.gateway.outbound_events import delegate_event

        self.record_outbound_event(delegate_event(role, phase="start", preview=preview[:80]))
        logger.info("Gateway milestone delegate_start role=%s preview=%r", role, preview[:40])

    def notify_workflow_step(
        self,
        workflow_name: str,
        step_id: str,
        *,
        step_index: int = 0,
        step_total: int = 0,
        phase: str = "start",
        error: str = "",
    ) -> None:
        def _apply() -> None:
            self.workflow_name = str(workflow_name or "").strip()
            self.workflow_step = str(step_id or "").strip()
            self.workflow_step_index = int(step_index)
            self.workflow_step_total = int(step_total)
            self.workflow_step_phase = str(phase or "start").strip()
            from butler.gateway.outbound_events import workflow_event

            self.record_outbound_event(
                workflow_event(
                    self.workflow_name,
                    self.workflow_step,
                    phase=self.workflow_step_phase,
                    step_index=self.workflow_step_index,
                    step_total=self.workflow_step_total,
                    error=error,
                )
            )
            logger.info(
                "Gateway milestone workflow_step wf=%s step=%s phase=%s (%s/%s)",
                self.workflow_name,
                self.workflow_step,
                self.workflow_step_phase,
                self.workflow_step_index,
                self.workflow_step_total,
            )

        self.emit_threadsafe(_apply)

    def on_tool_start(self, name: str, args: dict) -> None:
        name = str(name or "").strip()
        if name not in MILESTONE_TOOLS:
            return

        def _apply() -> None:
            self.last_tool_name = name
            if name == "delegate_task":
                role = str((args or {}).get("role") or "").strip()
                if role:
                    self.delegate_role = role
            elif name == "run_workflow":
                wf = str((args or {}).get("workflow_name") or (args or {}).get("name") or "").strip()
                if wf:
                    self.workflow_name = wf

        self.emit_threadsafe(_apply)

    def on_tool_complete(self, name: str, result: str) -> None:
        del name, result

    def flush_pending_delegate_completion(self) -> None:
        from butler.gateway.completion_notify import flush_pending_delegate_completion

        flush_pending_delegate_completion(self)

    def notify_delegate_finished(self, report: Any) -> None:
        """Push or defer delegate AgentReport (see delegate_completion_mode)."""
        from butler.gateway.completion_notify import try_push_agent_report

        elapsed = time.monotonic() - self._started_at if self._started_at else 0.0
        try_push_agent_report(
            report,
            kind="delegate",
            bridge=self,
            elapsed_turn_seconds=elapsed,
        )

    def notify_turn_timeout(self, *, timeout_seconds: float) -> None:
        from butler.gateway.completion_notify import try_push_turn_timeout

        elapsed = time.monotonic() - self._started_at if self._started_at else 0.0
        try_push_turn_timeout(
            self,
            timeout_seconds=timeout_seconds,
            elapsed_seconds=elapsed,
        )

    def notify_workflow_finished(self, report: Any) -> None:
        from butler.gateway.completion_notify import try_push_agent_report

        elapsed = time.monotonic() - self._started_at if self._started_at else 0.0
        try_push_agent_report(
            report,
            kind="workflow",
            bridge=self,
            elapsed_turn_seconds=elapsed,
        )

    def record_turn_elapsed(self, elapsed_seconds: float) -> None:
        self._last_turn_elapsed = max(0.0, float(elapsed_seconds))

    def maybe_notify_turn_complete_after_reply(self) -> None:
        """Call after the main WeChat reply was sent (see platforms/base.py)."""
        from butler.gateway.completion_notify import try_push_turn_complete

        self.flush_pending_delegate_completion()
        elapsed = self._last_turn_elapsed
        if elapsed <= 0 and self._started_at:
            elapsed = time.monotonic() - self._started_at
        try_push_turn_complete(self, elapsed_seconds=elapsed)

    def schedule_supplementary_reply(self, text: str, *, kind: str = "queued") -> bool:
        """Send an extra user-visible message (e.g. drained inbound queue)."""
        if self._closed or not (text or "").strip():
            return False
        body = (text or "").strip()
        from butler.gateway.pii_scrub import scrub_outbound_text

        body = scrub_outbound_text(body)
        if len(body) > 4000:
            body = body[:3997] + "..."

        async def _send() -> None:
            try:
                await self.adapter.send(self.chat_id, body)
                logger.info(
                    "Gateway supplementary reply sent kind=%s chat_id=%s len=%d",
                    kind,
                    self.chat_id[:12],
                    len(body),
                )
            except Exception as exc:
                logger.warning("Gateway supplementary reply failed: %s", exc)

        try:
            asyncio.run_coroutine_threadsafe(_send(), self.loop)
            return True
        except Exception as exc:
            logger.warning("Gateway supplementary schedule failed: %s", exc)
            return False

    def schedule_completion_push(self, text: str, *, kind: str) -> bool:
        """Thread-safe: send an extra completion message."""
        if self._closed or not (text or "").strip():
            return False
        if kind in ("turn", "workflow") and self._completion_push_sent:
            return False
        if kind == "timeout" and (self._timeout_notified or self._completion_push_sent):
            return False
        body = (text or "").strip()
        from butler.gateway.pii_scrub import scrub_outbound_text

        body = scrub_outbound_text(body)
        if len(body) > 4000:
            body = body[:3997] + "..."

        async def _send() -> None:
            from butler.gateway.completion_notify import deliver_completion_push

            ok = await deliver_completion_push(
                self.adapter,
                self.chat_id,
                body,
                kind=kind,
            )
            if ok:
                if kind == "delegate":
                    self._delegate_push_count += 1
                else:
                    self._completion_push_sent = True
                if kind == "timeout":
                    self._timeout_notified = True
                logger.info(
                    "Gateway completion push sent kind=%s chat_id=%s len=%d",
                    kind,
                    self.chat_id[:12],
                    len(body),
                )

        try:
            asyncio.run_coroutine_threadsafe(_send(), self.loop)
            return True
        except Exception as exc:
            logger.warning("Gateway completion push schedule failed: %s", exc)
            return False

    async def maybe_send_ack(self) -> None:
        if self._closed or self._final_sent or self._ack_sent:
            return
        if self.max_ack_messages <= 0:
            return
        elapsed = int(time.monotonic() - self._started_at)
        text = self._build_ack_text(elapsed)
        if not text:
            return
        from butler.gateway.pii_scrub import scrub_outbound_text

        text = scrub_outbound_text(text)
        try:
            await self.adapter.send(self.chat_id, text)
            self._ack_sent = True
            logger.info("Gateway progress ack sent chat_id=%s elapsed=%ds", self.chat_id, elapsed)
            try:
                from butler.gateway.task_milestone import maybe_schedule_task_milestone

                maybe_schedule_task_milestone(self)
            except Exception as exc:
                logger.debug("maybe send ack skipped: %s", exc)
        except Exception as exc:
            logger.warning("Gateway progress ack failed: %s", exc)

    async def _milestone_timer(self) -> None:
        try:
            from butler.gateway.task_milestone import (
                maybe_schedule_task_milestone,
                task_milestone_min_seconds,
            )

            await asyncio.sleep(task_milestone_min_seconds())
            if not self._closed and not self._final_sent:
                maybe_schedule_task_milestone(self)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("milestone timer ended: %s", exc)

    def _build_ack_text(self, elapsed: int) -> str:
        eta = self._estimate_eta(elapsed)
        if self.delegate_role:
            return (
                f"正在处理：已委派 {self.delegate_role}，完成后回复摘要。"
                f"（已用 {elapsed}s{eta}）可发 /health 查看状态"
            )
        if self.workflow_name:
            step_part = ""
            if self.workflow_step:
                if self.workflow_step_total > 0:
                    step_part = f"（{self.workflow_step}，{self.workflow_step_index}/{self.workflow_step_total}）"
                else:
                    step_part = f"（{self.workflow_step}）"
            return (
                f"正在处理：工作流 {self.workflow_name} 执行中{step_part}。"
                f"（已用 {elapsed}s{eta}）可发 /health 查看状态"
            )
        base = (
            f"正在处理，请稍候（已用 {elapsed}s{eta}）。"
            "完成后回复摘要；可发 /health 查看状态。"
        )
        preview = (self._stream_preview or "").strip()
        if preview:
            snippet = preview[-120:].replace("\n", " ")
            return f"{base}\n…{snippet}"
        return base

    @staticmethod
    def _estimate_eta(elapsed: int) -> str:
        if elapsed < 10:
            return "，预计 15-30s"
        if elapsed < 30:
            return "，预计还需 10-30s"
        if elapsed < 60:
            return "，预计还需 30-60s"
        return ""

    async def _typing_refresh_loop(self) -> None:
        try:
            while not self._closed:
                await asyncio.sleep(self.typing_refresh_seconds)
                if self._closed or self._final_sent:
                    break
                await self._safe_send_typing()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("typing refresh loop ended: %s", exc)

    async def _ack_timer(self) -> None:
        try:
            await asyncio.sleep(self.ack_seconds)
            if not self._closed and not self._final_sent:
                await self.maybe_send_ack()
        except asyncio.CancelledError:
            raise

    async def _safe_send_typing(self) -> None:
        try:
            await self.adapter.send_typing(self.chat_id)
        except Exception as exc:
            logger.debug("send_typing failed: %s", exc)

    async def _safe_stop_typing(self) -> None:
        try:
            await self.adapter.stop_typing(self.chat_id)
        except Exception as exc:
            logger.debug("stop_typing failed: %s", exc)


def merge_loop_callbacks(base: Any, extra: Any | None) -> Any:
    """Merge optional per-run callbacks onto a base LoopCallbacks."""
    from butler.core.loop_types import LoopCallbacks

    if extra is None:
        return base
    if base is None:
        return extra

    def _pick(name: str) -> Any:
        v = getattr(extra, name, None)
        if v is not None:
            return v
        return getattr(base, name, None)

    return LoopCallbacks(
        on_llm_start=_pick("on_llm_start"),
        on_llm_complete=_pick("on_llm_complete"),
        on_stream_delta=_pick("on_stream_delta"),
        on_stream_boundary=_pick("on_stream_boundary"),
        on_tool_start=_pick("on_tool_start"),
        on_tool_complete=_pick("on_tool_complete"),
        on_error=_pick("on_error"),
        on_iteration=_pick("on_iteration"),
        on_fallback=_pick("on_fallback"),
        pre_llm_transform=_pick("pre_llm_transform"),
        should_continue=_pick("should_continue"),
    )


__all__ = [
    "GatewayOutboundBridge",
    "get_current_bridge",
    "get_gateway_bridge_optional",
    "merge_loop_callbacks",
    "set_current_bridge",
]
