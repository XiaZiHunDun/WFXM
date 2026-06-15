"""B9 oracle gold curriculum — structured read→patch→pytest episodes for learning."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from butler.dev_engine.b9_types import B9TaskSpec


@dataclass(frozen=True)
class B9CurriculumStep:
    action: str
    target: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"action": self.action, "target": self.target, "detail": self.detail}


@dataclass
class B9CurriculumEpisode:
    task_id: str
    title: str
    tags: tuple[str, ...]
    steps: list[B9CurriculumStep]
    pattern_summary: str
    skill_name: str = ""
    anti_patterns: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "tags": list(self.tags),
            "skill_name": self.skill_name,
            "pattern_summary": self.pattern_summary,
            "anti_patterns": list(self.anti_patterns),
            "steps": [s.to_dict() for s in self.steps],
            "exported_at": time.time(),
        }


# Oracle gold episodes (Tier-1 curriculum first, then stretch).
B9_ORACLE_EPISODES: dict[str, B9CurriculumEpisode] = {
    "B9L_two_file_patch": B9CurriculumEpisode(
        task_id="B9L_two_file_patch",
        title="Adjust THRESHOLD in config.py for filter predicate",
        tags=("multi_file", "pytest", "tier1"),
        skill_name="b9-two-file-threshold",
        pattern_summary=(
            "Read test_b9.py for expected keep() behavior; patch config.py THRESHOLD "
            "(not filter.py) so predicate matches test."
        ),
        anti_patterns=("Editing test_b9.py", "Patching filter.py logic when only constant is wrong"),
        steps=[
            B9CurriculumStep("read_file", "test_b9.py", "keep(5) must be False; keep(15) True"),
            B9CurriculumStep("read_file", "config.py", "Locate THRESHOLD used by filter.keep"),
            B9CurriculumStep("patch", "config.py", "THRESHOLD = 10 → THRESHOLD = 5"),
            B9CurriculumStep("terminal", "pytest", "python3 -m pytest test_b9.py -q"),
        ],
    ),
    "B9L_extract_constant": B9CurriculumEpisode(
        task_id="B9L_extract_constant",
        title="Extract MAX_RETRIES to constants.py",
        tags=("multi_file", "refactor", "pytest", "tier1"),
        skill_name="b9-extract-constant",
        pattern_summary="Move shared constant to constants.py; update app.py import; keep tests green.",
        steps=[
            B9CurriculumStep("read_file", "test_b9.py", "Imports MAX_RETRIES from app"),
            B9CurriculumStep("read_file", "app.py", "Find MAX_RETRIES definition"),
            B9CurriculumStep("write_file", "constants.py", "MAX_RETRIES = 3"),
            B9CurriculumStep("patch", "app.py", "from constants import MAX_RETRIES"),
            B9CurriculumStep("terminal", "pytest", "python3 -m pytest test_b9.py -q"),
        ],
    ),
    "B9L_test_driven_add": B9CurriculumEpisode(
        task_id="B9L_test_driven_add",
        title="Add ping() to satisfy import in test",
        tags=("pytest", "add_function", "tier1"),
        skill_name="b9-test-driven-add",
        pattern_summary="Test imports ping from service — implement ping() returning exact literal 'pong'.",
        anti_patterns=("Leaving service.py empty", "Changing test import"),
        steps=[
            B9CurriculumStep("read_file", "test_b9.py", "assert ping() == 'pong'"),
            B9CurriculumStep("read_file", "service.py", "Nearly empty module"),
            B9CurriculumStep("write_file", "service.py", "def ping(): return 'pong'"),
            B9CurriculumStep("terminal", "pytest", "python3 -m pytest test_b9.py -q"),
        ],
    ),
    "B9L_add_missing_method": B9CurriculumEpisode(
        task_id="B9L_add_missing_method",
        title="Add Store.get() and fix __init__/put",
        tags=("pytest", "add_function", "tier1"),
        skill_name="b9-add-missing-method",
        pattern_summary="Add __init__ with dict, fix put to use self._data[k]=v, add get(k).",
        steps=[
            B9CurriculumStep("read_file", "test_b9.py", "Store.put then get('a') == 1"),
            B9CurriculumStep("read_file", "store.py", "Only put(); no get"),
            B9CurriculumStep("patch", "store.py", "Add __init__, get, fix put"),
            B9CurriculumStep("terminal", "pytest", "python3 -m pytest test_b9.py -q"),
        ],
    ),
    "B9L_fix_exception_handler": B9CurriculumEpisode(
        task_id="B9L_fix_exception_handler",
        title="Narrow bare except so ValueError propagates",
        tags=("pytest", "error_handling", "tier1"),
        skill_name="b9-fix-exception-handler",
        pattern_summary="Replace bare except+return None with except ValueError: raise.",
        steps=[
            B9CurriculumStep("read_file", "test_b9.py", "pytest.raises(ValueError) on 'x'"),
            B9CurriculumStep("read_file", "parser.py", "bare except returns None"),
            B9CurriculumStep("patch", "parser.py", "except ValueError: raise"),
            B9CurriculumStep("terminal", "pytest", "python3 -m pytest test_b9.py -q"),
        ],
    ),
    "B9L_fix_off_by_one_loop": B9CurriculumEpisode(
        task_id="B9L_fix_off_by_one_loop",
        title="Fix off-by-one in range bound",
        tags=("pytest", "logic_bug", "tier1"),
        skill_name="b9-fix-off-by-one",
        pattern_summary="sum_until(4)==6 means sum 0..3 — use range(n) not range(n+1).",
        steps=[
            B9CurriculumStep("read_file", "test_b9.py", "assert sum_until(4) == 6"),
            B9CurriculumStep("read_file", "loops.py", "for i in range(n + 1)"),
            B9CurriculumStep("patch", "loops.py", "range(n + 1) → range(n)"),
            B9CurriculumStep("terminal", "pytest", "python3 -m pytest test_b9.py -q"),
        ],
    ),
    "B9L_prod_no_test": B9CurriculumEpisode(
        task_id="B9L_prod_no_test",
        title="Trim label() return with strip()",
        tags=("prod_shaped", "pytest", "tier1"),
        skill_name="b9-trim-return",
        pattern_summary="Assertion wants trimmed string — add .strip() on f-string return.",
        anti_patterns=("Only read_file without patch", "Editing test"),
        steps=[
            B9CurriculumStep("read_file", "test_b9.py", "label('ok') == 'ok'"),
            B9CurriculumStep("read_file", "formatter.py", "returns padded f-string"),
            B9CurriculumStep("patch", "formatter.py", "append .strip() to return"),
            B9CurriculumStep("terminal", "pytest", "python3 -m pytest test_b9.py -q"),
        ],
    ),
    "B9L_multi_file_import": B9CurriculumEpisode(
        task_id="B9L_multi_file_import",
        title="Fix import module name to match helpers.py",
        tags=("multi_file", "import", "tier2"),
        skill_name="b9-fix-import",
        pattern_summary="list_directory; patch main.py import helper → helpers.",
        steps=[
            B9CurriculumStep("list_directory", ".", "Confirm helpers.py exists"),
            B9CurriculumStep("read_file", "main.py", "Wrong import from helper"),
            B9CurriculumStep("patch", "main.py", "from helpers import ..."),
            B9CurriculumStep("terminal", "pytest", "python3 -m pytest test_b9.py -q"),
        ],
    ),
    "B9L_pytest_fix_impl": B9CurriculumEpisode(
        task_id="B9L_pytest_fix_impl",
        title="Fix mul() operator",
        tags=("pytest", "logic_bug", "tier2"),
        skill_name="b9-fix-operator",
        pattern_summary="mul uses + but test expects * — patch calc.py only.",
        steps=[
            B9CurriculumStep("read_file", "test_b9.py", "Expected multiplication"),
            B9CurriculumStep("read_file", "calc.py", "return a + b"),
            B9CurriculumStep("patch", "calc.py", "a + b → a * b"),
            B9CurriculumStep("terminal", "pytest", "python3 -m pytest test_b9.py -q"),
        ],
    ),
    "B9L_prod_lingwen_validate_progress": B9CurriculumEpisode(
        task_id="B9L_prod_lingwen_validate_progress",
        title="Close LingWen workflow_state batch result",
        tags=("prod_shaped", "lingwen1", "novel_factory", "tier1"),
        skill_name="b9-prod-lingwen-validate-progress",
        pattern_summary=(
            "workflow_state.json one line status:OPEN_FIX — patch to status:PASSED, "
            "then run validate_progress.py."
        ),
        anti_patterns=("write_file entire JSON", "Skipping terminal validator"),
        steps=[
            B9CurriculumStep(
                "read_file",
                "novel-factory/workflow_state.json",
                "One line only: status:OPEN_FIX",
            ),
            B9CurriculumStep(
                "patch",
                "novel-factory/workflow_state.json",
                "old_string status:OPEN_FIX → new_string status:PASSED",
            ),
            B9CurriculumStep(
                "terminal",
                "novel-factory/scripts/validate_progress.py",
                "python3 novel-factory/scripts/validate_progress.py — expect 进度验证: 通过",
            ),
            B9CurriculumStep("terminal", "pytest", "python3 -m pytest test_b9.py -q"),
        ],
    ),
}


def curriculum_audit_path() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "audit" / "b9_curriculum.json"


def get_episode(task_id: str) -> B9CurriculumEpisode | None:
    return B9_ORACLE_EPISODES.get(task_id)


def episode_for_spec(spec: B9TaskSpec) -> B9CurriculumEpisode | None:
    return get_episode(spec.task_id)


def export_curriculum_to_disk(*, path: Path | None = None) -> Path:
    """Write all oracle episodes to audit JSON (curriculum SSOT on disk)."""
    out = path or curriculum_audit_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "exported_at": time.time(),
        "episode_count": len(B9_ORACLE_EPISODES),
        "episodes": [ep.to_dict() for ep in B9_ORACLE_EPISODES.values()],
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def format_curriculum_block(task_id: str, *, max_steps: int = 4) -> str:
    ep = get_episode(task_id)
    if ep is None or max_steps <= 0:
        return ""
    lines = [
        "<b9-curriculum>",
        f"## Oracle gold: {ep.title}",
        f"pattern: {ep.pattern_summary}",
    ]
    if ep.anti_patterns:
        lines.append("avoid: " + "; ".join(ep.anti_patterns))
    lines.append("steps:")
    for step in ep.steps[:max_steps]:
        lines.append(f"- {step.action} {step.target}: {step.detail}")
    lines.append("</b9-curriculum>")
    return "\n".join(lines)


_CATALOG_SKILLS_ROOT = (
    Path(__file__).resolve().parents[1] / "registry" / "catalog" / "skills"
)


def format_episode_skill_block(task_id: str) -> str:
    """Load catalog SKILL.md body for a curriculum episode (B9 LIVE injection)."""
    import re

    ep = get_episode(task_id)
    if ep is None or not ep.skill_name:
        return ""
    path = _CATALOG_SKILLS_ROOT / ep.skill_name / "SKILL.md"
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\s*\n.*?\n---\s*\n(.*)\Z", text, re.DOTALL)
    body = match.group(1).strip() if match else text.strip()
    if not body:
        return ""
    return f"### `{ep.skill_name}`\n{body}"


__all__ = [
    "B9_ORACLE_EPISODES",
    "B9CurriculumEpisode",
    "B9CurriculumStep",
    "curriculum_audit_path",
    "episode_for_spec",
    "export_curriculum_to_disk",
    "format_curriculum_block",
    "format_episode_skill_block",
    "get_episode",
]
