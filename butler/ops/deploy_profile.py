"""Deploy / env profile helpers for Owner diagnostics and doctor (PROD-P0-02)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

OperatingProfile = Literal["gateway", "dev-local", "dev-remote", "unknown"]

_DEPLOY_PROFILES = frozenset({"gateway", "dev", "all"})
_ENV_PROFILES = frozenset({"lead", "dev-gateway", "dev-local", "dev-remote"})

_LLM_KEY_VARS = (
    "MINIMAX_API_KEY",
    "MINIMAX_CN_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)


def deploy_profile() -> str:
    return os.getenv("BUTLER_DEPLOY_PROFILE", "").strip().lower()


def env_profile() -> str:
    return os.getenv("BUTLER_ENV_PROFILE", "").strip().lower()


def _llm_key_set() -> bool:
    return any(os.getenv(k, "").strip() for k in _LLM_KEY_VARS)


def gateway_singleton_lock_held() -> bool:
    """True when another process holds the gateway flock (best-effort)."""
    data_home = os.getenv("BUTLER_DATA_HOME", "").strip()
    base = Path(data_home).expanduser() if data_home else Path.home() / ".butler"
    path = base / "gateway.singleton.lock"
    if not path.is_file():
        return False
    import fcntl

    fd = os.open(str(path), os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    except BlockingIOError:
        return True
    except OSError:
        return False
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def effective_operating_profile() -> OperatingProfile:
    ep = env_profile()
    if ep == "dev-remote":
        return "dev-remote"
    if ep == "dev-local":
        return "dev-local"
    if ep in ("lead", "dev-gateway"):
        return "gateway"
    dp = deploy_profile()
    if dp == "gateway" or gateway_singleton_lock_held():
        return "gateway"
    if dp == "dev":
        return "dev-local"
    return "unknown"


def profile_deviation_warnings() -> list[str]:
    """Human hints when env vars disagree with detected runtime."""
    warnings: list[str] = []
    dp = deploy_profile()
    ep = env_profile()
    lock = gateway_singleton_lock_held()
    op = effective_operating_profile()

    if lock and dp == "dev" and not ep:
        warnings.append("Gateway 进程在跑，但 BUTLER_DEPLOY_PROFILE=dev（建议 gateway 或 dev-local）")
    if op == "gateway" and not _llm_key_set():
        warnings.append("生产剖面未检测到 LLM API Key")
    if op == "gateway" and not os.getenv("BUTLER_OWNER_WECHAT_ID", "").strip():
        warnings.append("未配置 BUTLER_OWNER_WECHAT_ID（Owner 门控可能不可用）")
    if ep == "dev-remote" and os.getenv("BUTLER_CC_BRIDGE", "0").strip() not in ("1", "true", "yes"):
        warnings.append("dev-remote 剖面建议 BUTLER_CC_BRIDGE=1")
    return warnings


def _yes_no(ok: bool) -> str:
    return "✓" if ok else "✗"


def format_owner_profile_lines(*, max_lines: int = 8) -> list[str]:
    """5–8 profile-relevant lines for Owner /诊断 brief."""
    op = effective_operating_profile()
    dp = deploy_profile() or "(未设)"
    ep = env_profile()
    lines = [f"部署剖面：{op}（pip={dp}" + (f", env={ep}" if ep else "") + ")"]

    if op == "gateway":
        lines.append(f"  LLM Key：{_yes_no(_llm_key_set())}")
        lines.append(
            f"  Owner 微信：{_yes_no(bool(os.getenv('BUTLER_OWNER_WECHAT_ID', '').strip()))}"
        )
        export_on = os.getenv("BUTLER_EXPORT_SEND_WECHAT_FILE", "1").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        lines.append(f"  微信文件出站：{_yes_no(export_on)}")
        lines.append(f"  Gateway 锁：{'运行中' if gateway_singleton_lock_held() else '未检测到'}")
        prod_ev = os.getenv("BUTLER_EVAL_PROD_EVIDENCE", "1").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        lines.append(f"  G1-04 生产记账：{_yes_no(prod_ev)}")
        mcp = os.getenv("BUTLER_MCP_ENABLED", "0").strip().lower() in ("1", "true", "yes")
        lines.append(f"  MCP：{'开' if mcp else '关'}")
    elif op == "dev-local":
        lines.append(f"  LLM Key：{_yes_no(_llm_key_set())}")
        lines.append(f"  pip 推荐：BUTLER_DEPLOY_PROFILE=dev")
        sandbox = os.getenv("BUTLER_TERMINAL_SANDBOX", "0").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        lines.append(f"  终端沙箱：{'开' if sandbox else '关'}")
        lines.append("  守门：bash scripts/butler-pytest-fast-gate.sh")
    elif op == "dev-remote":
        lines.append(f"  LLM Key：{_yes_no(_llm_key_set())}")
        bridge = os.getenv("BUTLER_CC_BRIDGE", "0").strip().lower() in ("1", "true", "yes")
        lines.append(f"  CC 桥接：{'开' if bridge else '关'}")
        lines.append(f"  终端 profile：{os.getenv('BUTLER_TERMINAL_PROFILE', '(默认)')}")
        lines.append("  相关：/沙箱 · /分工")
    else:
        lines.append(f"  LLM Key：{_yes_no(_llm_key_set())}")
        lines.append("  建议设 BUTLER_DEPLOY_PROFILE 或读 deploy-profiles 指南")

    for w in profile_deviation_warnings():
        if len(lines) >= max_lines:
            break
        lines.append(f"  ⚠ {w}")

    return lines[:max_lines]


__all__ = [
    "deploy_profile",
    "effective_operating_profile",
    "env_profile",
    "format_owner_profile_lines",
    "gateway_singleton_lock_held",
    "profile_deviation_warnings",
]
