#!/usr/bin/env python3
"""Apply Butler terminal / sandbox env profile to .env (upsert known keys only)."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

PROFILES: dict[str, dict[str, str]] = {
    "lead": {
        "BUTLER_ENV_PROFILE": "lead",
        "BUTLER_ENABLE_TERMINAL": "0",
        "BUTLER_TERMINAL_SANDBOX": "0",
        "BUTLER_TERMINAL_SANDBOX_FAIL_UNAVAILABLE": "0",
        "BUTLER_MEMORY_WRITE_APPROVAL": "owner_scopes",
        "BUTLER_SKILL_WRITE_APPROVAL": "1",
        "BUTLER_TOOLSET": "wechat_minimal",
        "BUTLER_TRANSCRIPT_FTS": "1",
        "BUTLER_MEMORY_OBSERVER_QUEUE": "1",
        "BUTLER_MEMORY_OBSERVATION_RECALL": "1",
        "BUTLER_MEMORY_UNIFIED_RECALL": "1",
    },
    "dev-gateway": {
        "BUTLER_ENV_PROFILE": "dev-gateway",
        "BUTLER_ENABLE_TERMINAL": "1",
        "BUTLER_TERMINAL_PROFILE": "dev",
        "BUTLER_TERMINAL_SANDBOX": "1",
        "BUTLER_TERMINAL_SANDBOX_FAIL_UNAVAILABLE": "1",
    },
    "dev-local": {
        "BUTLER_ENV_PROFILE": "dev-local",
        "BUTLER_ENABLE_TERMINAL": "1",
        "BUTLER_TERMINAL_PROFILE": "dev",
        "BUTLER_TERMINAL_SANDBOX": "0",
        "BUTLER_TERMINAL_SANDBOX_FAIL_UNAVAILABLE": "0",
        "BUTLER_MEMORY_WRITE_APPROVAL": "0",
        "BUTLER_SKILL_WRITE_APPROVAL": "0",
        "BUTLER_TOOLSET": "full",
        "BUTLER_TRANSCRIPT_FTS": "1",
    },
    "dev-remote": {
        "BUTLER_ENV_PROFILE": "dev-remote",
        "BUTLER_ENABLE_TERMINAL": "1",
        "BUTLER_TERMINAL_PROFILE": "dev",
        "BUTLER_TERMINAL_SANDBOX": "1",
        "BUTLER_TERMINAL_SANDBOX_FAIL_UNAVAILABLE": "1",
        "BUTLER_TERMINAL_SANDBOX_NETWORK_ALLOWLIST": "1",
        "BUTLER_CC_BRIDGE": "1",
        "BUTLER_TERMINAL_ALLOWLIST_EXTRA": "claude",
        "BUTLER_MEMORY_WRITE_APPROVAL": "owner_scopes",
        "BUTLER_SKILL_WRITE_APPROVAL": "1",
        "BUTLER_TOOLSET": "full",
        "BUTLER_TRANSCRIPT_FTS": "1",
    },
}

PROFILE_COMMENTS: dict[str, list[str]] = {
    "lead": [
        "# === Terminal Profile: lead（微信生产 Lead，推荐）===",
        "# terminal 关；测试走 delegate dev / runtime readonly job；无需 bubblewrap",
        "# P3-H：observation + hybrid 统一召回（需 BUTLER_SEMANTIC_MEMORY=1 效果更佳）",
    ],
    "dev-gateway": [
        "# === Terminal Profile: dev-gateway（Linux dev 网关）===",
        "# 需: sudo apt install bubblewrap · 无 bwrap 时 terminal 硬失败",
    ],
    "dev-local": [
        "# === Terminal Profile: dev-local（本机开发）===",
        "# 无 bwrap 时 honest 关 OS 沙箱；装 bwrap 后改 dev-gateway 或 dev-remote",
    ],
    "dev-remote": [
        "# === Terminal Profile: dev-remote（微信远程开发 / CC 互补）===",
        "# 需 bubblewrap；CC 桥接 BUTLER_CC_BRIDGE=1；networkPolicy.allow + NETWORK_ALLOWLIST",
    ],
}

_MANAGED_KEYS = frozenset(
    key for profile in PROFILES.values() for key in profile
)
_PROFILE_BLOCK_START = re.compile(r"^#\s*===\s*Terminal Profile:")


def _strip_profile_block(lines: list[str]) -> list[str]:
    out: list[str] = []
    skipping = False
    for line in lines:
        if _PROFILE_BLOCK_START.match(line.strip()):
            skipping = True
            continue
        if skipping:
            stripped = line.strip()
            if not stripped:
                skipping = False
                continue
            if stripped.startswith("#"):
                continue
            key = stripped.split("=", 1)[0].strip()
            if key in _MANAGED_KEYS:
                continue
            skipping = False
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in _MANAGED_KEYS:
                continue
        out.append(line)
    while out and not out[-1].strip():
        out.pop()
    return out


def apply_profile(env_path: Path, profile: str) -> str:
    if profile not in PROFILES:
        raise SystemExit(f"Unknown profile: {profile}. Choose: {', '.join(PROFILES)}")
    if not env_path.is_file():
        raise SystemExit(f"Missing {env_path}")

    values = PROFILES[profile]
    lines = _strip_profile_block(env_path.read_text(encoding="utf-8").splitlines())
    block: list[str] = [""] + PROFILE_COMMENTS[profile]
    for key, value in values.items():
        block.append(f"{key}={value}")
    updated = "\n".join(lines + block) + "\n"
    env_path.write_text(updated, encoding="utf-8")
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply Butler terminal/sandbox env profile")
    parser.add_argument(
        "profile",
        choices=sorted(PROFILES),
        help="lead | dev-gateway | dev-local | dev-remote",
    )
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.dry_run:
        for key, value in PROFILES[args.profile].items():
            print(f"{key}={value}")
        return 0

    apply_profile(args.env, args.profile)
    print(f"Applied profile '{args.profile}' to {args.env.resolve()}")
    if args.profile == "dev-gateway":
        print("Next: sudo apt-get install -y bubblewrap && restart gateway")
    elif args.profile == "dev-remote":
        print("Next: apt install bubblewrap; ensure `claude` on PATH; restart gateway")
    elif args.profile == "dev-local":
        print("Honest mode: OS sandbox off until bubblewrap is installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
