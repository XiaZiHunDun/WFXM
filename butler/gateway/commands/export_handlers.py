"""WeChat session export commands."""

from __future__ import annotations

from butler.gateway.owner_gate import is_gateway_owner, owner_required_message


def handle_export_session_command(
    arg: str,
    *,
    platform: str,
    external_id: str | None,
    session_key: str,
) -> str:
    if not is_gateway_owner(platform=platform, external_id=external_id, session_key=session_key):
        return owner_required_message()

    max_lines = 0
    if str(arg or "").strip().isdigit():
        max_lines = int(arg.strip())

    from butler.core.transcript_export import (
        export_session_markdown,
        resolve_export_workspace,
    )

    ws = resolve_export_workspace(session_key)
    result = export_session_markdown(
        session_key,
        max_lines=max_lines or None,
        workspace=ws,
    )
    if not result.get("ok"):
        return f"导出失败: {result.get('error', '?')}"

    path = result.get("path") or ""
    plat = str(platform or "").strip().lower()
    msg = (
        f"已导出会话 Markdown（{result.get('sections', 0)} 段）\n"
        f"大小: {result.get('bytes', 0)} 字节"
    )
    if plat in ("wechat", "weixin"):
        from butler.gateway.outbound_files import (
            append_wechat_file_delivery_line,
            export_wechat_file_enabled,
        )

        if export_wechat_file_enabled() and path:
            msg += "\n\n（正在发送 .md 文件…）"
            return append_wechat_file_delivery_line(msg, path)
    return f"{msg}\n路径: {path}"
