"""DESIGN.md section extraction and preset resolution (PR5)."""

from __future__ import annotations

from pathlib import Path

from butler.core.design_md_sections import (
    extract_design_md_sections,
    format_frontmatter_summary,
    parse_frontmatter,
    resolve_design_md_path,
)
from butler.core.handoff import default_visual_acceptance, render_handoff_block
from butler.delegate.category_resolver import resolve_category
from butler.project import Project


def test_resolve_design_md_workspace_root(tmp_path: Path):
    design = tmp_path / "DESIGN.md"
    design.write_text("# Design\n", encoding="utf-8")
    assert resolve_design_md_path(tmp_path) == design.resolve()


def test_resolve_design_preset_butler_dir(tmp_path: Path):
    preset_path = tmp_path / ".butler" / "design" / "minimax" / "DESIGN.md"
    preset_path.parent.mkdir(parents=True)
    preset_path.write_text("---\nname: mini\n---\n", encoding="utf-8")
    got = resolve_design_md_path(tmp_path, design_preset="minimax")
    assert got == preset_path.resolve()


def test_extract_dos_and_responsive(tmp_path: Path):
    (tmp_path / "DESIGN.md").write_text(
        "---\nname: demo\ncolors:\n  primary: '#112233'\n---\n"
        "# Design\n\n"
        "## Overview\n"
        "Brand overview.\n\n"
        "## Do's and Don'ts\n"
        "- Do use tokens\n"
        "- Don't hardcode hex\n\n"
        "## Responsive Behavior\n"
        "Mobile first.\n\n"
        "## Components\n"
        "ignored body.\n",
        encoding="utf-8",
    )
    block = extract_design_md_sections(
        tmp_path,
        section_names=("Overview", "Do's and Don'ts", "Responsive Behavior"),
    )
    assert "Do's and Don'ts" in block
    assert "Don't hardcode" in block
    assert "Responsive Behavior" in block
    assert "primary" in block or "frontmatter" in block.lower()
    assert "ignored body" not in block or "Components" not in block


def test_frontmatter_summary():
    fm = {"name": "x", "colors": {"primary": "#000"}}
    summary = format_frontmatter_summary(fm)
    assert "primary" in summary


def test_parse_frontmatter_splits_body():
    fm, body = parse_frontmatter("---\nbrand: acme\n---\n## Foo\nbar")
    assert fm.get("brand") == "acme"
    assert "## Foo" in body


def test_project_design_preset_field(tmp_path: Path):
    cfg = tmp_path / "project.yaml"
    cfg.write_text("name: ui\ndesign_preset: cursor\n", encoding="utf-8")
    proj = Project.from_yaml(cfg)
    assert proj.design_preset == "cursor"


def test_ui_build_category_resolves():
    preset = resolve_category("ui-build")
    assert preset is not None
    assert preset.get("role") == "dev"
    assert "DESIGN.md" in str(preset.get("prompt_append") or "")


def test_visual_handoff_acceptance():
    block = render_handoff_block(acceptance=default_visual_acceptance())
    assert "DESIGN.md" in block
    assert "Do's and Don'ts" in block
