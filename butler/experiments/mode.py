"""Research mode path guards (harness read-only, experiments/ writable)."""

from __future__ import annotations

from pathlib import Path

from butler.env_parse import env_truthy

_PATH_WRITE_TOOLS = frozenset({"write_file", "patch", "delete_file"})


def experiment_mode_enabled() -> bool:
    return env_truthy("BUTLER_EXPERIMENT_MODE", default=False)


def _rel_path(workspace: Path, path_str: str) -> str:
    raw = str(path_str or "").strip()
    if not raw:
        return ""
    ws = workspace.expanduser().resolve()
    try:
        target = Path(raw).expanduser()
        if not target.is_absolute():
            target = (ws / target).resolve()
        else:
            target = target.resolve()
        return target.relative_to(ws).as_posix()
    except ValueError:
        return raw.replace("\\", "/").lstrip("/")


def is_harness_path(workspace: Path, path_str: str) -> bool:
    rel = _rel_path(workspace, path_str)
    if not rel:
        return False
    rel_lower = rel.lower()
    return (
        rel_lower.startswith(".butler/harness/")
        or rel_lower == ".butler/harness"
        or rel_lower.startswith("harness/")
        or rel_lower == "harness"
    )


def is_experiment_writable_path(workspace: Path, path_str: str) -> bool:
    rel = _rel_path(workspace, path_str)
    if not rel:
        return False
    rel_lower = rel.lower()
    if rel_lower == "experiments" or rel_lower.startswith("experiments/"):
        return True
    return False


def check_experiment_mode_block(
    tool_name: str,
    args: dict,
    *,
    workspace: Path | None,
) -> str | None:
    """Return error message when experiment mode forbids the path operation."""
    if not experiment_mode_enabled() or workspace is None:
        return None
    if tool_name not in _PATH_WRITE_TOOLS:
        return None
    path_val = str(args.get("path") or args.get("file_path") or "").strip()
    if not path_val:
        return None
    if is_harness_path(workspace, path_val):
        return (
            "BUTLER_EXPERIMENT_MODE=1：`.butler/harness/` 为只读评测面，"
            "禁止 write/patch/delete"
        )
    if not is_experiment_writable_path(workspace, path_val):
        return (
            "BUTLER_EXPERIMENT_MODE=1：仅允许写入 `experiments/` 目录；"
            f"拒绝路径: {path_val}"
        )
    return None


__all__ = [
    "check_experiment_mode_block",
    "experiment_mode_enabled",
    "is_experiment_writable_path",
    "is_harness_path",
]
