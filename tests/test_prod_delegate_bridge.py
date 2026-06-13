"""Production delegate bridge + B9_FAIL retrieval guard."""

from __future__ import annotations

import json
from pathlib import Path

from butler.dev_engine.coding_knowledge import (
    CodingExperience,
    ExperienceLibrary,
    TheoremLibrary,
    process_task,
)
from butler.dev_engine.prod_delegate_bridge import (
    enrich_delegate_context_for_production,
    experience_task_affinity,
    infer_b9_task_id,
    migrate_lingwen_experiences_to_l3,
    production_auto_verify_levels,
    production_delegate_keywords,
    should_apply_prod_delegate_bridge,
)
from butler.memory.memory_scope import LINGWEN1_PROJECT_ID, project_coding_experiences_path


def test_should_apply_prod_bridge_for_lingwen_sample():
    assert should_apply_prod_delegate_bridge(
        role="dev",
        category="lingwen-prod-sample",
    )


def test_should_not_apply_prod_bridge_for_b9_benchmark():
    assert not should_apply_prod_delegate_bridge(
        role="dev",
        category="b9-benchmark",
    )


def test_infer_lingwen_sample_task_id():
    tid = infer_b9_task_id(
        "Read demo/hello.py and verify add",
        "lingwen1-sample-demo-import context",
        category="lingwen-prod-sample",
    )
    assert tid == "B9L_prod_lingwen_demo_add"


def test_infer_lingwen_constants_sample_task_id():
    tid = infer_b9_task_id(
        "Verify constants.py has module docstring",
        "lingwen1-sample-constants-comment context",
        category="lingwen-prod-sample",
    )
    assert tid == "B9L_prod_lingwen_constants_docstring"


def test_production_keywords_include_retrieval_aliases():
    kws = production_delegate_keywords(
        "fix greet return hello pytest",
        "",
        category="deep",
    )
    assert "greet" in kws
    assert "hello" in kws


def test_production_auto_verify_levels_for_prod_category():
    assert production_auto_verify_levels("deep") == "lint,typecheck,test"
    assert production_auto_verify_levels("b9-benchmark") == ""


def test_experience_task_affinity_match():
    assert experience_task_affinity(
        "B9_EX_prod_lingwen_demo_add",
        inferred_task_id="B9L_prod_lingwen_demo_add",
    )
    assert experience_task_affinity(
        "B9_EX_test_driven_add",
        inferred_task_id="B9L_prod_lingwen_demo_add",
    ) is False


def test_enrich_context_injects_playbook():
    out = enrich_delegate_context_for_production(
        "base context",
        task="Read demo/hello.py verify add operator pytest",
        category="lingwen-prod-sample",
        category_meta={"category": "lingwen-prod-sample"},
    )
    assert "TASK PLAYBOOK" in out
    assert "B9L_prod_lingwen_demo_add" in out
    assert "base context" in out


def test_b9_fail_excluded_without_failure_class(tmp_path):
    tlib = TheoremLibrary()
    xlib = ExperienceLibrary(theorem_lib=tlib)
    xlib.add(
        CodingExperience(
            id="B9_EX_ok",
            title="ok",
            domain=["b9"],
            theorem_basis={"T01", "T03", "T04", "T10"},
            context="ping pong",
            pattern="p",
            benchmarks={"retrieval_keywords": "threshold,config,pytest"},
        ),
        skip_validation=True,
    )
    xlib.add(
        CodingExperience(
            id="B9_FAIL_two_file_patch",
            title="fail",
            domain=["b9", "failure", "wrong_patch"],
            theorem_basis={"T01", "T03", "T04", "T10"},
            context="threshold wrong",
            pattern="bad",
            benchmarks={"failure_class": "wrong_patch", "retrieval_keywords": "threshold"},
        ),
        skip_validation=True,
    )
    hits = xlib.search(
        {"threshold", "config", "pytest"},
        {"T01", "T03", "T04", "T10"},
        strict_coverage=True,
    )
    assert hits[0].id == "B9_EX_ok"
    assert all(h.id != "B9_FAIL_two_file_patch" for h in hits)

    matched = xlib.search(
        {"threshold", "wrong_patch"},
        {"T01", "T03", "T04", "T10"},
        strict_coverage=True,
        failure_class="wrong_patch",
    )
    assert any(h.id == "B9_FAIL_two_file_patch" for h in matched)


def test_migrate_lingwen_to_l3(tmp_path, monkeypatch):
    from types import SimpleNamespace

    ws = tmp_path / "lingwen"
    ws.mkdir()
    l4 = tmp_path / "coding_experiences.json"
    l4.write_text(
        json.dumps(
            [
                {
                    "id": "B9_EX_prod_lingwen_demo_add",
                    "title": "lw",
                    "domain": ["b9"],
                    "theorem_basis": ["T01"],
                    "context": "c",
                    "pattern": "p",
                    "scope": {
                        "visibility": "private",
                        "project_id": LINGWEN1_PROJECT_ID,
                        "source": "b9",
                    },
                },
                {
                    "id": "B9_EX_global",
                    "title": "g",
                    "domain": ["b9"],
                    "theorem_basis": ["T01"],
                    "context": "c",
                    "pattern": "p",
                    "scope": {"visibility": "global", "source": "b9"},
                },
            ]
        ),
        encoding="utf-8",
    )

    class _PM:
        def get_project(self, name: str):
            if name == LINGWEN1_PROJECT_ID:
                return SimpleNamespace(
                    name=LINGWEN1_PROJECT_ID,
                    workspace=ws,
                    pack="novel-factory",
                    type="content",
                )
            return None

    monkeypatch.setattr("butler.project.manager.get_project_manager", lambda: _PM())

    dry = migrate_lingwen_experiences_to_l3(butler_home=tmp_path, dry_run=True)
    assert dry["migrated"] == ["B9_EX_prod_lingwen_demo_add"]

    applied = migrate_lingwen_experiences_to_l3(butler_home=tmp_path, dry_run=False)
    assert applied["migrated"] == ["B9_EX_prod_lingwen_demo_add"]
    l4_rows = json.loads(l4.read_text(encoding="utf-8"))
    assert len(l4_rows) == 1
    assert l4_rows[0]["id"] == "B9_EX_global"
    l3_path = project_coding_experiences_path(ws)
    l3_rows = json.loads(l3_path.read_text(encoding="utf-8"))
    assert l3_rows[0]["id"] == "B9_EX_prod_lingwen_demo_add"
    assert l3_rows[0]["scope"]["level"] == "project"


def test_process_task_prefers_b9_ex_over_fail(tmp_path):
    tlib = TheoremLibrary()
    xlib = ExperienceLibrary(theorem_lib=tlib)
    xlib.add(
        CodingExperience(
            id="B9_EX_test_driven_add",
            title="ok",
            domain=["b9"],
            theorem_basis={"T01", "T03", "T04", "T10"},
            context="ping pong implement",
            pattern="p",
            benchmarks={
                "b9_task": "B9L_test_driven_add",
                "retrieval_keywords": "ping,pong,implement",
            },
        ),
        skip_validation=True,
    )
    xlib.add(
        CodingExperience(
            id="B9_FAIL_test_driven_add",
            title="fail",
            domain=["b9", "failure"],
            theorem_basis={"T01", "T03", "T04", "T10"},
            context="ping fail",
            pattern="bad",
            benchmarks={"failure_class": "verify_fail", "retrieval_keywords": "ping,pong"},
        ),
        skip_validation=True,
    )
    ctx = process_task(
        ["ping", "pong", "implement", "pytest"],
        tlib,
        xlib,
        strict_experience=True,
    )
    assert ctx.selected_experience is not None
    assert ctx.selected_experience.id == "B9_EX_test_driven_add"
