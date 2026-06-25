"""Terminal / sandbox env profile helpers (lead vs dev-gateway vs dev-local)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from butler.env_parse import env_truthy

VALID_PROFILES = frozenset({"lead", "dev-gateway", "dev-local", "dev-remote"})


@dataclass(frozen=True)
class EnvProfileExpectation:
    name: str
    terminal_enabled: bool
    sandbox_enabled: bool
    fail_if_unavailable: bool
    description: str


PROFILE_EXPECTATIONS: dict[str, EnvProfileExpectation] = {
    "lead": EnvProfileExpectation(
        name="lead",
        terminal_enabled=False,
        sandbox_enabled=False,
        fail_if_unavailable=False,
        description="微信生产 Lead：terminal 关，委派 dev / runtime job",
    ),
    "dev-gateway": EnvProfileExpectation(
        name="dev-gateway",
        terminal_enabled=True,
        sandbox_enabled=True,
        fail_if_unavailable=True,
        description="Linux dev 网关：terminal + bubblewrap 沙箱，无 bwrap 硬失败",
    ),
    "dev-local": EnvProfileExpectation(
        name="dev-local",
        terminal_enabled=True,
        sandbox_enabled=False,
        fail_if_unavailable=False,
        description="本机开发：terminal 开，无 bwrap 时 honest 关 OS 沙箱",
    ),
    "dev-remote": EnvProfileExpectation(
        name="dev-remote",
        terminal_enabled=True,
        sandbox_enabled=True,
        fail_if_unavailable=True,
        description="远程开发：terminal + bwrap + CC 桥接 + 网络 allowlist 模式",
    ),
}


def current_env_profile() -> str:
    raw = os.getenv("BUTLER_ENV_PROFILE", "").strip().lower()
    return raw if raw in VALID_PROFILES else ""


def profile_expectation(name: str = "") -> EnvProfileExpectation | None:
    key = (name or current_env_profile()).strip().lower()
    if not key:
        return None
    return PROFILE_EXPECTATIONS.get(key)


def profile_mismatch_messages(*, bwrap_available: bool) -> list[str]:
    """Return human hints when BUTLER_ENV_PROFILE disagrees with actual env."""
    prof = profile_expectation()
    if prof is None:
        return []

    msgs: list[str] = []
    term_on = env_truthy("BUTLER_ENABLE_TERMINAL", default=False)
    sandbox_on = env_truthy("BUTLER_TERMINAL_SANDBOX", default=False)
    fail_closed = env_truthy("BUTLER_TERMINAL_SANDBOX_FAIL_UNAVAILABLE", default=False)

    if term_on != prof.terminal_enabled:
        want = "1" if prof.terminal_enabled else "0"
        msgs.append(
            f"Profile `{prof.name}` 期望 BUTLER_ENABLE_TERMINAL={want}，当前={'1' if term_on else '0'}"
        )
    if sandbox_on != prof.sandbox_enabled:
        want = "1" if prof.sandbox_enabled else "0"
        msgs.append(
            f"Profile `{prof.name}` 期望 BUTLER_TERMINAL_SANDBOX={want}，当前={'1' if sandbox_on else '0'}"
        )
    if fail_closed != prof.fail_if_unavailable:
        want = "1" if prof.fail_if_unavailable else "0"
        msgs.append(
            "Profile `{name}` 期望 BUTLER_TERMINAL_SANDBOX_FAIL_UNAVAILABLE={want}，"
            "当前={cur}".format(name=prof.name, want=want, cur="1" if fail_closed else "0")
        )
    if prof.name == "dev-gateway" and prof.sandbox_enabled and not bwrap_available:
        msgs.append(
            "Profile dev-gateway 需要 bubblewrap：sudo apt-get install -y bubblewrap"
        )
    if prof.name == "lead" and (term_on or sandbox_on):
        msgs.append("Profile lead 不应开启 terminal/沙箱；请运行 scripts/apply-butler-env-profile.py lead")
    return msgs


__all__ = [
    "EnvProfileExpectation",
    "PROFILE_EXPECTATIONS",
    "VALID_PROFILES",
    "current_env_profile",
    "profile_expectation",
    "profile_mismatch_messages",
]
