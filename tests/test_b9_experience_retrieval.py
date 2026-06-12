"""B9 experience retrieval — production keyword bridge."""

from __future__ import annotations

import json
import os

from butler.dev_engine.b9_experience_retrieval import (
    apply_retrieval_benchmarks,
    backfill_b9_experience_retrieval,
    retrieval_keywords_for_task,
)
from butler.dev_engine.coding_knowledge import (
    CodingExperience,
    ExperienceLibrary,
    TheoremLibrary,
    process_task,
)
from butler.ops.b9_lessons import promote_episode_to_experience
from butler.dev_engine.b9_oracle_curriculum import get_episode


def test_greet_keywords_include_prod_phrasing():
    kws = retrieval_keywords_for_task("B9L_prod_demo_fix_greet_return")
    assert "greet" in kws
    assert "hello" in kws


def test_b9_experience_matches_production_greet_task(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.config.get_butler_home", lambda: tmp_path)
    xlib_path = tmp_path / "coding_experiences.json"
    tlib = TheoremLibrary()
    xlib = ExperienceLibrary(theorem_lib=tlib)
    benchmarks = apply_retrieval_benchmarks(
        {"b9_task": "B9L_prod_demo_fix_greet_return"},
        "B9L_prod_demo_fix_greet_return",
    )
    exp = CodingExperience(
        id="B9_EX_prod_demo_fix_greet_return",
        title="greet return",
        domain=["b9", "prod_shaped", "pytest"],
        theorem_basis={"T01", "T04", "T03", "T10"},
        context="B9L_prod_demo_fix_greet_return; production keywords: greet, hello",
        pattern="patch greet.py return hello",
        benchmarks=benchmarks,
        validity_start=0,
        validity_end=1e12,
    )
    xlib.add(exp, skip_validation=True)
    xlib.save_to_file(str(xlib_path))

    loaded = ExperienceLibrary.load_from_file(str(xlib_path), theorem_lib=tlib)
    ctx = process_task(
        ["fix", "greet", "pytest", "return", "hello"],
        tlib,
        loaded,
        strict_experience=True,
    )
    assert ctx.selected_experience is not None
    assert ctx.selected_experience.id.startswith("B9_EX_")


def test_promote_episode_writes_retrieval_keywords(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.config.get_butler_home", lambda: tmp_path)
    ep = get_episode("B9L_multi_file_import")
    assert ep is not None
    ok, _ = promote_episode_to_experience(ep, skip_if_exists=False)
    assert ok
    data = json.loads((tmp_path / "coding_experiences.json").read_text(encoding="utf-8"))
    row = next(r for r in data if r["id"] == "B9_EX_multi_file_import")
    assert "import" in row["benchmarks"].get("retrieval_keywords", "")
    assert "import" in row["context"].lower()


def test_backfill_updates_existing_b9_experiences(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.config.get_butler_home", lambda: tmp_path)
    ep = get_episode("B9L_test_driven_add")
    assert ep is not None
    promote_episode_to_experience(ep, skip_if_exists=False)
    path = os.path.join(str(tmp_path), "coding_experiences.json")
    # strip retrieval keywords to simulate legacy row
    rows = json.loads(open(path, encoding="utf-8").read())
    for row in rows:
        row["benchmarks"] = {"b9_task": row["benchmarks"].get("b9_task", "")}
        row["context"] = row["benchmarks"]["b9_task"]
    open(path, "w", encoding="utf-8").write(json.dumps(rows))
    out = backfill_b9_experience_retrieval(xlib_path=path)
    assert out["updated"] >= 1
    rows2 = json.loads(open(path, encoding="utf-8").read())
    assert any("retrieval_keywords" in r.get("benchmarks", {}) for r in rows2)
