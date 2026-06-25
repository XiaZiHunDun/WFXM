"""Package long Owner-facing text as .txt/.md exports for WeChat file delivery."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path

from butler.config import get_butler_home
from butler.env_parse import env_truthy, int_env
from butler.gateway.outbound_files import (
    append_wechat_file_delivery_line,
    export_wechat_file_enabled,
    export_wechat_max_bytes,
)


def is_wechat_platform(platform: str) -> bool:
    return str(platform or "").strip().lower() in ("wechat", "weixin")


def attach_min_chars() -> int:
    return int_env("BUTLER_WECHAT_ATTACH_MIN_CHARS", 400, min=0)


def attach_delegate_enabled() -> bool:
    return env_truthy("BUTLER_WECHAT_ATTACH_DELEGATE", default=True) and export_wechat_file_enabled()


def attach_detail_enabled() -> bool:
    return env_truthy("BUTLER_WECHAT_ATTACH_DETAIL", default=True) and export_wechat_file_enabled()


def attach_diagnostic_enabled() -> bool:
    return env_truthy("BUTLER_WECHAT_ATTACH_DIAGNOSTIC", default=True) and export_wechat_file_enabled()


def attach_runtime_enabled() -> bool:
    return env_truthy("BUTLER_WECHAT_ATTACH_RUNTIME", default=True) and export_wechat_file_enabled()


def wechat_attach_suffix() -> str:
    """WeChat file attachment extension; default ``.txt`` (phone-friendly plain text)."""
    raw = os.getenv("BUTLER_WECHAT_ATTACH_SUFFIX", ".txt").strip().lower()
    if raw in ("txt", ".txt"):
        return ".txt"
    if raw in ("md", "markdown", ".md", ".markdown"):
        return ".md" if raw.startswith(".") else f".{raw}"
    return ".txt"


def _safe_segment(value: str) -> str:
    raw = str(value or "").strip() or "export"
    return re.sub(r"[^a-zA-Z0-9._+-]+", "_", raw)[:80] or "export"


def _export_dir(workspace: Path | None) -> Path:
    if workspace is not None:
        out = Path(workspace) / ".butler" / "exports"
    else:
        out = get_butler_home() / "exports"
    out.mkdir(parents=True, exist_ok=True)
    return out


def write_text_export(
    body: str,
    *,
    name_prefix: str,
    workspace: Path | None = None,
    suffix: str | None = None,
) -> Path | None:
    """Write scrubbed text under exports/; return path or None on failure."""
    from butler.gateway.pii_scrub import scrub_outbound_text

    text = scrub_outbound_text(str(body or ""))
    if not text.strip():
        return None

    ext = suffix if suffix is not None else wechat_attach_suffix()
    ext = ext if ext.startswith(".") else f".{ext}"
    if ext.lower() not in (".md", ".markdown", ".txt"):
        ext = wechat_attach_suffix()

    max_bytes = export_wechat_max_bytes()
    encoded = text.encode("utf-8")
    if len(encoded) > max_bytes:
        text = (
            encoded[: max_bytes - 80].decode("utf-8", errors="ignore")
            + "\n\n…（已截断至微信附件大小上限）\n"
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    name = f"{_safe_segment(name_prefix)}_{stamp}{ext}"
    path = _export_dir(workspace) / name
    try:
        path.write_text(text, encoding="utf-8")
    except OSError:
        return None
    return path


def maybe_attach_wechat_file(
    chat_text: str,
    full_body: str,
    *,
    platform: str,
    name_prefix: str,
    workspace: Path | None = None,
    enabled: bool = True,
    min_chars: int | None = None,
    suffix: str | None = None,
    attach_hint: str = "（完整内容见附件）",
) -> str:
    """
    On WeChat, when ``full_body`` is long enough, write it to exports/ and
    append a deliverable path line for ``WeChatAdapter.send()``.
    """
    if not is_wechat_platform(platform):
        return chat_text if chat_text.strip() else full_body
    if not enabled or not export_wechat_file_enabled():
        return chat_text if chat_text.strip() else full_body

    full = str(full_body or "")
    threshold = attach_min_chars() if min_chars is None else max(0, int(min_chars))
    if len(full) < threshold:
        return chat_text if chat_text.strip() else full

    path = write_text_export(
        full,
        name_prefix=name_prefix,
        workspace=workspace,
        suffix=suffix,
    )
    if path is None:
        return chat_text if chat_text.strip() else full

    summary = (chat_text or "").strip()
    if not summary:
        summary = full[: min(280, threshold)] + f"\n\n{attach_hint}"
    elif attach_hint not in summary:
        summary = f"{summary}\n\n{attach_hint}"

    return append_wechat_file_delivery_line(summary, path)


def build_delegate_completion_message(
    report,
    *,
    prefix: str = "",
    platform: str = "wechat",
    workspace: Path | None = None,
) -> str:
    """Compact WeChat text plus optional full report file attachment."""
    from butler.report import format_detail, format_for_wechat

    body = format_for_wechat(report)
    chat = f"{prefix}\n\n{body}".strip() if prefix else body
    if not attach_delegate_enabled() or not is_wechat_platform(platform):
        return chat

    tid = str(getattr(report, "task_id", "") or "report").strip() or "report"
    full = format_detail(report)
    return maybe_attach_wechat_file(
        chat,
        full,
        platform=platform,
        name_prefix=f"delegate_{tid}",
        workspace=workspace,
        enabled=True,
        attach_hint="（完整委派报告见 .txt 附件）",
    )


__all__ = [
    "attach_delegate_enabled",
    "attach_detail_enabled",
    "attach_diagnostic_enabled",
    "attach_runtime_enabled",
    "attach_min_chars",
    "build_delegate_completion_message",
    "is_wechat_platform",
    "maybe_attach_wechat_file",
    "wechat_attach_suffix",
    "write_text_export",
]
