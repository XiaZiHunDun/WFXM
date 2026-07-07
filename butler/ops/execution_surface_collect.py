"""Best-effort collectors for execution surface diagnostics (P0-A / P2-F)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from butler.core.best_effort import safe_best_effort
from butler.config import get_butler_home
from butler.core.harness_flags import mcp_deferred_same_turn_enabled, mcp_deferred_tools_enabled
from butler.mcp.config import mcp_enabled as mcp_enabled_flag
from butler.mcp.deferred import get_promoted_tools
from butler.mcp.diagnostics import format_mcp_diagnostic_lines
from butler.memory.experience_consolidation import load_merge_pending
from butler.ops.runtime_metrics import snapshot_global, snapshot_session
from butler.registry.paths import default_mcp_config_path as registry_default_mcp_config_path
from butler.skills.injection_policy import skill_injection_mode as registry_skill_injection_mode
from butler.skills.similarity import recent_dedup_status
from butler.tenant import DEFAULT_TENANT, tenant_skills_dir
from butler.tools.orthogonality_lint import lint_tool_orthogonality_for_diagnostics
from butler.tools.registry import get_tool_definitions

_EXECUTION_TRUST_COUNTERS: tuple[str, ...] = (
    "execution_fallback_skip",
    "execution_ref_only_load",
    "execution_pointer_pin",
)


def _sum_counter_matches(counters: dict[str, int], name: str) -> int:
    return sum(
        int(v)
        for key, v in counters.items()
        if key == name or key.startswith(f"{name}{{")
    )


def collect_execution_trust_metrics(*, session_key: str = "") -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        global_counters = (snapshot_global().get("counters") or {})
        out: dict[str, Any] = {}
        for name in _EXECUTION_TRUST_COUNTERS:
            total = _sum_counter_matches(global_counters, name)
            if total:
                out[name] = total

        pin_detail: dict[str, int] = {}
        for key, value in global_counters.items():
            if not key.startswith("execution_pointer_pin{"):
                continue
            if "source=" in key:
                source = key.split("source=", 1)[1].rstrip("}")
                pin_detail[source] = pin_detail.get(source, 0) + int(value)
            else:
                pin_detail[key] = int(value)
        if pin_detail:
            out["execution_pointer_pin_by_source"] = pin_detail

        sk = str(session_key or "").strip()
        if sk:
            sess_counters = (snapshot_session(sk).get("counters") or {})
            sess_out: dict[str, Any] = {}
            for name in _EXECUTION_TRUST_COUNTERS:
                total = _sum_counter_matches(sess_counters, name)
                if total:
                    sess_out[name] = total
            if sess_out:
                out["session"] = sess_out
        return out

    result = safe_best_effort(
        _run,
        label="execution_surface.trust_metrics",
        default={},
    )
    return result if isinstance(result, dict) else {}


def mcp_imports_available() -> bool:
    def _run() -> bool:
        return True

    return safe_best_effort(
        _run,
        label="execution_surface.mcp_imports",
        default=False,
    ) is True


def mcp_enabled_flag() -> bool:
    def _run() -> bool:
        return bool(mcp_enabled_flag())

    return bool(
        safe_best_effort(_run, label="execution_surface.mcp_enabled", default=False)
    )


def default_mcp_config_path() -> Path | None:
    def _run() -> Path:
        return cast(Path, registry_default_mcp_config_path())

    return cast(
        Path | None,
        safe_best_effort(
        _run,
        label="execution_surface.mcp_config_path",
        default=None,
        ),
    )


def experience_merge_pending_count() -> int | None:
    def _run() -> int:
        pending = load_merge_pending()
        return len(pending) if pending else 0

    result = safe_best_effort(
        _run,
        label="execution_surface.experience_merge_pending",
        default=None,
    )
    return result if isinstance(result, int) else None


def recent_skill_dedup_events() -> list[Any] | None:
    def _run() -> list[Any]:
        dedup = recent_dedup_status()
        return dedup[-5:] if dedup else []

    result = safe_best_effort(
        _run,
        label="execution_surface.skill_dedup",
        default=None,
    )
    return result if isinstance(result, list) else None


def digestion_runtime_counters() -> dict[str, int]:
    def _run() -> dict[str, int]:
        counters = (snapshot_global().get("counters") or {})
        out: dict[str, int] = {}
        for key in (
            "digestion_skill_fallback_merge",
            "digestion_experience_merged",
            "digestion_experience_merge_pending",
        ):
            if key in counters:
                out[key] = int(counters[key])
        return out

    result = safe_best_effort(
        _run,
        label="execution_surface.digestion_counters",
        default={},
    )
    return result if isinstance(result, dict) else {}


def builtin_tool_count() -> int | None:
    def _run() -> int:
        return len(get_tool_definitions())

    result = safe_best_effort(
        _run,
        label="execution_surface.builtin_tool_count",
        default=None,
    )
    return result if isinstance(result, int) else None


def tool_orthogonality_warnings() -> list[str]:
    def _run() -> list[str]:
        return lint_tool_orthogonality_for_diagnostics(max_pairs=2) or []

    result = safe_best_effort(
        _run,
        label="execution_surface.tool_orthogonality",
        default=[],
    )
    return result if isinstance(result, list) else []


def collect_digestion_health() -> dict[str, Any]:
    out: dict[str, Any] = {}
    pending = experience_merge_pending_count()
    if pending:
        out["experience_merge_pending"] = pending
    dedup = recent_skill_dedup_events()
    if dedup:
        out["skill_dedup_events"] = dedup
    out.update(digestion_runtime_counters())
    tool_count = builtin_tool_count()
    if tool_count is not None:
        out["builtin_tool_count"] = tool_count
    ortho = tool_orthogonality_warnings()
    if ortho:
        out["tool_orthogonality_warnings"] = ortho
    return out


def skill_injection_mode() -> str | None:
    def _run() -> str:
        return str(registry_skill_injection_mode() or "")

    result = safe_best_effort(
        _run,
        label="execution_surface.skill_injection_mode",
        default=None,
    )
    return result if result else None


def skill_catalog_count(orchestrator: Any) -> int | None:
    def _run() -> int:
        mgr = getattr(orchestrator, "_skill_manager", None)
        if mgr is None:
            return 0
        return len(mgr.list_skills())

    result = safe_best_effort(
        _run,
        label="execution_surface.skill_catalog_count",
        default=None,
    )
    return result if isinstance(result, int) else None


def mcp_surface_flags(
    *,
    session_key: str,
    health_session_key: str,
) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        out: dict[str, Any] = {
            "mcp_enabled": mcp_enabled_flag(),
            "mcp_deferred": mcp_deferred_tools_enabled(),
            "mcp_deferred_same_turn": mcp_deferred_same_turn_enabled(),
            "mcp_config_present": registry_default_mcp_config_path().is_file(),
        }
        if out["mcp_enabled"] and out["mcp_deferred"]:
            sk = str(session_key or health_session_key or "").strip()
            out["mcp_promoted_tools"] = sorted(get_promoted_tools(sk))
        return out

    result = safe_best_effort(
        _run,
        label="execution_surface.mcp_surface",
        default={},
    )
    return result if isinstance(result, dict) else {}


def legacy_global_skills_dir(butler_home: Path) -> Path:
    return Path(butler_home).expanduser().resolve() / "skills"


def check_legacy_global_skills(butler_home: Path) -> list[str]:
    """Warn when pre-tenant ``~/.butler/skills/`` still has files alongside tenant dir."""
    home = Path(butler_home).expanduser().resolve()
    legacy = legacy_global_skills_dir(home)
    if not legacy.is_dir():
        return []
    md_files = sorted(legacy.glob("*.md"))
    if not md_files:
        return []
    tenant_dir = tenant_skills_dir(home, DEFAULT_TENANT)
    names = ", ".join(p.name for p in md_files[:5])
    if len(md_files) > 5:
        names += " …"
    return [
        f"遗留全局 Skill 目录仍有 {len(md_files)} 个文件 ({names})",
        f"  路径: {legacy}",
        f"  建议: 合并到 {tenant_dir} 后删除遗留目录（runtime 不读此路径）",
    ]


def legacy_skill_warnings() -> list[str]:
    def _run() -> list[str]:
        return check_legacy_global_skills(get_butler_home())

    result = safe_best_effort(
        _run,
        label="execution_surface.legacy_skills",
        default=[],
    )
    return result if isinstance(result, list) else []


def current_project(orchestrator: Any, *, session_key: str) -> Any | None:
    def _run() -> Any | None:
        pm = getattr(orchestrator, "project_manager", None)
        if pm is None:
            return None
        return pm.get_current(session_key=session_key or None)

    return safe_best_effort(
        _run,
        label="execution_surface.current_project",
        default=None,
    )


def mcp_diagnostic_lines(session_key: str) -> list[str]:
    def _run() -> list[str]:
        return cast(list[str], format_mcp_diagnostic_lines(session_key))

    result = safe_best_effort(
        _run,
        label="execution_surface.mcp_diagnostic_lines",
        default=[],
    )
    return result if isinstance(result, list) else []


__all__ = [
    "check_legacy_global_skills",
    "collect_digestion_health",
    "collect_execution_trust_metrics",
    "current_project",
    "default_mcp_config_path",
    "digestion_runtime_counters",
    "experience_merge_pending_count",
    "check_legacy_global_skills",
    "legacy_global_skills_dir",
    "legacy_skill_warnings",
    "mcp_diagnostic_lines",
    "mcp_enabled_flag",
    "mcp_imports_available",
    "mcp_surface_flags",
    "recent_skill_dedup_events",
    "skill_catalog_count",
    "skill_injection_mode",
    "tool_orthogonality_warnings",
]
