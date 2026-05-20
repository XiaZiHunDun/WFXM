"""Butler-native gateway runner (no Hermes subprocess)."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from typing import Any

from butler.gateway.message_handler import ButlerMessageHandler
from butler.gateway.platforms.types import MessageEvent, PlatformConfig

logger = logging.getLogger(__name__)

NATIVE_PLATFORMS = frozenset({"wechat", "weixin", "微信"})


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
    session_key = f"wechat:{source.chat_id}"
    return await asyncio.to_thread(
        butler.handle_message,
        text,
        session_key=session_key,
        platform="wechat",
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
