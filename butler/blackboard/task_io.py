"""tasks/ 读写：backlog.yaml + claims/*.yaml。"""

from __future__ import annotations

from pathlib import Path

import yaml

from butler.blackboard import paths as bb_paths
from butler.blackboard.schema import BacklogFile, Claim


def load_backlog() -> BacklogFile:
    """读 tasks/backlog.yaml。文件不存在抛 FileNotFoundError。"""
    path = bb_paths.BACKLOG_PATH
    if not path.exists():
        raise FileNotFoundError(f"backlog not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return BacklogFile.model_validate(data)


def save_backlog(bf: BacklogFile) -> Path:
    """写 tasks/backlog.yaml。"""
    path = bb_paths.BACKLOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(bf.model_dump(mode="json"), allow_unicode=True, sort_keys=False)
    path.write_text(text, encoding="utf-8")
    return path


def _claim_path(task_id: str) -> Path:
    safe = task_id.replace("#", "%23").replace("/", "_")
    return bb_paths.CLAIMS_DIR / f"{safe}.yaml"


def load_claim(task_id: str) -> Claim:
    path = _claim_path(task_id)
    if not path.exists():
        raise FileNotFoundError(f"claim not found: {task_id}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Claim.model_validate(data)


def save_claim(claim: Claim) -> Path:
    claims_dir = bb_paths.CLAIMS_DIR
    claims_dir.mkdir(parents=True, exist_ok=True)
    path = _claim_path(claim.task_id)
    text = yaml.safe_dump(claim.model_dump(mode="json"), allow_unicode=True, sort_keys=False)
    path.write_text(text, encoding="utf-8")
    return path


def list_claims() -> list[Claim]:
    claims_dir = bb_paths.CLAIMS_DIR
    if not claims_dir.is_dir():
        return []
    out: list[Claim] = []
    for p in claims_dir.iterdir():
        if p.suffix == ".yaml" and p.name != ".gitkeep":
            try:
                out.append(Claim.model_validate(yaml.safe_load(p.read_text(encoding="utf-8"))))
            except Exception:
                continue
    return out