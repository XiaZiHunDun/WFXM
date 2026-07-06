"""Transport-level cache_control 4-boundary auto-placement (Sprint 29 P2-4.3).

Anthropic Prompt Caching 在 4 个 boundary 上接受 ``cache_control: {type: ephemeral}``
标记, 4 个 boundary 都在 transport 这一层自动布点能最大化 cache 命中率:

  1. system prompt      — 给 system 末尾 text block 加 marker
  2. 最后 user message   — 给最后 role=user 的 content 末尾加 marker block
  3. tools 数组          — 给 tools 列表最后一项顶层加 marker
  4. 最后 tool_result    — 给 tool_result 块的 content 末尾加 marker

与 ``cache_safe_delegate`` 的关系: 后者是 delegate 侧"防 prompt prefix 改坏 cache"
的安全策略 (不同层次); 本模块是 transport 侧的"自动布点"优化层.

bypass 开关: ``BUTLER_TRANSPORT_CACHE_CONTROL=0`` (默认 True) → 4 boundary 全部
早退, kwargs 不动.
"""

from __future__ import annotations

from typing import Any

from butler.env_parse import env_truthy


_CACHE_CONTROL_MARKER: dict[str, str] = {"type": "ephemeral"}


def cache_control_enabled() -> bool:
    """True unless ``BUTLER_TRANSPORT_CACHE_CONTROL`` is explicitly disabled."""
    return bool(env_truthy("BUTLER_TRANSPORT_CACHE_CONTROL", default=True))


def apply_cache_control_to_system(system: Any) -> list[dict[str, Any]]:
    """Return system prompt as a list of text blocks with cache marker on tail.

    - 关闭时返 ``[]`` (caller 走原 str 路径)
    - 开启 + 空 system → 返 ``[]`` (不构造空 block)
    - 开启 + 有 text → 返 ``[{"type": "text", "text": ..., "cache_control": ...}]``
    """
    if not cache_control_enabled():
        return []
    text = str(system or "").strip()
    if not text:
        return []
    return [
        {
            "type": "text",
            "text": text,
            "cache_control": dict(_CACHE_CONTROL_MARKER),
        }
    ]


def _ensure_content_list(content: Any) -> list[dict[str, Any]]:
    """Normalize message content to a list-of-blocks form.

    - str → ``[{"type": "text", "text": <str>}]``
    - list → 透传 (assumed to already be list of blocks)
    - 其他 → 包装成 ``[{"type": "text", "text": str(content)}]``
    """
    if isinstance(content, list):
        return list(content)
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [{"type": "text", "text": str(content)}]


def apply_cache_control_to_messages(messages: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Append cache marker to the last ``role=user`` message's content tail.

    - 关闭时透传 (原 list 引用, 调用方不依赖深拷贝)
    - 没有 ``role=user`` 的消息 → 整体不动
    - user content 已是 list → 在末尾追加 1 个 marker block
    - user content 是 str → 转 list, 末尾追加 marker block
    - 最后一条是 assistant → 不动 (assistant 不作 cache breakpoint)
    """
    if not cache_control_enabled():
        return messages if messages is not None else []
    if not messages:
        return messages if messages is not None else []
    last_user_idx: int | None = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            last_user_idx = i
            break
    if last_user_idx is None:
        return messages
    msg = dict(messages[last_user_idx])
    blocks = _ensure_content_list(msg.get("content"))
    blocks = list(blocks) + [
        {"type": "text", "text": "", "cache_control": dict(_CACHE_CONTROL_MARKER)}
    ]
    msg["content"] = blocks
    out = list(messages)
    out[last_user_idx] = msg
    return out


def apply_cache_control_to_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Add cache marker to the last tool in the tools array.

    - 关闭时透传
    - 空 tools / None → 返 ``[]``
    - 开启 + tools → 最后 1 个 tool 顶层加 ``cache_control`` 字段
    """
    if not cache_control_enabled():
        return tools if tools is not None else []
    if not tools:
        return []
    out = list(tools)
    last = dict(out[-1])
    last["cache_control"] = dict(_CACHE_CONTROL_MARKER)
    out[-1] = last
    return out


def apply_cache_control_to_last_tool_result(
    messages: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Add cache marker to the last ``tool_result`` block in messages.

    Operates on Anthropic-format messages (list of role/content). Iterates
    reverse to find the last user message whose content list contains a
    ``tool_result`` block; mutates a copy of that block with the marker.

    - 关闭时透传
    - 无 tool_result 块 → 整体不动
    - 多个 tool_result → 只给最后 1 个加 marker
    """
    if not cache_control_enabled():
        return messages if messages is not None else []
    if not messages:
        return messages if messages is not None else []
    target_idx: int | None = None
    target_block_idx: int | None = None
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if m.get("role") != "user":
            continue
        content = m.get("content")
        if not isinstance(content, list):
            continue
        for j in range(len(content) - 1, -1, -1):
            if isinstance(content[j], dict) and content[j].get("type") == "tool_result":
                target_idx = i
                target_block_idx = j
                break
        if target_idx is not None:
            break
    if target_idx is None or target_block_idx is None:
        return messages
    out = list(messages)
    msg = dict(out[target_idx])
    new_content = list(msg["content"])
    block = dict(new_content[target_block_idx])
    block["cache_control"] = dict(_CACHE_CONTROL_MARKER)
    new_content[target_block_idx] = block
    msg["content"] = new_content
    out[target_idx] = msg
    return out


__all__ = [
    "cache_control_enabled",
    "apply_cache_control_to_system",
    "apply_cache_control_to_messages",
    "apply_cache_control_to_tools",
    "apply_cache_control_to_last_tool_result",
]
