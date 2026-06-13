"""Memory scope for multi-project coding experiences."""

from __future__ import annotations

import json
from pathlib import Path

from butler.dev_engine.coding_knowledge import CodingExperience, ExperienceLibrary, TheoremLibrary
from butler.memory.memory_scope import (
    LINGWEN1_PROJECT_ID,
    MemoryScope,
    infer_default_scope,
    project_coding_experiences_path,
)


def test_infer_lingwen_private_scope():
    scope = infer_default_scope(exp_id="B9_EX_prod_lingwen_demo_add", domain=["b9"])
    assert scope.visibility == "private"
    assert scope.project_id == LINGWEN1_PROJECT_ID


def test_infer_b9_global_scope():
    scope = infer_default_scope(exp_id="B9_EX_test_driven_add", domain=["b9"])
    assert scope.visibility == "global"
    assert scope.source == "b9"


def test_memory_scope_visible_private():
    scope = MemoryScope(visibility="private", project_id="灵文1号")
    assert scope.visible_to(project_id="灵文1号")
    assert not scope.visible_to(project_id="演示试点")
    assert not scope.visible_to(project_id="")


def test_memory_scope_visible_stack():
    scope = MemoryScope(visibility="stack", stack_tags=("novel-factory", "python"))
    assert scope.visible_to(project_id="x", stack_tags=frozenset({"novel-factory"}))
    assert not scope.visible_to(project_id="x", stack_tags=frozenset({"rust"}))


def test_coding_experience_scope_roundtrip(tmp_path):
    path = tmp_path / "coding_experiences.json"
    xlib = ExperienceLibrary()
    xlib.add(
        CodingExperience(
            id="EX_demo",
            title="demo",
            domain=["b9"],
            theorem_basis={"T01"},
            context="ctx",
            pattern="pat",
            scope=MemoryScope(visibility="private", project_id="P1", source="manual"),
        ),
        skip_validation=True,
    )
    xlib.save_to_file(str(path))
    loaded = ExperienceLibrary.load_from_file(str(path))
    exp = loaded.get("EX_demo")
    assert exp is not None
    assert exp.scope.visibility == "private"
    assert exp.scope.project_id == "P1"


def test_search_filters_private_by_project():
    xlib = ExperienceLibrary()
    xlib.add(
        CodingExperience(
            id="B9_EX_prod_lingwen_demo_add",
            title="lw",
            domain=["b9"],
            theorem_basis={"T01", "T03", "T04", "T10"},
            context="lingwen demo add operator",
            pattern="fix add",
            benchmarks={"retrieval_keywords": "lingwen,demo,add"},
            scope=infer_default_scope(exp_id="B9_EX_prod_lingwen_demo_add", domain=["b9"]),
        ),
        skip_validation=True,
    )
    xlib.add(
        CodingExperience(
            id="B9_EX_test_driven_add",
            title="global",
            domain=["b9"],
            theorem_basis={"T01", "T03", "T04", "T10"},
            context="test driven add ping pong",
            pattern="implement",
            benchmarks={"retrieval_keywords": "ping,pong,pytest"},
            scope=infer_default_scope(exp_id="B9_EX_test_driven_add", domain=["b9"]),
        ),
        skip_validation=True,
    )
    other = xlib.search(
        {"lingwen", "demo", "add"},
        {"T01", "T03", "T04", "T10"},
        project_id="演示试点",
    )
    assert all(e.id != "B9_EX_prod_lingwen_demo_add" for e in other)
    lw = xlib.search(
        {"lingwen", "demo", "add"},
        {"T01", "T03", "T04", "T10"},
        project_id=LINGWEN1_PROJECT_ID,
    )
    assert any(e.id == "B9_EX_prod_lingwen_demo_add" for e in lw)


def test_load_merged_for_project(tmp_path):
    tenant = tmp_path / "tenant.json"
    ws = tmp_path / "proj"
    ws.mkdir()
    tenant_lib = ExperienceLibrary()
    tenant_lib.add(
        CodingExperience(
            id="B9_EX_global",
            title="g",
            domain=["b9"],
            theorem_basis={"T01"},
            context="global ctx",
            pattern="g",
            benchmarks={"retrieval_keywords": "global"},
        ),
        skip_validation=True,
    )
    tenant_lib.save_to_file(str(tenant))

    proj_path = project_coding_experiences_path(ws)
    proj_path.parent.mkdir(parents=True, exist_ok=True)
    proj_lib = ExperienceLibrary()
    proj_lib.add(
        CodingExperience(
            id="EX_proj_only",
            title="p",
            domain=["dev"],
            theorem_basis={"T01"},
            context="project only",
            pattern="p",
            benchmarks={"retrieval_keywords": "project"},
            scope=MemoryScope(level="project", visibility="private", project_id="P1"),
        ),
        skip_validation=True,
    )
    proj_lib.save_to_file(str(proj_path))

    merged = ExperienceLibrary.load_merged_for_project(
        tenant_path=str(tenant),
        project_workspace=str(ws),
    )
    assert merged.get("B9_EX_global") is not None
    assert merged.get("EX_proj_only") is not None


def test_legacy_load_infers_scope_without_json_field(tmp_path):
    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "B9_EX_prod_lingwen_workflow_guard",
                    "title": "lw",
                    "domain": ["b9"],
                    "theorem_basis": ["T01"],
                    "context": "lingwen workflow",
                    "pattern": "guard",
                    "benchmarks": {},
                    "validity_start": 0,
                    "validity_end": 9999999999,
                    "supersedes": None,
                }
            ]
        ),
        encoding="utf-8",
    )
    loaded = ExperienceLibrary.load_from_file(str(path))
    exp = loaded.get("B9_EX_prod_lingwen_workflow_guard")
    assert exp is not None
    assert exp.scope.visibility == "private"
    assert exp.scope.project_id == LINGWEN1_PROJECT_ID


def test_stack_tags_for_novel_factory_project(tmp_path):
    from types import SimpleNamespace

    from butler.memory.memory_scope import stack_tags_for_project

    ws = tmp_path / "lingwen"
    (ws / "novel-factory").mkdir(parents=True)
    proj = SimpleNamespace(pack="novel-factory", type="content", workspace=ws)
    tags = stack_tags_for_project(proj)
    assert "novel-factory" in tags
    assert "content" in tags


def test_load_delegate_experience_library_merges_l3(tmp_path):
    from types import SimpleNamespace

    from butler.memory.memory_scope import load_delegate_experience_library

    bh = tmp_path / "butler"
    bh.mkdir()
    tenant = bh / "coding_experiences.json"
    tenant.write_text("[]", encoding="utf-8")

    ws = tmp_path / "proj"
    ws.mkdir()
    proj = SimpleNamespace(name="演示试点", workspace=ws, pack="", type="software")

    xlib = load_delegate_experience_library(
        butler_home=bh,
        project=proj,
        theorem_lib=TheoremLibrary(),
    )
    assert xlib is not None


def test_process_task_respects_project_scope():
    from butler.dev_engine.coding_knowledge import process_task

    xlib = ExperienceLibrary()
    xlib.add(
        CodingExperience(
            id="B9_EX_prod_lingwen_demo_add",
            title="lw",
            domain=["b9"],
            theorem_basis={"T01", "T03", "T04", "T10"},
            context="lingwen demo add",
            pattern="fix",
            benchmarks={"retrieval_keywords": "lingwen,demo,add"},
            scope=infer_default_scope(exp_id="B9_EX_prod_lingwen_demo_add", domain=["b9"]),
        ),
        skip_validation=True,
    )
    tlib = TheoremLibrary()
    ctx_other = process_task(
        ["lingwen", "demo", "add"],
        tlib,
        xlib,
        project_id="演示试点",
        stack_tags=frozenset(),
    )
    assert ctx_other.selected_experience is None
    ctx_lw = process_task(
        ["lingwen", "demo", "add"],
        tlib,
        xlib,
        project_id=LINGWEN1_PROJECT_ID,
        stack_tags=frozenset({"novel-factory"}),
    )
    assert ctx_lw.selected_experience is not None
    assert ctx_lw.selected_experience.id == "B9_EX_prod_lingwen_demo_add"
