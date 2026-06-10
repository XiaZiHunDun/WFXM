"""Optional provider-side remote compaction (/v1/responses/compact subset)."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)


def remote_compact_enabled() -> bool:
    return env_truthy("BUTLER_REMOTE_COMPACT", default=False)


def remote_compact_url_override() -> str:
    return str(os.getenv("BUTLER_REMOTE_COMPACT_URL", "") or "").strip()


def _compact_endpoint(base_url: str) -> str:
    override = remote_compact_url_override()
    if override:
        return override
    root = (base_url or "").rstrip("/")
    if root.endswith("/v1"):
        return f"{root}/responses/compact"
    return f"{root}/v1/responses/compact"


def _host_allows_remote(base_url: str) -> bool:
    if remote_compact_url_override():
        return True
    if env_truthy("BUTLER_REMOTE_COMPACT_FORCE", default=False):
        return True
    host = (urlparse(base_url or "").hostname or "").lower()
    return "openai.com" in host or "chatgpt.com" in host


def _messages_to_compact_input(messages: list[dict]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        role = str(m.get("role") or "user")
        if role not in ("user", "assistant", "developer", "system"):
            continue
        content = str(m.get("content") or "")
        if not content and m.get("tool_calls"):
            content = f"[tool_calls: {len(m['tool_calls'])}]"
        if not content.strip():
            continue
        out.append(
            {
                "type": "message",
                "role": role if role != "system" else "developer",
                "content": [{"type": "input_text", "text": content[:8000]}],
            }
        )
    return out


def _extract_summary_from_response(data: dict[str, Any]) -> str | None:
    if not isinstance(data, dict):
        return None
    for key in ("summary", "compacted_summary", "text"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    output = data.get("output")
    if isinstance(output, list):
        for item in reversed(output):
            if not isinstance(item, dict):
                continue
            if item.get("type") == "compaction":
                for field in ("encrypted_content", "summary", "text"):
                    val = item.get(field)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
            content = item.get("content")
            if isinstance(content, list):
                parts = [
                    str(c.get("text") or "")
                    for c in content
                    if isinstance(c, dict) and c.get("text")
                ]
                joined = "\n".join(parts).strip()
                if joined:
                    return joined
            if isinstance(content, str) and content.strip():
                return content.strip()
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        msg = (choices[0] or {}).get("message") or {}
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return None


def try_remote_summarize(middle: list[dict], previous_summary: str = "") -> str | None:
    """
    POST to /v1/responses/compact when enabled and endpoint is allowed.
    Returns summary text, or None to fall back to local auxiliary compaction.
    """
    if not remote_compact_enabled() or len(middle) < 2:
        return None

    from butler.core.compaction_prompt import build_compaction_user_prompt
    from butler.core.context_compressor import _format_for_summary
    from butler.transport.auxiliary_client import create_auxiliary_client

    client = create_auxiliary_client("compression")
    base_url = str(getattr(client, "_base_url", "") or "")
    api_key = str(getattr(client, "_api_key", "") or "")
    if not base_url or not _host_allows_remote(base_url):
        return None

    transcript = _format_for_summary(middle)
    if len(transcript) < 100:
        return None

    prompt = build_compaction_user_prompt(
        transcript=transcript,
        previous_summary=previous_summary,
    )
    input_items = _messages_to_compact_input(middle)
    if not input_items:
        input_items = [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": prompt[:12000]}],
            }
        ]

    from butler.config import get_butler_settings

    compact_model = (
        getattr(client, "model", None)
        or get_butler_settings().remote_compact_model_name()
        or ""
    )
    if not compact_model:
        return None

    body: dict[str, Any] = {
        "model": compact_model,
        "input": input_items,
        "instructions": (
            "Compress the conversation into structured handoff notes. "
            "Respond as a single compaction summary."
        ),
    }

    url = _compact_endpoint(base_url)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key or 'dummy'}",
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=int(getattr(client, "timeout", 120))) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
    except urllib.error.HTTPError as exc:
        logger.info("Remote compact HTTP %s at %s", exc.code, url)
        return None
    except Exception as exc:
        logger.debug("Remote compact failed: %s", exc)
        return None

    summary = _extract_summary_from_response(data)
    if summary:
        try:
            from butler.ops.retry_buckets import record_recovery_event

            record_recovery_event("remote_compact_ok")
        except Exception as exc:
            logger.debug("try remote summarize skipped: %s", exc)
        return summary
    return None
