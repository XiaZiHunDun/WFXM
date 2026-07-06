"""WeChat (iLink) ``WeChatAdapter`` class (ENG-13 PR-3)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple, cast

from butler.config import get_butler_home
from butler.gateway.platforms.base import ButlerPlatformAdapter
from butler.gateway.platforms.types import MessageEvent, PlatformConfig, SendResult
from butler.gateway.platforms.wechat_ilink._compat import (
    ContextTokenStore,
    TypingTicketCache,
    _normalize_markdown_blocks,
    _wrap_copy_friendly_lines_for_wechat,
    aiohttp,
)

logger = logging.getLogger(__name__)


class WeChatAdapter(ButlerPlatformAdapter):  # type: ignore[misc]
    """Butler-native WeChat (iLink Bot API) adapter."""

    MAX_MESSAGE_LENGTH = 2000
    SUPPORTS_MESSAGE_EDITING = False

    def __init__(self, config: PlatformConfig):
        super().__init__(config, "wechat")
        self._data_home = str(get_butler_home())
        self._token_store = ContextTokenStore(self._data_home)
        self._typing_cache = TypingTicketCache()
        self._poll_session: Optional[aiohttp.ClientSession] = None
        self._send_session: Optional[aiohttp.ClientSession] = None
        self._poll_task: Optional[asyncio.Task[None]] = None
        self._bg_typing_tasks: set[asyncio.Task[None]] = set()
        from butler.gateway.platforms.wechat_ilink_phases import (
            _phase_init_account,
            _phase_init_chunks,
            _phase_init_dedup,
            _phase_init_policies,
        )

        _phase_init_account(self, config)
        _phase_init_chunks(self, config)
        _phase_init_policies(self, config)
        _phase_init_dedup(self)

    @staticmethod
    def _coerce_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()] if str(value).strip() else []

    def _schedule_typing_ticket_bg(self, user_id: str, context_token: Optional[str]) -> None:
        from butler.gateway.platforms.wechat_ilink.adapter_lifecycle import schedule_typing_ticket_bg

        schedule_typing_ticket_bg(self, user_id, context_token)

    async def connect(self) -> bool:
        from butler.gateway.platforms.wechat_ilink.adapter_lifecycle import connect

        return cast(bool, await connect(self))

    async def disconnect(self) -> None:
        from butler.gateway.platforms.wechat_ilink.adapter_lifecycle import disconnect

        await disconnect(self)

    async def _poll_loop(self) -> None:
        from butler.gateway.platforms.wechat_ilink.adapter_lifecycle import poll_loop

        await poll_loop(self)

    async def _dispatch_poll_response(
        self,
        response: Dict[str, Any],
        consecutive_failures: int,
        handle_response: Any,
    ) -> int:
        from butler.gateway.platforms.wechat_ilink.adapter_inbound import dispatch_poll_response

        return cast(
            int,
            await dispatch_poll_response(
                self, response, consecutive_failures, handle_response,
            ),
        )

    @staticmethod
    def _poll_backoff_seconds(consecutive_failures: int) -> float:
        from butler.gateway.platforms.wechat_ilink.adapter_inbound import poll_backoff_seconds

        return cast(float, poll_backoff_seconds(consecutive_failures))

    async def _handle_poll_exception(
        self, exc: Exception, consecutive_failures: int,
    ) -> int:
        from butler.gateway.platforms.wechat_ilink.adapter_inbound import handle_poll_exception

        return cast(
            int,
            await handle_poll_exception(self, exc, consecutive_failures),
        )

    async def _process_message_safe(self, message: Dict[str, Any]) -> None:
        from butler.gateway.platforms.wechat_ilink.adapter_inbound import process_message_safe

        await process_message_safe(self, message)

    async def _process_message(self, message: Dict[str, Any]) -> None:
        from butler.gateway.platforms.wechat_ilink.adapter_inbound import process_message

        await process_message(self, message)

    def _is_dm_allowed(self, sender_id: str) -> bool:
        if self._dm_policy == "disabled":
            return False
        if self._dm_policy == "allowlist":
            return sender_id in self._allow_from
        return True

    async def _collect_media(
        self, item: Dict[str, Any], media_paths: List[str], media_types: List[str],
    ) -> None:
        from butler.gateway.platforms.wechat_ilink import adapter_media

        await adapter_media.collect_media(self, item, media_paths, media_types)

    async def _download_image(self, item: Dict[str, Any]) -> Optional[str]:
        from butler.gateway.platforms.wechat_ilink import adapter_media

        return cast(Optional[str], await adapter_media.download_image(self, item))

    async def _download_video(self, item: Dict[str, Any]) -> Optional[str]:
        from butler.gateway.platforms.wechat_ilink import adapter_media

        return cast(Optional[str], await adapter_media.download_video(self, item))

    async def _download_file(self, item: Dict[str, Any]) -> Tuple[Optional[str], str]:
        from butler.gateway.platforms.wechat_ilink import adapter_media

        return cast(
            Tuple[Optional[str], str],
            await adapter_media.download_file(self, item),
        )

    async def _download_voice(self, item: Dict[str, Any]) -> Optional[str]:
        from butler.gateway.platforms.wechat_ilink import adapter_media

        return cast(Optional[str], await adapter_media.download_voice(self, item))

    async def _maybe_fetch_typing_ticket(self, user_id: str, context_token: Optional[str]) -> None:
        from butler.gateway.platforms.wechat_ilink import adapter_outbound

        await adapter_outbound.maybe_fetch_typing_ticket(self, user_id, context_token)

    async def _ensure_typing_ticket_for_event(self, event: MessageEvent) -> None:
        from butler.gateway.platforms.wechat_ilink import adapter_outbound

        await adapter_outbound.ensure_typing_ticket_for_event(self, event)

    def _split_text(
        self,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> List[str]:
        from butler.gateway.platforms.wechat_ilink import adapter_outbound

        return cast(
            List[str],
            adapter_outbound.split_text(self, content, metadata=metadata),
        )

    async def _send_text_chunk(
        self,
        *,
        chat_id: str,
        chunk: str,
        context_token: Optional[str],
        client_id: str,
    ) -> None:
        from butler.gateway.platforms.wechat_ilink import adapter_outbound

        await adapter_outbound.send_text_chunk(
            self, chat_id=chat_id, chunk=chunk,
            context_token=context_token, client_id=client_id,
        )

    async def _backoff_for_rate_limit(self, chat_id: str, attempt: int) -> None:
        from butler.gateway.platforms.wechat_ilink import adapter_outbound

        await adapter_outbound.backoff_for_rate_limit(self, chat_id, attempt)

    async def _backoff_for_transport_error(
        self, chat_id: str, attempt: int, exc: Exception,
    ) -> None:
        from butler.gateway.platforms.wechat_ilink import adapter_outbound

        await adapter_outbound.backoff_for_transport_error(self, chat_id, attempt, exc)

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        from butler.gateway.platforms.wechat_ilink import adapter_outbound

        return await adapter_outbound.send_message(
            self, chat_id, content, reply_to=reply_to, metadata=metadata,
        )

    async def send_typing(self, chat_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        from butler.gateway.platforms.wechat_ilink import adapter_outbound

        await adapter_outbound.send_typing(self, chat_id, metadata=metadata)

    async def stop_typing(self, chat_id: str) -> None:
        from butler.gateway.platforms.wechat_ilink import adapter_outbound

        await adapter_outbound.stop_typing(self, chat_id)

    async def send_image(
        self,
        chat_id: str,
        image_url: str,
        caption: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        from butler.gateway.platforms.wechat_ilink import adapter_outbound

        return await adapter_outbound.send_image(
            self, chat_id, image_url, caption,
            reply_to=reply_to, metadata=metadata,
        )

    async def send_image_file(
        self,
        chat_id: str,
        image_path: str,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> SendResult:
        from butler.gateway.platforms.wechat_ilink import adapter_outbound

        return await adapter_outbound.send_image_file(
            self, chat_id, image_path, caption=caption,
            reply_to=reply_to, metadata=metadata, **kwargs,
        )

    async def send_document(
        self,
        chat_id: str,
        file_path: str,
        caption: Optional[str] = None,
        file_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> SendResult:
        from butler.gateway.platforms.wechat_ilink import adapter_outbound

        return await adapter_outbound.send_document(
            self, chat_id, file_path, caption=caption, file_name=file_name,
            reply_to=reply_to, metadata=metadata, **kwargs,
        )

    async def send_video(
        self,
        chat_id: str,
        video_path: str,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        from butler.gateway.platforms.wechat_ilink import adapter_outbound

        return await adapter_outbound.send_video(
            self, chat_id, video_path, caption=caption,
            reply_to=reply_to, metadata=metadata,
        )

    async def send_voice(
        self,
        chat_id: str,
        audio_path: str,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        from butler.gateway.platforms.wechat_ilink import adapter_outbound

        return await adapter_outbound.send_voice(
            self, chat_id, audio_path, caption=caption,
            reply_to=reply_to, metadata=metadata,
        )

    async def _download_remote_media(self, url: str) -> str:
        from butler.gateway.platforms.wechat_ilink import adapter_media

        return cast(str, await adapter_media.download_remote_media(self, url))

    async def _send_file(
        self,
        chat_id: str,
        path: str,
        caption: str,
        force_file_attachment: bool = False,
    ) -> str:
        from butler.gateway.platforms.wechat_ilink import adapter_outbound

        return cast(
            str,
            await adapter_outbound.send_file(
                self, chat_id, path, caption,
                force_file_attachment=force_file_attachment,
            ),
        )

    def _build_outbound_media_item(
        self,
        path: str,
        media_type: int,
        item_builder: Any,
        *,
        encrypted_query_param: str,
        aes_key: bytes,
        ciphertext_size: int,
        plaintext_size: int,
        rawfilemd5: str,
    ) -> Dict[str, Any]:
        from butler.gateway.platforms.wechat_ilink import adapter_outbound

        return cast(
            Dict[str, Any],
            adapter_outbound.build_outbound_media_item(
                self, path, media_type, item_builder,
                encrypted_query_param=encrypted_query_param,
                aes_key=aes_key,
                ciphertext_size=ciphertext_size,
                plaintext_size=plaintext_size,
                rawfilemd5=rawfilemd5,
            ),
        )

    def _outbound_media_builder(
        self, path: str, force_file_attachment: bool = False,
    ) -> Any:
        from butler.gateway.platforms.wechat_ilink import adapter_outbound

        return adapter_outbound.outbound_media_builder(
            self, path, force_file_attachment=force_file_attachment,
        )

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        chat_type = "group" if chat_id.endswith("@chatroom") else "dm"
        return {"name": chat_id, "type": chat_type, "chat_id": chat_id}

    def extract_local_files(self, content: str) -> tuple[list[str], str]:
        from butler.gateway.outbound_files import extract_deliverable_local_files

        paths, cleaned = extract_deliverable_local_files(content)
        return paths, cleaned

    def format_message(self, content: Optional[str]) -> str:
        if content is None:
            return ""
        from butler.gateway.pii_scrub import scrub_outbound_text

        scrubbed = scrub_outbound_text(str(content))
        return cast(
            str,
            _wrap_copy_friendly_lines_for_wechat(_normalize_markdown_blocks(scrubbed)),
        )


__all__ = ["WeChatAdapter"]
