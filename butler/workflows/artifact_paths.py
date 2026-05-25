"""Canonical MetaGPT-style artifact paths under ``.butler/artifacts/``."""

from __future__ import annotations

from pathlib import Path

ARTIFACT_DIRNAME = "artifacts"
REQUIREMENTS_FILE = "REQUIREMENTS.md"
TASKS_FILE = "TASKS.md"
DESIGN_FILE = "DESIGN.md"


def artifacts_dir(workspace: Path | str) -> Path:
    return Path(workspace).expanduser().resolve() / ".butler" / ARTIFACT_DIRNAME


def requirements_path(workspace: Path | str) -> Path:
    return artifacts_dir(workspace) / REQUIREMENTS_FILE


def tasks_path(workspace: Path | str) -> Path:
    return artifacts_dir(workspace) / TASKS_FILE


def design_path(workspace: Path | str) -> Path:
    return artifacts_dir(workspace) / DESIGN_FILE


def ensure_artifact_scaffold(workspace: Path | str) -> Path:
    root = artifacts_dir(workspace)
    root.mkdir(parents=True, exist_ok=True)
    return root


__all__ = [
    "ARTIFACT_DIRNAME",
    "DESIGN_FILE",
    "REQUIREMENTS_FILE",
    "TASKS_FILE",
    "artifacts_dir",
    "design_path",
    "ensure_artifact_scaffold",
    "requirements_path",
    "tasks_path",
]
