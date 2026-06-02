"""WeChat slash commands for dev-tool visibility, git, test, and project dashboard."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from butler.gateway.owner_gate import is_gateway_owner, owner_required_message

logger = logging.getLogger(__name__)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _env_on(name: str) -> bool:
    from butler.env_parse import env_truthy

    return env_truthy(name)


def _get_active_project() -> Any:
    """Return the active Project or None."""
    try:
        from butler.gateway.message_handler import GatewayMessageHandler
        handler = GatewayMessageHandler._instance  # type: ignore[attr-defined]
        if handler and hasattr(handler, "_orchestrator"):
            return handler._orchestrator.project_manager.active_project
    except Exception as exc:
        logger.debug("get active project skipped: %s", exc)
    try:
        from butler.project.manager import ProjectManager
        pm = ProjectManager()
        return pm.active_project
    except Exception:
        return None


def _project_workspace() -> Path | None:
    proj = _get_active_project()
    if proj and hasattr(proj, "workspace"):
        ws = Path(proj.workspace)
        if ws.is_dir():
            return ws
    return None


def _project_dev_config() -> dict[str, Any]:
    proj = _get_active_project()
    if proj and hasattr(proj, "dev"):
        return dict(proj.dev or {})
    return {}


def format_dev_status() -> str:
    lines = [
        "开发工具状态（当前网关进程环境）",
        f"  BUTLER_ENABLE_TERMINAL={os.getenv('BUTLER_ENABLE_TERMINAL', '0')}",
        f"  BUTLER_TERMINAL_PROFILE={os.getenv('BUTLER_TERMINAL_PROFILE', '(默认)')}",
        f"  BUTLER_ENABLE_GIT={os.getenv('BUTLER_ENABLE_GIT', '0')}",
        f"  BUTLER_ENABLE_GIT_WRITE={os.getenv('BUTLER_ENABLE_GIT_WRITE', '0')}",
        f"  BUTLER_TOOL_SAFE_ROOT={os.getenv('BUTLER_TOOL_SAFE_ROOT', '(未设)')}",
        f"  BUTLER_WECHAT_DEV_SMOKE={os.getenv('BUTLER_WECHAT_DEV_SMOKE', '0')}",
        "",
        "生产微信建议: GIT_WRITE=0；本机验收可开 GIT_WRITE=1。",
        "跑守门测试: 设 BUTLER_WECHAT_DEV_SMOKE=1 后发送 /开发验收",
        "或 SSH: bash scripts/butler-dev-delegate-smoke.sh",
    ]
    return "\n".join(lines)


def run_dev_smoke(*, timeout_seconds: int = 180) -> str:
    if not _env_on("BUTLER_WECHAT_DEV_SMOKE"):
        return (
            "未启用微信开发验收（BUTLER_WECHAT_DEV_SMOKE=0）。\n"
            "在 .env 设 BUTLER_WECHAT_DEV_SMOKE=1 并重启网关后重试，"
            "或在本机执行: bash scripts/butler-dev-delegate-smoke.sh"
        )
    root = _repo_root()
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{root}:{env.get('PYTHONPATH', '')}"
    env.setdefault("BUTLER_ENABLE_TERMINAL", "1")
    env.setdefault("BUTLER_TERMINAL_PROFILE", "dev")
    env.setdefault("BUTLER_ENABLE_GIT", "1")
    env.setdefault("BUTLER_ENABLE_GIT_WRITE", "1")
    try:
        proc = subprocess.run(
            [
                "python3",
                "-m",
                "pytest",
                "tests/test_dev_tools_integration.py",
                "-q",
                "--tb=line",
            ],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            timeout=max(30, timeout_seconds),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"开发验收超时（>{timeout_seconds}s）"
    except OSError as exc:
        return f"开发验收启动失败: {exc}"

    tail = (proc.stdout or "")[-800:] + (proc.stderr or "")[-400:]
    if proc.returncode == 0:
        return "开发验收通过（test_dev_tools_integration）。\n" + tail.strip()
    return (
        f"开发验收失败 exit={proc.returncode}。\n"
        + tail.strip()
        + "\n\n详见 logs 或本机 butler-dev-delegate-smoke.sh"
    )


# ── /git command ───────────────────────────────────────────────


def format_git_for_wechat(arg: str = "") -> str:
    from butler.tools.git_tools import git_read_enabled

    if not git_read_enabled():
        return "Git 未启用 (BUTLER_ENABLE_GIT=0)"

    ws = _project_workspace()
    workdir = str(ws) if ws else None
    arg = (arg or "").strip()

    if arg.startswith("diff"):
        return _format_git_diff(workdir)
    if arg.startswith("log"):
        parts = arg.split(maxsplit=1)
        n = 10
        if len(parts) > 1:
            try:
                n = int(parts[1])
            except ValueError:
                pass
        return _format_git_log(workdir, count=n)

    return _format_git_status(workdir)


def _format_git_status(workdir: str | None) -> str:
    from butler.tools.git_tools import _run_git

    status = _run_git(["status", "--short", "--branch"], workdir=workdir)
    if status.get("exit_code", -1) != 0:
        err = status.get("stderr") or status.get("error", "git 不可用")
        return f"Git 错误: {err}"

    stdout = status.get("stdout", "").strip()
    lines = stdout.split("\n")

    branch_line = lines[0] if lines else ""
    branch = branch_line.replace("## ", "").split("...")[0] if branch_line.startswith("##") else "unknown"
    changes = [line for line in lines[1:] if line.strip()]

    log = _run_git(["log", "-5", "--format=%h %ar %s"], workdir=workdir)
    commits = (log.get("stdout") or "").strip().split("\n") if log.get("exit_code") == 0 else []
    commits = [c for c in commits if c.strip()]

    result = [f"🔀 Git 状态  [{branch}]\n"]

    if changes:
        staged = [line for line in changes if line[0] in "MADRC"]
        unstaged = [line for line in changes if line[0] == " " or line[0] == "?"]
        if staged:
            result.append(f"📦 已暂存: {len(staged)} 个文件")
        if unstaged:
            result.append(f"📝 未暂存: {len(unstaged)} 个文件")
        result.append("")
        for c in changes[:15]:
            flag = c[:2]
            fname = c[3:]
            icon = {"M": "✏️", "A": "➕", "D": "➖", "R": "🔄", "?": "❓"}.get(flag.strip(), "·")
            result.append(f"  {icon} {fname}")
        if len(changes) > 15:
            result.append(f"  ... 还有 {len(changes) - 15} 个")
    else:
        result.append("✅ 工作区干净")

    if commits:
        result.append("\n📝 最近提交:")
        for c in commits[:5]:
            result.append(f"  · {c}")

    result.append("\n/git diff  查看变更详情  |  /git log  查看历史")
    return "\n".join(result)


def _format_git_diff(workdir: str | None) -> str:
    from butler.tools.git_tools import _run_git

    stat = _run_git(["diff", "--stat"], workdir=workdir)
    if stat.get("exit_code", -1) != 0:
        return f"Git diff 错误: {stat.get('error', 'unknown')}"

    stdout = (stat.get("stdout") or "").strip()
    if not stdout:
        cached = _run_git(["diff", "--cached", "--stat"], workdir=workdir)
        cached_out = (cached.get("stdout") or "").strip()
        if cached_out:
            return f"📊 Git Diff (已暂存)\n\n{cached_out}\n\n/git  返回状态"
        return "📊 无变更 (工作区和暂存区都干净)\n\n/git  返回状态"

    return f"📊 Git Diff (未暂存)\n\n{stdout}\n\n/git  返回状态"


def _format_git_log(workdir: str | None, *, count: int = 10) -> str:
    from butler.tools.git_tools import _run_git

    count = max(1, min(count, 50))
    log = _run_git(["log", f"-{count}", "--format=%h | %ar | %an | %s"], workdir=workdir)
    if log.get("exit_code", -1) != 0:
        return f"Git log 错误: {log.get('error', 'unknown')}"

    stdout = (log.get("stdout") or "").strip()
    if not stdout:
        return "📝 暂无提交记录"

    lines = stdout.split("\n")
    result = [f"📝 最近 {len(lines)} 条提交\n"]
    for line in lines:
        result.append(f"  · {line}")
    result.append(f"\n/git  返回状态  |  /git log {count * 2}  查看更多")
    return "\n".join(result)


# ── /测试 command ──────────────────────────────────────────────


def format_test_for_wechat(arg: str = "") -> str:
    if not _env_on("BUTLER_ENABLE_TERMINAL"):
        return "终端未启用 (BUTLER_ENABLE_TERMINAL=0)\n需设置后才能执行测试"

    ws = _project_workspace()
    if not ws:
        return "无活跃项目，请先 /切换 到目标项目"

    dev = _project_dev_config()
    test_cmd = dev.get("test_command", "").strip()

    if arg.strip() == "历史" or arg.strip() == "history":
        return _format_test_history(ws)

    if not test_cmd:
        return (
            "项目未配置 test_command\n"
            "请在 project.yaml 添加:\n"
            "dev:\n  test_command: \"pytest -q tests/\""
        )

    return _run_project_command(ws, test_cmd, label="测试")


def _run_project_command(ws: Path, cmd: str, *, label: str = "命令") -> str:
    from butler.tools.path_safety import safe_subprocess_env

    argv = cmd.split()
    start = time.time()
    try:
        proc = subprocess.run(
            argv,
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=120,
            env={**safe_subprocess_env(), "PYTHONPATH": str(_repo_root())},
        )
    except subprocess.TimeoutExpired:
        return f"⏰ {label}超时 (>120s)"
    except FileNotFoundError:
        return f"❌ 命令不可用: {argv[0]}"
    except OSError as exc:
        return f"❌ {label}失败: {exc}"

    elapsed = time.time() - start
    stdout = (proc.stdout or "")[-2000:]
    stderr = (proc.stderr or "")[-500:]

    if proc.returncode == 0:
        result = f"✅ {label}通过 ({elapsed:.1f}s)\n\n{stdout.strip()}"
    else:
        result = f"❌ {label}失败 (exit={proc.returncode}, {elapsed:.1f}s)\n\n{stdout.strip()}"
        if stderr.strip():
            result += f"\n\n--- stderr ---\n{stderr.strip()}"

    _save_test_result(ws, label, proc.returncode, elapsed, stdout)
    return result[:3000]


def _save_test_result(ws: Path, label: str, exit_code: int, elapsed: float, output: str) -> None:
    history_path = ws / ".butler" / "test_history.json"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.is_file() else []
    except (json.JSONDecodeError, OSError):
        history = []

    passed = failed = 0
    for line in output.split("\n"):
        if "passed" in line and ("failed" in line or "error" in line or line.strip().endswith("passed")):
            import re
            m_p = re.search(r"(\d+)\s+passed", line)
            m_f = re.search(r"(\d+)\s+(?:failed|error)", line)
            if m_p:
                passed = int(m_p.group(1))
            if m_f:
                failed = int(m_f.group(1))

    history.append({
        "label": label,
        "exit_code": exit_code,
        "elapsed": round(elapsed, 1),
        "passed": passed,
        "failed": failed,
        "timestamp": time.time(),
    })
    history = history[-20:]
    try:
        history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _format_test_history(ws: Path) -> str:
    history_path = ws / ".butler" / "test_history.json"
    if not history_path.is_file():
        return "📋 暂无测试记录\n\n运行 /测试 执行首次测试"

    try:
        history = json.loads(history_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "📋 测试记录读取失败"

    if not history:
        return "📋 暂无测试记录"

    from datetime import datetime, timedelta, timezone
    cn_tz = timezone(timedelta(hours=8))

    lines = [f"📋 测试历史 (最近 {len(history)} 次)\n"]
    for r in reversed(history[-10:]):
        ts = datetime.fromtimestamp(r.get("timestamp", 0), tz=cn_tz).strftime("%m-%d %H:%M")
        icon = "✅" if r.get("exit_code") == 0 else "❌"
        info = f"{r.get('passed', 0)}通过"
        if r.get("failed", 0):
            info += f" {r['failed']}失败"
        lines.append(f"  {icon} {ts}  {info}  ({r.get('elapsed', 0)}s)")
    lines.append("\n/测试  重新运行")
    return "\n".join(lines)


# ── /构建 command ──────────────────────────────────────────────


def format_build_for_wechat(arg: str = "") -> str:
    if not _env_on("BUTLER_ENABLE_TERMINAL"):
        return "终端未启用 (BUTLER_ENABLE_TERMINAL=0)"

    ws = _project_workspace()
    if not ws:
        return "无活跃项目，请先 /切换 到目标项目"

    dev = _project_dev_config()
    build_cmd = dev.get("build_command", "").strip()

    if not build_cmd:
        return (
            "项目未配置 build_command\n"
            "请在 project.yaml 添加:\n"
            "dev:\n  build_command: \"python -m py_compile main.py\""
        )

    return _run_project_command(ws, build_cmd, label="构建")


# ── /项目概况 command ──────────────────────────────────────────


def format_project_dashboard(arg: str = "") -> str:
    proj = _get_active_project()
    if not proj:
        return "无活跃项目，请先 /切换 到目标项目"

    ws = Path(proj.workspace) if hasattr(proj, "workspace") else None
    if not ws or not ws.is_dir():
        return f"项目 {proj.name} 的工作区不可用"

    lines = [f"📊 {proj.name} · 项目概况\n"]

    dev = dict(proj.dev or {}) if hasattr(proj, "dev") else {}
    source_dirs = dev.get("source_dirs", [])

    file_count = _count_files(ws, source_dirs)
    if file_count is not None:
        lines.append(f"📁 文件: {file_count} 个")

    _append_git_summary(lines, ws)
    _append_todos_summary(lines, ws)
    _append_runtime_summary(lines, ws)
    _append_memory_summary(lines, ws)

    if dev.get("test_command"):
        lines.append(f"\n🔧 测试命令: {dev['test_command']}")

    lines.append("\n/git  代码状态  |  /测试  运行测试  |  /项目待办  查看待办")
    return "\n".join(lines)


def _count_files(ws: Path, source_dirs: list[str]) -> int | None:
    try:
        if source_dirs:
            total = 0
            for sd in source_dirs:
                d = ws / sd
                if d.is_dir():
                    total += sum(1 for _ in d.rglob("*") if _.is_file())
            return total
        return sum(1 for _ in ws.rglob("*.py") if _.is_file() and ".butler" not in str(_))
    except OSError:
        return None


def _append_git_summary(lines: list[str], ws: Path) -> None:
    from butler.tools.git_tools import git_read_enabled, _run_git

    if not git_read_enabled():
        lines.append("🔀 Git: 未启用")
        return

    workdir = str(ws)
    branch_result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], workdir=workdir)
    branch = (branch_result.get("stdout") or "").strip() if branch_result.get("exit_code") == 0 else "?"

    status = _run_git(["status", "--short"], workdir=workdir)
    change_count = 0
    if status.get("exit_code") == 0:
        change_lines = [
            line for line in (status.get("stdout") or "").strip().split("\n") if line.strip()
        ]
        change_count = len(change_lines)

    log = _run_git(["log", "-3", "--format=%h %ar %s"], workdir=workdir)
    commits = []
    if log.get("exit_code") == 0:
        commits = [c for c in (log.get("stdout") or "").strip().split("\n") if c.strip()]

    if change_count:
        lines.append(f"🔀 Git: [{branch}] {change_count} 个未提交变更")
    else:
        lines.append(f"🔀 Git: [{branch}] 工作区干净")

    if commits:
        lines.append("📝 最近提交:")
        for c in commits[:3]:
            lines.append(f"  · {c}")


def _append_todos_summary(lines: list[str], ws: Path) -> None:
    todos_path = ws / ".butler" / "todos.json"
    if not todos_path.is_file():
        return
    try:
        todos = json.loads(todos_path.read_text(encoding="utf-8"))
        if isinstance(todos, list):
            active = sum(1 for t in todos if t.get("status") in ("pending", "in_progress"))
            done = sum(1 for t in todos if t.get("status") == "completed")
            if active or done:
                lines.append(f"✅ 待办: {active} 活跃 / {done} 已完成")
    except (json.JSONDecodeError, OSError):
        pass


def _append_runtime_summary(lines: list[str], ws: Path) -> None:
    jobs_path = ws / "runtime" / "jobs.yaml"
    if not jobs_path.is_file():
        return
    try:
        import yaml
        data = yaml.safe_load(jobs_path.read_text(encoding="utf-8")) or {}
        jobs = data.get("jobs", [])
        active = sum(1 for j in jobs if j.get("enabled", True))
        if jobs:
            lines.append(f"⏰ 定时任务: {active} 个活跃 / {len(jobs)} 总计")
    except Exception as exc:
        logger.debug("append runtime summary skipped: %s", exc)
def _append_memory_summary(lines: list[str], ws: Path) -> None:
    mem_path = ws / ".butler" / "memory" / "MEMORY.md"
    if not mem_path.is_file():
        return
    try:
        content = mem_path.read_text(encoding="utf-8")
        line_count = len(content.strip().split("\n"))
        lines.append(f"💾 项目记忆: MEMORY.md {line_count} 行")
    except OSError:
        pass


def handle_dev_command(
    cmd: str,
    arg: str = "",
    *,
    platform: str = "",
    external_id: str | None = None,
    session_key: str = "",
) -> str | None:
    """Return reply for dev slash commands, or None.

    Sprint 12 SEC-12-2: dev tools (git/test/build/dashboard) only Owner.
    """
    if not is_gateway_owner(
        platform=platform, external_id=external_id, session_key=session_key
    ):
        return owner_required_message()
    if cmd in ("/开发状态", "/dev-status"):
        return format_dev_status()
    if cmd in ("/开发验收", "/dev-smoke"):
        return run_dev_smoke()
    if cmd in ("/git",):
        return format_git_for_wechat(arg)
    if cmd in ("/测试", "/test"):
        return format_test_for_wechat(arg)
    if cmd in ("/构建", "/build"):
        return format_build_for_wechat(arg)
    if cmd in ("/项目概况", "/project-dashboard"):
        return format_project_dashboard(arg)
    return None
