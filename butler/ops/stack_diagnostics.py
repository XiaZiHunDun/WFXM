"""Project ``stack.yaml`` health checks for ``/诊断``."""

from __future__ import annotations

import importlib.util
import logging
import os
import socket
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

logger = logging.getLogger(__name__)

_EXTRA_IMPORTS: dict[str, str] = {
    "wechat": "aiohttp",
    "mcp": "mcp",
    "embeddings": "fastembed",
    "vectors": "chromadb",
    "web": "trafilatura",
}


def _load_stack(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.debug("stack.yaml load failed %s: %s", path, exc)
        return None


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
    try:
        from butler.registry.paths import skills_root

        tenant_root = skills_root(tenant_id=tenant_id)
        if (tenant_root / f"{skill_name}.md").is_file():
            return True
        if (tenant_root / skill_name / "SKILL.md").is_file():
            return True
    except Exception as exc:
        logger.debug("skill disk check failed %s: %s", skill_name, exc)
    return False


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
    try:
        from butler.config import load_settings

        return load_settings().default_tenant
    except Exception:
        return "default"


def collect_stack_health(workspace: Path | str | None) -> dict[str, Any]:
    """Read ``<workspace>/stack.yaml`` and probe local deps (read-only)."""
    out: dict[str, Any] = {"found": False, "path": "", "checks": [], "warnings": [], "ok": True}
    if not workspace:
        return out
    ws = Path(workspace).expanduser().resolve()
    stack_path = ws / "stack.yaml"
    out["path"] = str(stack_path)
    data = _load_stack(stack_path)
    if not data:
        return out
    out["found"] = True
    out["project"] = str(data.get("project") or "")
    out["version"] = data.get("version")

    py = data.get("python_extras") if isinstance(data.get("python_extras"), dict) else {}
    for extra in py.get("includes") or []:
        mod = _EXTRA_IMPORTS.get(str(extra))
        if not mod:
            continue
        if _module_installed(mod):
            out["checks"].append(f"extra:{extra}=ok")
        else:
            out["warnings"].append(f"缺 pip extra [{extra}]（import {mod} 失败）")
            out["ok"] = False

    deploy_profile = str(data.get("deploy_profile") or py.get("install") or "").strip()
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

    for api in data.get("apis") or []:
        if not isinstance(api, dict):
            continue
        api_id = str(api.get("id") or "").strip()
        envs = api.get("env") if isinstance(api.get("env"), list) else []
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

    proc_env = data.get("process_env") if isinstance(data.get("process_env"), dict) else {}
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

    for host in data.get("host") or []:
        if not isinstance(host, dict):
            continue
        if str(host.get("name") or "") == "http-proxy":
            ep = str(host.get("endpoint") or "")
            if ep and not _proxy_endpoint_ok(ep):
                out["warnings"].append(f"代理 {ep} 不可达")
                out["ok"] = False
            elif ep:
                out["checks"].append("proxy:listen=ok")

    env_rec = data.get("env_recommended") if isinstance(data.get("env_recommended"), dict) else {}
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

    skills = data.get("skills") if isinstance(data.get("skills"), dict) else {}
    tenant_id = _tenant_id_default()
    try:
        from butler.registry.skill_lock import SkillLockFile

        lock_by_name = {rec.name: rec for rec in SkillLockFile(tenant_id=tenant_id).list_installed()}
    except Exception:
        lock_by_name = {}

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
        try:
            from butler.registry.marketplace_compat import check_directory_skill_layout

            for name in directory_skills:
                ok_layout, detail = check_directory_skill_layout(
                    str(name), workspace=ws, tenant_id=tenant_id
                )
                if ok_layout:
                    out["checks"].append(f"skill:{name}:directory={detail}")
                elif detail == "missing":
                    pass
                elif detail == "flat":
                    out["warnings"].append(
                        f"skill [{name}] 为单文件安装，建议 "
                        f"`butler skills upgrade {name}` 后 "
                        f"`butler skills sync --project {ws}`"
                    )
                    out["ok"] = False
                else:
                    out["warnings"].append(f"skill [{name}] 目录布局异常: {detail}")
                    out["ok"] = False
        except Exception as exc:
            logger.debug("directory skill layout check failed: %s", exc)

    adoption = data.get("plugin_adoption") if isinstance(data.get("plugin_adoption"), dict) else {}
    if adoption:
        try:
            from butler.registry.marketplace_compat import format_adoption_lines

            for line in format_adoption_lines(adoption):
                out["checks"].append(f"adoption:{line}")
            suggested = adoption.get("mcp_suggested")
            if not isinstance(suggested, list):
                adopted = adoption.get("adopted")
                if isinstance(adopted, dict):
                    suggested = adopted.get("mcp")
            if isinstance(suggested, list):
                from butler.registry.marketplace_compat import missing_mcp_suggestions

                for warn in missing_mcp_suggestions(adoption):
                    out["warnings"].append(warn)
        except Exception as exc:
            logger.debug("plugin_adoption check failed: %s", exc)

    ingest = data.get("ingest_pilot_dirs") or []
    if ingest:
        missing = [d for d in ingest if not (ws / str(d)).is_dir()]
        if missing:
            out["warnings"].append(f"EXT-3 试点目录缺失: {', '.join(missing)}")
        else:
            out["checks"].append("ingest_dirs=ok")
        try:
            from butler.memory.document_ingest import ingest_stats

            stats = ingest_stats(ws)
            if stats.get("enabled"):
                out["checks"].append(f"ingest:enabled md={stats.get('md_files', 0)}")
            elif stats.get("md_files", 0) > 0:
                out["checks"].append(f"ingest:cache md={stats.get('md_files', 0)}")
            else:
                out["warnings"].append(
                    "EXT-3 未启用（BUTLER_INGEST_ENABLED=0）且无 ingest 缓存；"
                    "参考书需 butler memory ingest"
                )
        except Exception as exc:
            logger.debug("ingest stats check failed: %s", exc)

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
