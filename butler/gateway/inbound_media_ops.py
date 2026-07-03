"""WeChat inbound media conversion best-effort helpers (P0-A)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def wechat_document_block_safe(doc_path: str, *, max_chars: int) -> str:
    try:
        from butler.tools.document_reader import convert_document

        result = convert_document(doc_path, max_chars=max_chars)
        if result.get("ok"):
            fmt = result.get("format", "文档")
            chars = result.get("chars", 0)
            text = result.get("text", "")
            logger.info(
                "WeChat document converted path=%s format=%s chars=%d",
                doc_path,
                fmt,
                chars,
            )
            return f"[微信文件 — {fmt.upper()}，{chars} 字]\n{text}"
        return f"[微信文件]\n（文档解析失败：{result.get('error', '未知错误')}）"
    except ImportError:
        return "[微信文件]\n（文档解析不可用，请安装: pip install 'butler-system[documents]'）"
    except Exception as exc:
        logger.warning("WeChat document conversion failed for %s: %s", doc_path, exc)
        return f"[微信文件]\n（文档解析失败：{exc}）"


def wechat_image_block_safe(img_path: str, *, hint: str) -> str:
    try:
        from butler.gateway.minimax_vlm import describe_image

        summary = describe_image(img_path, caption=hint)
        logger.info("WeChat vision ok path=%s chars=%d", img_path, len(summary))
        return f"--- 图片识别 ---\n{summary}"
    except Exception as exc:
        logger.warning("WeChat vision failed for %s: %s", img_path, exc)
        return f"--- 图片识别 ---\n（识别失败：{exc}）"


def wechat_voice_block_safe(vpath: str, *, ilink_text: str) -> str:
    try:
        from butler.gateway.speech_stt import transcribe_voice_file

        text = transcribe_voice_file(vpath)
        return f"[微信语音转写]\n{text}"
    except Exception as exc:
        logger.warning("WeChat STT failed for %s: %s", vpath, exc)
        if ilink_text:
            return f"[微信语音转写]\n{ilink_text}"
        return (
            "--- 语音转写 ---\n"
            f"（转写失败：{exc}。请用文字重说，或安装 ffmpeg + faster-whisper）"
        )
