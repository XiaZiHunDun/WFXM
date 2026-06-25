"""Terminal sandbox status and Owner sandbox.json policy (/沙箱)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from butler.gateway.command_registry import CommandContext, CommandDef, register, require_owner


def _workspace(ctx: CommandContext) -> Path | None:
    pm = ctx.orchestrator.project_manager
    proj = pm.get_current(session_key=ctx.session_key)
    if proj is None:
        return None
    ws = Path(getattr(proj, "workspace", "") or "")
    return ws if ws.is_dir() else None


def _format_policy_help() -> str:
    return (
        "用法：\n"
        "  /沙箱              诊断与 profile 指引\n"
        "  /沙箱 策略          查看当前项目 sandbox.json（合并后）\n"
        "  /沙箱 策略 示例     复制 .butler/sandbox.json.example 到项目\n"
        "\n"
        "改网关沙箱开关（须 restart）：\n"
        "  python3 scripts/apply-butler-env-profile.py dev-remote\n"
        "  或编辑 .env：BUTLER_TERMINAL_SANDBOX / BUTLER_CC_BRIDGE\n"
        "\n"
        "npm/pip 被沙箱断网时：\n"
        "  /批准沙箱外 <命令>  或 dev-remote + networkPolicy.allow"
    )


def _merged_sandbox_view(workspace: Path) -> dict[str, Any]:
    from butler.tools.terminal_sandbox import load_terminal_sandbox_config

    cfg = load_terminal_sandbox_config(workspace)
    return {
        "type": cfg.sandbox_type,
        "additionalReadwritePaths": list(cfg.additional_readwrite_paths),
        "additionalReadonlyPaths": list(cfg.additional_readonly_paths),
        "disableTmpWrite": cfg.disable_tmp_write,
        "networkPolicy": {
            "default": cfg.network.default,
            "allow": list(cfg.network.allow),
            "deny": list(cfg.network.deny),
        },
        "enabled": cfg.enabled,
        "failIfUnavailable": cfg.fail_if_unavailable,
    }


def _cmd_sandbox(ctx: CommandContext) -> Optional[str]:
    arg = (ctx.arg or "").strip()
    sub = arg.split(None, 1)[0].lower() if arg else ""
    rest = arg.split(None, 1)[1].strip() if arg and " " in arg else ""

    if sub in ("策略", "policy"):
        gate = require_owner(ctx)
        if gate:
            return gate
        ws = _workspace(ctx)
        if ws is None:
            return "无活跃项目，请先 /切换 到目标项目"
        target = ws / ".butler" / "sandbox.json"
        if rest in ("示例", "example", "init"):
            example = Path(__file__).resolve().parents[3] / ".butler" / "sandbox.json.example"
            if not example.is_file():
                example = ws.parents[1] / ".butler" / "sandbox.json.example"
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_file():
                return f"已存在 {target.relative_to(ws)}，未覆盖"
            target.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
            return (
                f"已写入 {target.relative_to(ws)}\n"
                "可编辑 networkPolicy.allow 后 restart；"
                "dev-remote 档可配合 BUTLER_TERMINAL_SANDBOX_NETWORK_ALLOWLIST=1"
            )
        view = _merged_sandbox_view(ws)
        lines = [
            f"项目沙箱策略（{ws.name}）",
            f"  文件：{(target if target.is_file() else '(无，用 ~/.butler/sandbox.json 或 example)')}",
            json.dumps(view, ensure_ascii=False, indent=2),
        ]
        return "\n".join(lines)

    from butler.ops.env_profiles import current_env_profile, profile_expectation
    from butler.ops.terminal_sandbox_diagnostics import format_terminal_sandbox_diagnostic_lines
    from butler.runtime.cc_bridge import cc_bridge_enabled, claude_cli_path

    ws = _workspace(ctx)
    lines = ["终端沙箱与远程开发", ""]
    lines.extend(format_terminal_sandbox_diagnostic_lines(workspace=ws))
    prof = profile_expectation() or profile_expectation(current_env_profile() or "")
    if prof:
        lines.append(f"  Profile：{prof.name} — {prof.description}")
    lines.append(f"  CC 桥接：{'开' if cc_bridge_enabled() else '关'}"
                 f"{'' if not cc_bridge_enabled() else (' · ' + (claude_cli_path() or 'claude 未安装'))}")
    lines.append("")
    lines.append(_format_policy_help())
    return "\n".join(lines)


_SANDBOX_COMMANDS: list[CommandDef] = [
    CommandDef(
        "/沙箱",
        ("/sandbox",),
        "开发工具",
        "终端沙箱诊断与 sandbox.json 策略",
        handler=_cmd_sandbox,
    ),
]


def register_sandbox_commands() -> None:
    for cmd in _SANDBOX_COMMANDS:
        register(cmd)


register_sandbox_commands()
