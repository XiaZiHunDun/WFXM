"""Build user-visible text from WeChat inbound media (image + voice)."""

from __future__ import annotations

from butler.gateway.platforms.types import MessageEvent, MessageType

_PLACEHOLDER = "（收到媒体消息；当前 Butler 网关会处理文字指令，请用文字说明需求。）"


def inbound_media_enabled() -> bool:
    from butler.gateway_settings import resolve_gateway_inbound_config

    return resolve_gateway_inbound_config().enabled


def _max_chars() -> int:
    from butler.gateway_settings import resolve_gateway_inbound_config

    return resolve_gateway_inbound_config().max_chars


def _truncate(text: str) -> str:
    limit = _max_chars()
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    return t[: limit - 3] + "..."


def _pair_media(event: MessageEvent) -> tuple[list[str], list[str], list[str]]:
    images: list[str] = []
    voices: list[str] = []
    documents: list[str] = []
    for url, mime in zip(event.media_urls or [], event.media_types or []):
        m = (mime or "").lower()
        if m.startswith("image/"):
            images.append(url)
        elif m.startswith("audio/") or "silk" in m:
            voices.append(url)
        elif _is_document_path(url, m):
            documents.append(url)
    return images, voices, documents


def _is_document_path(path: str, mime: str) -> bool:
    """Check if a file path/mime represents a convertible document."""
    try:
        from butler.tools.document_reader import can_convert
        if can_convert(path):
            return True
    except ImportError:
        pass
    doc_mimes = ("application/pdf", "application/msword", "application/vnd.openxml",
                 "application/vnd.ms-excel", "application/vnd.ms-powerpoint",
                 "text/html", "text/csv", "application/epub")
    return any(mime.startswith(dm) for dm in doc_mimes)


def build_inbound_user_text(event: MessageEvent) -> str:
    """Turn MessageEvent into orchestrator user message text."""
    base = (event.text or "").strip()
    if not inbound_media_enabled():
        if base:
            return base
        if event.media_urls:
            return _PLACEHOLDER
        return ""

    images, voices, documents = _pair_media(event)
    blocks: list[str] = []

    if documents:
        from butler.gateway.inbound_media_ops import wechat_document_block_safe

        for doc_path in documents[:3]:
            blocks.append(wechat_document_block_safe(doc_path, max_chars=_max_chars()))

    if images:
        if base:
            blocks.append(f"[微信图片]\n（用户附图说明：{base}）")
        else:
            blocks.append("[微信图片]")
        for img_path in images[:3]:
            from butler.gateway.inbound_media_ops import wechat_image_block_safe

            hint = base if len(images) == 1 else ""
            blocks.append(wechat_image_block_safe(img_path, hint=hint))
        base = ""

    if voices:
        from butler.gateway_settings import resolve_gateway_inbound_config

        prefer_ilink = resolve_gateway_inbound_config().speech.prefer_ilink_text
        ilink_text = base.strip() if base else ""

        if prefer_ilink and ilink_text:
            blocks.append(f"[微信语音转写]\n{ilink_text}")
            base = ""
        else:
            from butler.gateway.inbound_media_ops import wechat_voice_block_safe

            for vpath in voices[:2]:
                blocks.append(wechat_voice_block_safe(vpath, ilink_text=ilink_text))
                base = ""
            base = ""

    if base:
        if event.message_type == MessageType.VOICE and not voices:
            blocks.append(f"[微信语音转写]\n{base}")
        else:
            blocks.append(base)

    if not blocks:
        return _PLACEHOLDER if event.media_urls else ""

    return _truncate("\n\n".join(blocks))
