"""Project ``stack.yaml`` health checks for ``/诊断``."""

from __future__ import annotations

import importlib.util
import logging
import os
import socket
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_EXTRA_IMPORTS: dict[str, str] = {
    "wechat": "aiohttp",
    "mcp": "mcp",
    "embeddings": "fastembed",
    "vectors": "chromadb",
    "web": "trafilatura",
}


def _load_stack(path: Path) -> dict[str, Any] | None:
    from butler.ops.stack_diagnostics_ops import load_stack_safe

    return cast(dict[str, Any] | None, load_stack_safe(path))


def _env_matches(name: str, expected: str) -> bool:
    got = os.environ.get(name)
    if got is None:
        return False
    return str(got).strip() == str(expected).strip()


def _env_truthy(name: str, expected: str) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return str(expected).strip().lower() in ("0", "false", "no", "off", "")
    return str(raw).strip().lower() == str(expected).strip().lower()


def _proxy_endpoint_ok(endpoint: str) -> bool:
    try:
        parsed = urlparse(endpoint.strip())
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 7890
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


def _module_installed(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _skill_stub_on_disk(name: str, *, workspace: Path, tenant_id: str = "default") -> bool:
    """True only when a skill stub or orphan directory exists on disk."""
    from butler.ops.stack_diagnostics_ops import tenant_skill_paths_safe

    skill_name = str(name).strip()
    if not skill_name:
        return False
    proj_root = workspace / ".butler" / "skills"
    proj_stub = proj_root / f"{skill_name}.md"
    if proj_stub.is_file():
        return True
    proj_orphan = proj_root / skill_name / "SKILL.md"
    if proj_orphan.is_file():
        return True
    return bool(tenant_skill_paths_safe(skill_name, tenant_id=tenant_id))


def _skill_present(name: str, *, workspace: Path, tenant_id: str = "default") -> bool:
    return _skill_stub_on_disk(name, workspace=workspace, tenant_id=tenant_id)


def _env_any_set(names: list[str]) -> bool:
    return any(str(os.environ.get(str(n) or "", "")).strip() for n in names)


def _marketplace_skill_name(identifier: str) -> str:
    ident = str(identifier).strip()
    for prefix in ("marketplace:", "claude-marketplace:", "claude:"):
        if ident.startswith(prefix):
            ident = ident[len(prefix) :]
            break
    if "/" not in ident:
        return ident.strip().lower()
    return ident.split("/", 1)[1].strip().lower()


def _tenant_id_default() -> str:
    from butler.ops.stack_diagnostics_ops import tenant_id_default_safe

    return str(tenant_id_default_safe())


def collect_stack_health(workspace: Path | str | None) -> dict[str, Any]:
    """Read ``<workspace>/stack.yaml`` and probe local deps (read-only)."""
    from butler.ops.stack_diagnostics_ops import (
        check_directory_skill_layouts_safe,
        check_ingest_stats_safe,
        check_plugin_adoption_safe,
        skill_lock_by_name_safe,
    )

    out: dict[str, Any] = {"found": False, "path": "", "checks": [], "warnings": [], "ok": True}
    if not workspace:
        return out
    ws = Path(workspace).expanduser().resolve()
    stack_path = ws / "stack.yaml"
    out["path"] = str(stack_path)
    data = _load_stack(stack_path)
    if not data:
        return out
    stack: dict[str, Any] = data
    out["found"] = True
    out["project"] = str(stack.get("project") or "")
    out["version"] = stack.get("version")

    py_raw = stack.get("python_extras")
    py: dict[str, Any] = py_raw if isinstance(py_raw, dict) else {}
    for extra in py.get("includes") or []:
        mod = _EXTRA_IMPORTS.get(str(extra))
        if not mod:
            continue
        if _module_installed(mod):
            out["checks"].append(f"extra:{extra}=ok")
        else:
            out["warnings"].append(f"缺 pip extra [{extra}]（import {mod} 失败）")
            out["ok"] = False

    deploy_profile = str(stack.get("deploy_profile") or py.get("install") or "").strip()
    if deploy_profile:
        env_profile = os.getenv("BUTLER_DEPLOY_PROFILE", "").strip()
        extras_ok = all(
            _module_installed(_EXTRA_IMPORTS[str(e)])
            for e in (py.get("includes") or [])
            if str(e) in _EXTRA_IMPORTS
        )
        if env_profile and env_profile != deploy_profile:
            out["warnings"].append(
                f"deploy_profile 期望 {deploy_profile}，BUTLER_DEPLOY_PROFILE={env_profile}"
            )
            out["ok"] = False
        elif extras_ok:
            label = deploy_profile if not env_profile or env_profile == deploy_profile else env_profile
            out["checks"].append(f"deploy_profile:{label}=ok")
        else:
            out["warnings"].append(f"deploy_profile:{deploy_profile} 但 pip extra 未齐")
            out["ok"] = False

    for api in stack.get("apis") or []:
        if not isinstance(api, dict):
            continue
        api_id = str(api.get("id") or "").strip()
        env_raw = api.get("env")
        envs: list[Any] = env_raw if isinstance(env_raw, list) else []
        env_names = [str(e).strip() for e in envs if str(e).strip()]
        if not api_id or not env_names:
            continue
        required = bool(api.get("required"))
        if not required and not api.get("required_for"):
            continue
        if _env_any_set(env_names):
            out["checks"].append(f"api:{api_id}=ok")
        else:
            out["warnings"].append(f"缺 API [{api_id}] 环境变量（{' / '.join(env_names)}）")
            out["ok"] = False

    proc_env_raw = stack.get("process_env")
    proc_env: dict[str, Any] = proc_env_raw if isinstance(proc_env_raw, dict) else {}
    for key, want in proc_env.items():
        key_s = str(key)
        want_s = str(want)
        if _env_matches(key_s, want_s):
            out["checks"].append(f"{key_s}=ok")
        elif os.environ.get(key_s):
            out["warnings"].append(f"{key_s} 期望 {want_s}，当前 {os.environ.get(key_s)}")
            out["ok"] = False
        else:
            out["warnings"].append(f"未设 {key_s}（stack process_env）")
            out["ok"] = False

    for host in stack.get("host") or []:
        if not isinstance(host, dict):
            continue
        if str(host.get("name") or "") == "http-proxy":
            ep = str(host.get("endpoint") or "")
            if ep and not _proxy_endpoint_ok(ep):
                out["warnings"].append(f"代理 {ep} 不可达")
                out["ok"] = False
            elif ep:
                out["checks"].append("proxy:listen=ok")

    env_rec_raw = stack.get("env_recommended")
    env_rec: dict[str, Any] = env_rec_raw if isinstance(env_rec_raw, dict) else {}
    for key, want in env_rec.items():
        key_s = str(key)
        if not key_s.startswith("BUTLER_"):
            continue
        if _env_truthy(key_s, str(want)):
            out["checks"].append(f"{key_s}=ok")
        else:
            got = os.environ.get(key_s, "(unset)")
            out["warnings"].append(f"{key_s} 期望 {want}，当前 {got}")
            out["ok"] = False

    skills_raw = stack.get("skills")
    skills: dict[str, Any] = skills_raw if isinstance(skills_raw, dict) else {}
    tenant_id = _tenant_id_default()
    lock_by_name = skill_lock_by_name_safe(tenant_id)

    for ident in skills.get("marketplace_install") or []:
        ident_s = str(ident).strip()
        if not ident_s:
            continue
        skill_name = _marketplace_skill_name(ident_s)
        rec = lock_by_name.get(skill_name)
        if rec is None:
            out["warnings"].append(f"marketplace 未安装 [{ident_s}]")
            out["ok"] = False
        elif rec.identifier != ident_s:
            out["warnings"].append(
                f"lockfile [{skill_name}] identifier 期望 {ident_s}，实际 {rec.identifier}"
            )
            out["ok"] = False
        else:
            out["checks"].append(f"marketplace_lock:{skill_name}=ok")

    for name in skills.get("skills_expected") or []:
        if _skill_present(str(name), workspace=ws, tenant_id=tenant_id):
            out["checks"].append(f"skill:{name}=ok")
        else:
            out["warnings"].append(f"缺 skill [{name}]（.butler/skills 或租户目录无文件）")
            out["ok"] = False

    directory_skills = skills.get("directory_skills") or []
    if isinstance(directory_skills, list) and directory_skills:
        check_directory_skill_layouts_safe(
            directory_skills,
            workspace=ws,
            tenant_id=tenant_id,
            out=out,
        )

    adoption_raw = stack.get("plugin_adoption")
    adoption: dict[str, Any] = adoption_raw if isinstance(adoption_raw, dict) else {}
    if adoption:
        check_plugin_adoption_safe(adoption, out)

    ingest = stack.get("ingest_pilot_dirs") or []
    if ingest:
        missing = [d for d in ingest if not (ws / str(d)).is_dir()]
        if missing:
            out["warnings"].append(f"EXT-3 试点目录缺失: {', '.join(missing)}")
        else:
            out["checks"].append("ingest_dirs=ok")
        check_ingest_stats_safe(ws, out)

    return out


def format_stack_diagnostic_lines(workspace: Path | str | None) -> list[str]:
    stats = collect_stack_health(workspace)
    if not stats.get("found"):
        return []
    lines = ["项目 stack（依赖清单）:"]
    proj = str(stats.get("project") or "").strip()
    if proj:
        lines.append(f"  项目: {proj}")
    ver = stats.get("version")
    if ver:
        lines.append(f"  schema: v{ver}")
    status = "ok" if stats.get("ok") else "warn"
    lines.append(f"  状态: {status}")
    for item in stats.get("checks") or []:
        lines.append(f"  ✓ {item}")
    for item in stats.get("warnings") or []:
        lines.append(f"  ⚠ {item}")
    return lines


__all__ = ["collect_stack_health", "format_stack_diagnostic_lines"]
