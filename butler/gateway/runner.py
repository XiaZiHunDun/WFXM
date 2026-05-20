"""Butler-native gateway runner (no Hermes subprocess)."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import signal
from typing import Any

from butler.gateway.message_handler import ButlerMessageHandler
from butler.gateway.platforms.types import MessageEvent, PlatformConfig

logger = logging.getLogger(__name__)

NATIVE_PLATFORMS = frozenset({"wechat", "weixin", "微信"})

# Single worker: avoid ProjectManager / session registry races from concurrent to_thread calls.
_HANDLER_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="butler-gw-handler",
)
_HANDLER_TIMEOUT_SECONDS = float(os.getenv("BUTLER_GATEWAY_HANDLER_TIMEOUT", "180"))


def normalize_platforms(raw: str) -> list[str]:
    if not (raw or "").strip():
        return ["wechat"]
    out: list[str] = []
    for part in raw.replace(",", " ").split():
        name = part.strip().lower()
        if name in ("微信", "weixin"):
            name = "wechat"
        if name and name not in out:
            out.append(name)
    return out or ["wechat"]


def unsupported_platforms(platforms: list[str]) -> list[str]:
    return [p for p in platforms if p not in NATIVE_PLATFORMS]


def _warmup_gateway_runtime(butler: ButlerMessageHandler) -> None:
    """Avoid first user message blocking on jieba/skill index cold start."""
    try:
        from butler.skills.similarity import _ensure_jieba

        _ensure_jieba()
        mgr = getattr(butler._orchestrator, "_skill_manager", None)
        if mgr is not None:
            mgr.list_skills()
        logger.info("Gateway runtime warmup complete (skills/jieba)")
    except Exception as exc:
        logger.debug("Gateway warmup skipped: %s", exc)


async def _butler_message_handler(
    butler: ButlerMessageHandler,
    event: MessageEvent,
) -> str | None:
    text = (event.text or "").strip()
    if not text and event.media_urls:
        text = "（收到媒体消息；当前 Butler 网关会处理文字指令，请用文字说明需求。）"
    if not text:
        return None
    source = event.source
    if source is None:
        return None
    bridge = getattr(event, "gateway_bridge", None)

    def _run_in_worker() -> str:
        from butler.gateway.outbound_bridge import set_current_bridge

        if bridge is not None:
            set_current_bridge(bridge)
        try:
            return butler.handle_message(
                text,
                platform="wechat",
                external_id=source.chat_id,
            )
        finally:
            if bridge is not None:
                set_current_bridge(None)

    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(_HANDLER_EXECUTOR, _run_in_worker),
            timeout=_HANDLER_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error(
            "Gateway handler timed out after %.0fs (chat_id=%s preview=%r)",
            _HANDLER_TIMEOUT_SECONDS,
            source.chat_id,
            text[:80],
        )
        return (
            f"处理超时（>{int(_HANDLER_TIMEOUT_SECONDS)}秒）。"
            "请稍后重试，或发 /health 查看状态；必要时重启 butler-gateway。"
        )


async def run_gateway_async(platforms: list[str]) -> int:
    """Start native adapters; blocks until cancelled."""
    unsupported = unsupported_platforms(platforms)
    if unsupported:
        logger.error(
            "Platforms not supported by Butler native gateway: %s. "
            "Use `butler gateway --hermes-fallback` for Hermes subprocess.",
            ", ".join(unsupported),
        )
        return 2

    butler = ButlerMessageHandler(channel="gateway")
    _warmup_gateway_runtime(butler)
    adapters: list[Any] = []

    for name in platforms:
        if name in ("wechat", "weixin"):
            from butler.gateway.platforms.wechat import WeChatAdapter, check_wechat_requirements

            if not check_wechat_requirements():
                logger.error("WeChat requires: pip install aiohttp cryptography certifi")
                return 1
            config = PlatformConfig(
                token=os.getenv("WECHAT_TOKEN", "") or os.getenv("WEIXIN_TOKEN", ""),
                extra={
                    "account_id": os.getenv("WECHAT_ACCOUNT_ID", "") or os.getenv("WEIXIN_ACCOUNT_ID", ""),
                },
            )
            adapter = WeChatAdapter(config)

            async def _handler(event: MessageEvent, _b: ButlerMessageHandler = butler) -> str | None:
                return await _butler_message_handler(_b, event)

            adapter.set_message_handler(_handler)
            adapters.append(adapter)

    if not adapters:
        logger.error("No adapters to start")
        return 1

    connected = []
    for adapter in adapters:
        if await adapter.connect():
            connected.append(adapter)
        else:
            logger.error("[%s] connect failed: %s", adapter.name, getattr(adapter, "_fatal_error_message", ""))

    if not connected:
        return 1

    logger.info("Butler native gateway running (%s)", ", ".join(a.name for a in connected))

    stop = asyncio.Event()

    def _request_stop(*_args: Any) -> None:
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop.set())

    await stop.wait()

    for adapter in connected:
        await adapter.disconnect()
    return 0


def run_gateway_blocking(platforms: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        return asyncio.run(run_gateway_async(platforms))
    except KeyboardInterrupt:
        return 0
