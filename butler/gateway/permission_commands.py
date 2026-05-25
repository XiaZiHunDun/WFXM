"""WeChat / CLI permission approval commands."""

from __future__ import annotations

from butler.gateway.owner_gate import is_gateway_owner, owner_required_message
from butler.permission_approvals import grant_always, grant_once, list_always


def parse_permission_command(text: str) -> tuple[str, str] | None:
    """Return (command, arg) for permission slash commands."""
    raw = (text or "").strip()
    if not raw.startswith("/"):
        return None
    parts = raw.split(maxsplit=2)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""
    extra = parts[2] if len(parts) > 2 else ""

    once_cmds = {"/批准一次", "/approve-once", "/approve_once"}
    always_cmds = {"/始终允许", "/always-allow", "/always_allow"}
    list_cmds = {"/权限", "/permissions", "/perm-list"}

    if cmd in once_cmds:
        return ("once", arg)
    if cmd in always_cmds:
        combined = f"{arg} {extra}".strip() if extra else arg
        return ("always", combined)
    if cmd in list_cmds:
        return ("list", "")
    return None


def handle_permission_command(
    text: str,
    *,
    platform: str,
    external_id: str | None,
    session_key: str,
) -> str | None:
    parsed = parse_permission_command(text)
    if parsed is None:
        return None
    if not is_gateway_owner(platform=platform, external_id=external_id, session_key=session_key):
        return owner_required_message()

    action, arg = parsed
    if action == "once":
        return grant_once(session_key, fingerprint=arg.strip())

    if action == "always":
        spec = (arg or "").strip()
        if not spec:
            return (
                "用法：/始终允许 <权限名> 或 /始终允许 write_file:secrets/*\n"
                "示例：/始终允许 external_directory · /始终允许 doom_loop · /始终允许 rule:read_file:AGENTS.md"
            )
        tool = "*"
        pattern = "*"
        permission = spec
        if ":" in spec:
            head, tail = spec.split(":", 1)
            permission = head.strip() or "rule"
            if "." in tail or "/" in tail or "*" in tail:
                tool = permission
                pattern = tail.strip() or "*"
                permission = "rule"
            else:
                tool = head.strip() or "*"
                pattern = tail.strip() or "*"
        return grant_always(
            session_key,
            permission=permission,
            tool=tool,
            pattern=pattern,
        )

    rows = list_always(session_key)
    if not rows:
        return "当前会话无「始终允许」记录。"
    lines = ["始终允许:"]
    for row in rows:
        lines.append(
            f"  · {row.get('permission')} tool={row.get('tool')} pattern={row.get('pattern')}"
        )
    return "\n".join(lines)
