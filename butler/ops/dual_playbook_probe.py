"""B1 dual-playbook static + manifest helpers (LingWen1 维护态 / 新书态)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from butler.ops.lingwen1_delegate_drill import LINGWEN_PROJECT_NAME

# SSOT phrases — keep in sync with projects/LingWen1/docs/dual-playbook.md
MAINTENANCE_PROBE_TEXT = (
    "当前灵文1号是什么阶段？请读 workflow_state 后摘要，并建议今天适合跑哪个只读巡检。"
)
NEW_BOOK_PROBE_TEXT = (
    "我想新开一本小说，不是维护星陨纪元。请说明要从 workflow 哪一步开始，"
    "以及你会委派谁做什么。"
)

DUAL_PLAYBOOK_DOC = Path("projects/LingWen1/docs/dual-playbook.md")
WORKFLOW_STATE_REL = "novel-factory/workflow_state.json"
SCENARIO_MANIFEST = "wechat-dual-playbook-scenarios.yaml"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def run_dual_playbook_static_probe(*, root: Path | None = None) -> dict[str, Any]:
    """Preflight B1 without LLM: lifecycle, workflow_state, doc phrases, lead role."""
    root = root or _repo_root()
    errors: list[str] = []
    details: dict[str, Any] = {}

    doc = root / DUAL_PLAYBOOK_DOC
    if not doc.is_file():
        errors.append(f"missing {DUAL_PLAYBOOK_DOC}")
    else:
        text = doc.read_text(encoding="utf-8")
        for phrase, label in (
            (MAINTENANCE_PROBE_TEXT, "maintenance"),
            (NEW_BOOK_PROBE_TEXT, "new_book"),
        ):
            if phrase not in text:
                errors.append(f"dual-playbook.md missing {label} probe phrase")
        details["dual_playbook_doc"] = str(DUAL_PLAYBOOK_DOC)

    manifest = root / ".butler" / "simulation" / SCENARIO_MANIFEST
    if not manifest.is_file():
        errors.append(f"missing .butler/simulation/{SCENARIO_MANIFEST}")
    else:
        details["scenario_manifest"] = SCENARIO_MANIFEST

    from butler.project.lead import gateway_loop_role, is_lead_project
    from butler.project.manager import get_project_manager

    pm = get_project_manager()
    proj = pm.get_project(LINGWEN_PROJECT_NAME)
    if proj is None:
        errors.append(f"project not registered: {LINGWEN_PROJECT_NAME}")
    else:
        details["project"] = LINGWEN_PROJECT_NAME
        if not is_lead_project(LINGWEN_PROJECT_NAME, project=proj):
            errors.append("expected lead project")
        if gateway_loop_role(LINGWEN_PROJECT_NAME, project=proj) != "lead":
            errors.append("expected gateway_loop_role=lead")
        lc = (getattr(proj, "lifecycle", "") or "").strip()
        details["lifecycle"] = lc or "(unset)"
        if lc != "complete":
            errors.append(f"expected lifecycle=complete, got {lc!r}")

        from butler.project.meta import lifecycle_operating_hint

        hint = lifecycle_operating_hint(proj)
        if "维护态" not in hint:
            errors.append("lifecycle_operating_hint missing 维护态")
        details["lifecycle_hint_ok"] = "维护态" in hint

        ws = Path(proj.workspace)
        state_path = ws / WORKFLOW_STATE_REL
        if not state_path.is_file():
            errors.append(f"missing {WORKFLOW_STATE_REL}")
        else:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            phase = str(data.get("current_phase") or "")
            step = str(data.get("current_step") or "")
            details["workflow_phase"] = phase
            details["workflow_step"] = step
            if "COMPLETE" not in phase.upper():
                errors.append(f"expected PHASE_COMPLETE-like phase, got {phase!r}")
            if not step.startswith("STEP_"):
                errors.append(f"unexpected workflow step: {step!r}")

    ok = not errors
    return {
        "ok": ok,
        "errors": errors,
        "details": details,
        "maintenance_probe": MAINTENANCE_PROBE_TEXT,
        "new_book_probe": NEW_BOOK_PROBE_TEXT,
    }


__all__ = [
    "DUAL_PLAYBOOK_DOC",
    "MAINTENANCE_PROBE_TEXT",
    "NEW_BOOK_PROBE_TEXT",
    "SCENARIO_MANIFEST",
    "WORKFLOW_STATE_REL",
    "run_dual_playbook_static_probe",
]
