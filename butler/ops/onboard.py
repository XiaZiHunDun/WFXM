"""One-page onboarding checklist for new Owners / operators (PROD-P6-01)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

ProfileName = Literal["gateway", "dev-local", "dev-remote"]

_PROFILE_REQUIRED: dict[ProfileName, tuple[str, ...]] = {
    "gateway": (
        "MINIMAX_API_KEY",
        "BUTLER_OWNER_WECHAT_ID",
        "BUTLER_PROJECTS_DIR",
    ),
    "dev-local": (
        "MINIMAX_API_KEY",
        "BUTLER_DEPLOY_PROFILE",
    ),
    "dev-remote": (
        "MINIMAX_API_KEY",
        "BUTLER_ENV_PROFILE",
    ),
}

_PROFILE_OPTIONAL: dict[ProfileName, tuple[str, ...]] = {
    "gateway": (
        "BUTLER_EVAL_PROD_EVIDENCE",
        "BUTLER_GATEWAY_DURABLE_OUTBOX",
        "BUTLER_ONBOARDING_WELCOME",
    ),
    "dev-local": ("BUTLER_ENV_PROFILE", "PYTHONPATH"),
    "dev-remote": ("BUTLER_CC_BRIDGE", "BUTLER_TERMINAL_PROFILE"),
}

_PROFILE_NEXT_STEPS: dict[ProfileName, tuple[str, ...]] = {
    "gateway": (
        "cp .env.example .env  # 填 LLM Key 与 BUTLER_OWNER_WECHAT_ID",
        "pip install -e \".[gateway]\"",
        "butler wechat-setup",
        "bash scripts/install-butler-gateway-service.sh",
        "bash scripts/butler-gateway-ops.sh status",
        "微信发 /状态 · /简报",
    ),
    "dev-local": (
        "export BUTLER_DEPLOY_PROFILE=dev",
        "pip install -e \".[dev]\"",
        "export PYTHONPATH=.",
        "bash scripts/butler-pytest-fast-gate.sh",
        "butler chat",
    ),
    "dev-remote": (
        "export BUTLER_ENV_PROFILE=dev-remote",
        "export BUTLER_CC_BRIDGE=1  # opt-in",
        "python3 scripts/apply-butler-env-profile.py dev-remote",
        "微信 /沙箱 · /分工",
    ),
}


def _env_set(name: str) -> bool:
    val = os.getenv(name, "").strip()
    if name == "MINIMAX_API_KEY":
        from butler.ops.deploy_profile import _llm_key_set

        return _llm_key_set()
    if name == "BUTLER_DEPLOY_PROFILE":
        return val in ("dev", "gateway", "all")
    if name == "BUTLER_ENV_PROFILE":
        return bool(val)
    if name == "PYTHONPATH":
        return bool(val) or Path.cwd().name != ""
    return bool(val)


def resolve_onboard_profile(
    explicit: str = "",
) -> ProfileName:
    raw = str(explicit or "").strip().lower()
    if raw in ("gateway", "dev-local", "dev-remote"):
        return raw  # type: ignore[return-value]
    from butler.ops.deploy_profile import effective_operating_profile

    op = effective_operating_profile()
    if op in ("gateway", "dev-local", "dev-remote"):
        return op  # type: ignore[return-value]
    return "gateway"


def format_onboard_report(*, profile: ProfileName | None = None) -> str:
    prof = profile or resolve_onboard_profile()
    lines = [
        "Butler 上手一页纸（PROD-P6 onboard）",
        "",
        f"剖面：{prof}",
        "文档：docs/guides/deploy-profiles-2026-06.md",
        "",
        "必填项",
    ]
    for key in _PROFILE_REQUIRED[prof]:
        mark = "✓" if _env_set(key) else "✗"
        lines.append(f"  {mark} {key}")

    lines.append("")
    lines.append("推荐项")
    for key in _PROFILE_OPTIONAL[prof]:
        mark = "✓" if _env_set(key) else "·"
        lines.append(f"  {mark} {key}")

    env_path = Path.cwd() / ".env"
    lines.append("")
    lines.append(f".env：{'✓ ' + str(env_path) if env_path.is_file() else '✗ 请 cp .env.example .env'}")

    from butler.ops.deploy_profile import profile_deviation_warnings

    warns = profile_deviation_warnings()
    if warns:
        lines.append("")
        lines.append("注意")
        for w in warns:
            lines.append(f"  ⚠ {w}")

    lines.append("")
    lines.append("下一步")
    for step in _PROFILE_NEXT_STEPS[prof]:
        lines.append(f"  {step}")

    lines.append("")
    lines.append("Owner 首周：docs/guides/owner-first-week-2026-06.md")
    lines.append("运维：docs/guides/wechat-gateway-ops.md")
    return "\n".join(lines)


__all__ = [
    "format_onboard_report",
    "resolve_onboard_profile",
]
