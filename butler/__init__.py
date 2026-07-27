"""Butler System v4 — 自建 Agent Loop + 微信 Gateway 管家。

提供：用户→管家→项目的层次结构、分层记忆、Skill自动合并、多角色模型配置。

目录结构（基于九层模型）：
- L1 接入与交互: gateway/, cli/
- L2 编排与控制: orchestrator/, workflows/, delegate/
- L3 认知推理环: core/ (agent_loop/, context/, compaction/, tool/, session/, llm/, loop/)
- L4 工具与能力: tools/, mcp/, skills/, dev_engine/
- L5 记忆与知识: memory/
- L6 模型与协议: transport/
- L7 策略与门控: permissions/
- L8 可靠性与韧性: resilience/
- L9 观测与运营: ops/
- 横切: contracts/, configuration/, utilities/
"""

from __future__ import annotations

import datetime
import logging
import sys

__version__ = "4.0.0"

__all__ = [
    "core",
    "gateway",
    "orchestrator",
    "tools",
    "memory",
    "transport",
    "permissions",
    "resilience",
    "ops",
    "configuration",
    "utilities",
    "contracts",
    "mcp",
    "skills",
    "dev_engine",
    "workflows",
    "delegate",
    "session",
    "cli",
    "__version__",
    "get_build_identity",
    "format_build_identity_line",
    "mark_start_time",
]

_logger = logging.getLogger(__name__)

_git_sha: str | None = None
_start_time: datetime.datetime | None = None


def _resolve_git_sha() -> str:
    global _git_sha
    if _git_sha is not None:
        return _git_sha
    from butler.butler_init_ops import resolve_git_sha_safe

    _git_sha = resolve_git_sha_safe()
    return _git_sha


def get_build_identity() -> dict[str, str]:
    """Return version, git SHA, python version, and start time for diagnostics."""
    global _start_time
    if _start_time is None:
        _start_time = datetime.datetime.now(tz=datetime.timezone.utc)
    sha = _resolve_git_sha()
    return {
        "version": __version__,
        "git_sha": sha,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "python_path": sys.executable,
        "start_time": _start_time.isoformat(),
    }


def format_build_identity_line() -> str:
    info = get_build_identity()
    return f"Butler v{info['version']} (commit={info['git_sha']}, python={info['python']})"


def mark_start_time() -> None:
    """Record process start time (call once at gateway/CLI entry)."""
    global _start_time
    _start_time = datetime.datetime.now(tz=datetime.timezone.utc)
