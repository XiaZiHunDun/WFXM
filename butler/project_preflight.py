"""Project onboarding preflight checks for Butler workspaces."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from butler.project import Project
from butler.project_lead import is_lead_project


class CheckLevel(str, Enum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    INFO = "info"


@dataclass
class PreflightItem:
    level: CheckLevel
    code: str
    message: str
    hint: str = ""


@dataclass
class PreflightReport:
    path: str
    registered: bool = False
    project_name: str = ""
    suggested_template: str = ""
    suggested_tags: list[str] = field(default_factory=list)
    items: list[PreflightItem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.level == CheckLevel.FAIL for i in self.items)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["items"] = [
            {**asdict(i), "level": i.level.value}
            for i in self.items
        ]
        d["ok"] = self.ok
        return d


_CODE_MARKERS = (
    ".git",
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "Makefile",
)
_SCRIPT_MARKERS = ("src", "lib", "app", "novel-factory/tools")


def _detect_pack(workspace: Path) -> str:
    if (workspace / "novel-factory" / "workflow_state.json").is_file():
        return "novel-factory"
    if (workspace / "novel-factory").is_dir():
        return "novel-factory"
    return ""


def _detect_lifecycle(workspace: Path) -> str:
    state = workspace / "novel-factory" / "workflow_state.json"
    if not state.is_file():
        return ""
    try:
        data = yaml.safe_load(state.read_text(encoding="utf-8")) or {}
    except Exception:
        try:
            data = json.loads(state.read_text(encoding="utf-8"))
        except Exception:
            return ""
    phase = str(data.get("phase") or data.get("current_phase") or "").upper()
    if "COMPLETE" in phase:
        return "lifecycle:complete"
    return "lifecycle:active"


def _has_executable_tree(workspace: Path) -> bool:
    for name in _CODE_MARKERS:
        if (workspace / name).exists():
            return True
    for name in _SCRIPT_MARKERS:
        p = workspace / name
        if p.is_dir() and any(p.iterdir()):
            return True
    return False


def _under_root(child: Path, root: Path | None) -> bool:
    if root is None:
        return True
    try:
        child.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _skill_files(workspace: Path) -> tuple[list[Path], bool]:
    """List project skills by basename (git ``skills/`` wins over ``.butler/skills/``)."""
    by_name: dict[str, Path] = {}
    had_dup_dirs = False
    for base in (workspace / "skills", workspace / ".butler" / "skills"):
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*.md")):
            if path.name in by_name and by_name[path.name] != path:
                had_dup_dirs = True
            elif path.name not in by_name:
                by_name[path.name] = path
    return sorted(by_name.values(), key=lambda p: p.name.lower()), had_dup_dirs


def run_preflight(
    workspace: Path,
    *,
    projects_dir: Path | None = None,
    safe_root: Path | None = None,
) -> PreflightReport:
    """Inspect a directory for Butler project onboarding readiness."""
    ws = workspace.expanduser().resolve()
    items: list[PreflightItem] = []
    registered = False
    project_name = ""
    suggested_template = "software-default"
    suggested_tags: list[str] = []

    if not ws.exists():
        items.append(
            PreflightItem(CheckLevel.FAIL, "path_missing", f"路径不存在: {ws}")
        )
        return PreflightReport(path=str(ws), items=items)

    if not ws.is_dir():
        items.append(
            PreflightItem(CheckLevel.FAIL, "not_directory", f"不是目录: {ws}")
        )
        return PreflightReport(path=str(ws), items=items)

    if projects_dir is not None:
        if _under_root(ws, projects_dir):
            items.append(
                PreflightItem(
                    CheckLevel.OK,
                    "under_projects_dir",
                    f"位于项目根下: {projects_dir}",
                )
            )
        else:
            items.append(
                PreflightItem(
                    CheckLevel.WARN,
                    "outside_projects_dir",
                    f"不在 BUTLER_PROJECTS_DIR ({projects_dir}) 下",
                    "登记后 ProjectManager 可能扫不到；请移到该目录或调整 BUTLER_PROJECTS_DIR",
                )
            )

    if safe_root is not None:
        if _under_root(ws, safe_root):
            items.append(
                PreflightItem(
                    CheckLevel.OK,
                    "under_safe_root",
                    f"在 BUTLER_TOOL_SAFE_ROOT 内: {safe_root}",
                )
            )
        else:
            items.append(
                PreflightItem(
                    CheckLevel.WARN,
                    "outside_safe_root",
                    f"不在 BUTLER_TOOL_SAFE_ROOT ({safe_root}) 内",
                    "Agent 工具可能拒绝访问该路径",
                )
            )

    cfg = ws / "project.yaml"
    proj: Project | None = None
    if not cfg.is_file():
        items.append(
            PreflightItem(
                CheckLevel.FAIL,
                "missing_project_yaml",
                "缺少 project.yaml",
                "从 docs/templates/project-archetypes/ 复制模板后改名写入",
            )
        )
    else:
        try:
            proj = Project.from_yaml(cfg)
            project_name = proj.name
            items.append(
                PreflightItem(
                    CheckLevel.OK,
                    "project_yaml",
                    f"project.yaml 可读，name={proj.name!r} type={proj.type!r}",
                )
            )
            if proj.tools:
                items.append(
                    PreflightItem(
                        CheckLevel.OK,
                        "tools",
                        f"tools 已配置 {len(proj.tools)} 项",
                    )
                )
            else:
                items.append(
                    PreflightItem(
                        CheckLevel.WARN,
                        "tools_empty",
                        "tools 列表为空",
                        "按模板补全 read/write/patch 或只读集",
                    )
                )
        except Exception as exc:
            items.append(
                PreflightItem(
                    CheckLevel.FAIL,
                    "project_yaml_invalid",
                    f"project.yaml 解析失败: {exc}",
                )
            )

    if ws.name != (project_name or ws.name) and project_name:
        items.append(
            PreflightItem(
                CheckLevel.INFO,
                "dir_vs_name",
                f"目录名 {ws.name!r} 与 name {project_name!r} 不同（微信 /切换 用 name）",
            )
        )

    try:
        from butler.project_manager import get_project_manager

        pm = get_project_manager()
        if project_name and pm.get_project(project_name) is not None:
            registered = True
            items.append(
                PreflightItem(
                    CheckLevel.OK,
                    "registered",
                    f"已在 ProjectManager 注册: {project_name!r}",
                )
            )
        elif cfg.is_file() and project_name:
            items.append(
                PreflightItem(
                    CheckLevel.WARN,
                    "not_registered",
                    "有 project.yaml 但当前进程未加载（路径不在 projects_dir？）",
                    "确认 BUTLER_PROJECTS_DIR 或重启 butler gateway",
                )
            )
    except Exception:
        pass

    pack = _detect_pack(ws)
    lifecycle = _detect_lifecycle(ws)
    has_code = _has_executable_tree(ws)

    if pack:
        suggested_template = "novel-factory"
        suggested_tags.append(f"pack:{pack}")
    elif has_code:
        suggested_template = "software-default"
    else:
        suggested_template = "knowledge-light"
        suggested_tags.append("profile:knowledge-light")

    if lifecycle:
        suggested_tags.append(lifecycle)

    if has_code:
        items.append(
            PreflightItem(
                CheckLevel.OK,
                "executable_tree",
                "检测到可开发/可执行树（仓库或脚本目录）",
            )
        )
    else:
        items.append(
            PreflightItem(
                CheckLevel.WARN,
                "no_executable_tree",
                "未发现典型代码/脚本入口",
                "若仅文档仓可收紧 tools；否则补仓库或脚本后再登记",
            )
        )

    if pack:
        items.append(
            PreflightItem(
                CheckLevel.INFO,
                "pack_detected",
                f"建议能力包: {pack}",
            )
        )
    if lifecycle:
        items.append(
            PreflightItem(
                CheckLevel.INFO,
                "lifecycle_detected",
                f"运营态建议: {lifecycle}",
            )
        )

    mem = ws / ".butler" / "memory" / "MEMORY.md"
    if mem.is_file():
        items.append(
            PreflightItem(CheckLevel.OK, "memory", "已有 .butler/memory/MEMORY.md")
        )
    else:
        items.append(
            PreflightItem(
                CheckLevel.WARN,
                "memory_missing",
                "缺少 .butler/memory/MEMORY.md",
                "登记后执行 butler memory-reindex --project <name>",
            )
        )

    pilot = ws / "docs" / "pilot-setup.md"
    if pilot.is_file():
        items.append(
            PreflightItem(CheckLevel.OK, "pilot_setup", "已有 docs/pilot-setup.md")
        )
    else:
        items.append(
            PreflightItem(
                CheckLevel.WARN,
                "pilot_setup_missing",
                "缺少 docs/pilot-setup.md",
                "建议写运营说明、路径边界与微信验收顺序",
            )
        )

    jobs = ws / "runtime" / "jobs.yaml"
    if jobs.is_file():
        items.append(
            PreflightItem(CheckLevel.OK, "runtime_jobs", "已有 runtime/jobs.yaml")
        )
    else:
        items.append(
            PreflightItem(
                CheckLevel.INFO,
                "runtime_jobs_missing",
                "无 runtime/jobs.yaml（测试/巡检需时再建）",
            )
        )

    skills, skills_dup_dirs = _skill_files(ws)
    if skills:
        hint = ""
        if skills_dup_dirs and (ws / "skills").is_dir() and (ws / ".butler" / "skills").is_dir():
            hint = "skills/ 与 .butler/skills/ 同名文件已去重；改 git 源后请 sync 脚本同步"
        items.append(
            PreflightItem(
                CheckLevel.OK,
                "skills",
                f"发现项目 Skill: {', '.join(p.name for p in skills[:5])}"
                + (" …" if len(skills) > 5 else ""),
                hint,
            )
        )
    elif project_name and is_lead_project(project_name, project=proj):
        items.append(
            PreflightItem(
                CheckLevel.WARN,
                "skills_missing_lead",
                f"{project_name!r} 为 Lead 项目但无 skills/*.md",
                "运行 sync 脚本或复制 *-project-lead.md 到 skills/",
            )
        )

    if project_name and is_lead_project(project_name, project=proj):
        from butler.project_lead import lead_project_names

        src = []
        if proj and proj.lead is True:
            src.append("project.yaml lead:true")
        if project_name in lead_project_names():
            src.append("BUTLER_LEAD_PROJECTS")
        if proj and (proj.pack or "") == "novel-factory":
            src.append("pack:novel-factory")
        hint = ", ".join(src) if src else "Lead"
        items.append(
            PreflightItem(
                CheckLevel.OK,
                "lead_enabled",
                f"厂长模式已启用（{hint}）",
            )
        )
    elif pack or (proj and proj.type == "content"):
        items.append(
            PreflightItem(
                CheckLevel.INFO,
                "lead_optional",
                "未在 BUTLER_LEAD_PROJECTS 中；复杂项目可加入以启用厂长模式",
            )
        )

    items.append(
        PreflightItem(
            CheckLevel.INFO,
            "suggested_template",
            f"建议模板: {suggested_template}",
            "见 docs/templates/project-archetypes/",
        )
    )

    return PreflightReport(
        path=str(ws),
        registered=registered,
        project_name=project_name,
        suggested_template=suggested_template,
        suggested_tags=suggested_tags,
        items=items,
    )


def format_report(report: PreflightReport) -> str:
    """Human-readable preflight output."""
    lines = [f"Preflight: {report.path}"]
    if report.project_name:
        lines.append(f"  项目名: {report.project_name}")
    lines.append(
        f"  已注册: {'是' if report.registered else '否'}"
        f"  模板建议: {report.suggested_template}"
    )
    if report.suggested_tags:
        lines.append(f"  标签建议: {', '.join(report.suggested_tags)}")
    lines.append("")
    for item in report.items:
        tag = item.level.value.upper()
        line = f"  [{tag}] {item.message}"
        if item.hint:
            line += f"\n         → {item.hint}"
        lines.append(line)
    lines.append("")
    lines.append("通过" if report.ok else "未通过（存在 FAIL）")
    return "\n".join(lines)


def resolve_workspace(
    *,
    path: str = "",
    project_name: str = "",
    projects_dir: Path | None = None,
) -> Path | None:
    """Resolve workspace from --path or registered --project name."""
    if path.strip():
        return Path(path.strip())
    if project_name.strip():
        from butler.project_manager import get_project_manager

        proj = get_project_manager().get_project(project_name.strip())
        if proj is None:
            matched = get_project_manager().resolve_project_name(project_name.strip())
            if matched:
                proj = get_project_manager().get_project(matched)
        if proj is not None:
            return proj.workspace
    if projects_dir is not None:
        return projects_dir
    return None


__all__ = [
    "CheckLevel",
    "PreflightItem",
    "PreflightReport",
    "format_report",
    "resolve_workspace",
    "run_preflight",
]
