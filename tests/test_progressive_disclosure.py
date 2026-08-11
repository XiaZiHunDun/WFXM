"""butler.skills.progressive_disclosure 模块的综合测试。

覆盖:
1. parse_skill_frontmatter() — 前言解析、缺失、畸形、嵌套、列表、多行body
2. SkillMetadata — 构造、字段、默认值、bump_usage()
3. SkillRegistry — discover/list/load/search/categories/排除目录/平台过滤/路径穿越防护
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import pytest

from butler.skills.progressive_disclosure import (
    EXCLUDED_DIR_NAMES,
    SkillContent,
    SkillMetadata,
    SkillRegistry,
    parse_skill_frontmatter,
)


# ---------------------------------------------------------------------------
# 辅助: 创建测试 SKILL.md 文件
# ---------------------------------------------------------------------------

def _write_skill(
    path: Path,
    name: str = "test-skill",
    description: str = "A test skill",
    category: str = "general",
    version: str = "1.0.0",
    source: str = "builtin",
    extra_frontmatter: str = "",
    body: str = "# Skill Body\n\nThis is the body.",
    references: dict[str, str] | None = None,
    templates: dict[str, str] | None = None,
) -> Path:
    """在给定目录下创建一个 SKILL.md 文件及其可选的引用/模板文件。"""
    fm_lines = [
        "---",
        f"name: {name}",
        f"description: {description}",
        f"category: {category}",
        f"version: {version}",
        f"source: {source}",
    ]
    if extra_frontmatter:
        fm_lines.append(extra_frontmatter)
    fm_lines.append("---")
    fm_lines.append("")
    fm_lines.append(body)

    skill_dir = path / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("\n".join(fm_lines), encoding="utf-8")

    # 创建引用文件
    if references:
        refs_dir = skill_dir / "references"
        refs_dir.mkdir(exist_ok=True)
        for ref_name, ref_content in references.items():
            ref_path = refs_dir / ref_name
            ref_path.parent.mkdir(parents=True, exist_ok=True)
            ref_path.write_text(ref_content, encoding="utf-8")

    # 创建模板文件
    if templates:
        tmpl_dir = skill_dir / "templates"
        tmpl_dir.mkdir(exist_ok=True)
        for tmpl_name, tmpl_content in templates.items():
            tmpl_path = tmpl_dir / tmpl_name
            tmpl_path.parent.mkdir(parents=True, exist_ok=True)
            tmpl_path.write_text(tmpl_content, encoding="utf-8")

    return skill_file


# ===================================================================
# 1. parse_skill_frontmatter() 测试
# ===================================================================

class TestParseSkillFrontmatter:
    """parse_skill_frontmatter 的各种场景。"""

    def test_simple_frontmatter(self):
        """简单前言解析 — 基本键值对。"""
        content = "---\nname: my-skill\ndescription: A test skill\n---\n# Body"
        fm, body = parse_skill_frontmatter(content)
        assert fm == {"name": "my-skill", "description": "A test skill"}
        assert body == "# Body"

    def test_missing_frontmatter_returns_empty_dict(self):
        """没有 --- 前言时返回空 dict，body 为原文。"""
        content = "# Just a markdown file\n\nNo frontmatter here."
        fm, body = parse_skill_frontmatter(content)
        assert fm == {}
        assert body == content

    def test_malformed_yaml_handled_gracefully(self):
        """畸形 YAML — 字段值缺少引号等，不应抛出异常。"""
        content = "---\n: invalid\n  bad: indent\n---\nbody"
        fm, body = parse_skill_frontmatter(content)
        assert isinstance(fm, dict)
        assert body == "body"

    def test_unterminated_frontmatter(self):
        """未闭合的 --- — 整体作为 body 返回。"""
        content = "---\nname: test\nbody text"
        fm, body = parse_skill_frontmatter(content)
        assert fm == {}
        assert body == content

    def test_nested_fields_parsed(self):
        """嵌套字段正确解析为 dict。"""
        content = (
            "---\n"
            "name: nested-skill\n"
            "metadata:\n"
            "  author: Alice\n"
            "  tags:\n"
            "    - python\n"
            "    - api\n"
            "---\n"
            "# Body"
        )
        fm, body = parse_skill_frontmatter(content)
        assert fm["name"] == "nested-skill"
        meta = fm["metadata"]
        assert isinstance(meta, dict)
        assert meta["author"] == "Alice"
        assert meta["tags"] == ["python", "api"]

    def test_list_fields_parsed_inline(self):
        """内联列表字段解析 — [a, b, c]。"""
        content = (
            "---\n"
            "name: listy\n"
            "tags: [python, yaml, test]\n"
            "---\n"
            "body"
        )
        fm, body = parse_skill_frontmatter(content)
        assert fm["tags"] == ["python", "yaml", "test"]

    def test_list_fields_parsed_block(self):
        """块式列表字段解析 — 每行一个 - item。"""
        content = (
            "---\n"
            "name: block-list\n"
            "tags:\n"
            "  - alpha\n"
            "  - beta\n"
            "  - gamma\n"
            "---\n"
            "body"
        )
        fm, body = parse_skill_frontmatter(content)
        assert fm["tags"] == ["alpha", "beta", "gamma"]

    def test_multiline_body_preserved(self):
        """多行 body 文本被完整保留。"""
        body_text = "# Title\n\nSome text.\n\n## Section 2\n\nMore text."
        content = f"---\nname: multi\n---\n\n{body_text}"
        fm, body = parse_skill_frontmatter(content)
        assert body.strip() == body_text

    def test_empty_frontmatter(self):
        """空前言块 — 两个 --- 紧邻，正则不匹配时整体作为 body。"""
        content = "---\n---\nbody"
        fm, body = parse_skill_frontmatter(content)
        assert fm == {}
        assert body == content

    def test_scalar_coercion_null_bool_int_float(self):
        """标量类型强制转换 — null/布尔/整数/浮点。"""
        content = (
            "---\n"
            "opt_null: null\n"
            "opt_tilde: ~\n"
            "opt_true: true\n"
            "opt_false: false\n"
            "opt_int: 42\n"
            "opt_float: 3.14\n"
            "opt_neg: -10\n"
            "---\n"
            "body"
        )
        fm, _ = parse_skill_frontmatter(content)
        assert fm["opt_null"] is None
        assert fm["opt_tilde"] is None
        assert fm["opt_true"] is True
        assert fm["opt_false"] is False
        assert fm["opt_int"] == 42
        assert fm["opt_float"] == 3.14
        assert fm["opt_neg"] == -10

    def test_quoted_strings(self):
        """带引号的字符串解析。"""
        content = (
            '---\n'
            'name: "quoted-skill"\n'
            "desc: 'single quoted'\n"
            'escaped: "line1\\nline2"\n'
            '---\n'
            'body'
        )
        fm, _ = parse_skill_frontmatter(content)
        assert fm["name"] == "quoted-skill"
        assert fm["desc"] == "single quoted"
        assert fm["escaped"] == "line1\nline2"

    def test_block_scalar_literal(self):
        """| 块标量 — 保留换行。"""
        content = (
            "---\n"
            "description: |\n"
            "  Line one\n"
            "  Line two\n"
            "  Line three\n"
            "---\n"
            "body"
        )
        fm, _ = parse_skill_frontmatter(content)
        desc = fm["description"]
        assert "Line one" in desc
        assert "Line two" in desc
        assert "Line three" in desc

    def test_block_scalar_folded(self):
        """> 块标量 — 折叠为单行。"""
        content = (
            "---\n"
            "description: >\n"
            "  Line one\n"
            "  Line two\n"
            "---\n"
            "body"
        )
        fm, _ = parse_skill_frontmatter(content)
        desc = fm["description"]
        assert "Line one" in desc
        assert "Line two" in desc

    def test_body_after_closing_dashes(self):
        """body 在关闭 --- 之后，含空行。"""
        content = "---\nname: x\n---\n\nbody here"
        fm, body = parse_skill_frontmatter(content)
        assert fm["name"] == "x"
        assert body == "body here"

    def test_windows_line_endings(self):
        """Windows 换行符 \\r\\n 正常处理。"""
        content = "---\r\nname: win-skill\r\ndescription: windows\r\n---\r\nbody\r\n"
        fm, body = parse_skill_frontmatter(content)
        assert fm["name"] == "win-skill"
        assert body == "body\r\n"


# ===================================================================
# 2. SkillMetadata 测试
# ===================================================================

class TestSkillMetadata:
    """SkillMetadata 数据类的构造与方法。"""

    def test_construction_with_required_fields(self):
        """使用必填字段构造。"""
        meta = SkillMetadata(name="test", description="desc")
        assert meta.name == "test"
        assert meta.description == "desc"

    def test_defaults(self):
        """默认值正确。"""
        meta = SkillMetadata(name="test", description="desc")
        assert meta.category == "general"
        assert meta.version == "1.0.0"
        assert meta.source == "builtin"
        assert meta.usage_count == 0
        assert meta.last_used == 0.0
        assert meta.created_by is None
        assert meta.related_skills == []
        assert meta.path is None

    def test_custom_values(self):
        """自定义字段值。"""
        meta = SkillMetadata(
            name="custom",
            description="custom desc",
            category="dev",
            version="2.0.0",
            source="user",
            usage_count=5,
            last_used=1234567890.0,
            created_by="Alice",
            related_skills=["skill-a", "skill-b"],
            path=Path("/tmp/skill"),
        )
        assert meta.category == "dev"
        assert meta.version == "2.0.0"
        assert meta.source == "user"
        assert meta.usage_count == 5
        assert meta.last_used == 1234567890.0
        assert meta.created_by == "Alice"
        assert meta.related_skills == ["skill-a", "skill-b"]
        assert meta.path == Path("/tmp/skill")

    def test_bump_usage(self):
        """bump_usage() 增加计数并更新时间戳。"""
        meta = SkillMetadata(name="test", description="desc")
        before = time.time()
        meta.bump_usage()
        after = time.time()

        assert meta.usage_count == 1
        assert before <= meta.last_used <= after

        meta.bump_usage()
        assert meta.usage_count == 2

    def test_bump_usage_multiple_times(self):
        """多次 bump_usage() 计数持续累加。"""
        meta = SkillMetadata(name="test", description="desc")
        for i in range(10):
            meta.bump_usage()
        assert meta.usage_count == 10

    def test_slots_dataclass(self):
        """slots=True 不可添加新属性。"""
        meta = SkillMetadata(name="test", description="desc")
        with pytest.raises(AttributeError):
            meta.nonexistent = "value"


class TestSkillContent:
    """SkillContent 数据类。"""

    def test_construction_defaults(self):
        """使用默认值构造。"""
        meta = SkillMetadata(name="test", description="desc")
        content = SkillContent(metadata=meta, body="# body")
        assert content.metadata is meta
        assert content.body == "# body"
        assert content.references == {}
        assert content.templates == {}

    def test_custom_references_and_templates(self):
        """自定义引用和模板。"""
        meta = SkillMetadata(name="test", description="desc")
        content = SkillContent(
            metadata=meta,
            body="body",
            references={"ref1.md": "# ref"},
            templates={"tpl1.j2": "{{ var }}"},
        )
        assert content.references == {"ref1.md": "# ref"}
        assert content.templates == {"tpl1.j2": "{{ var }}"}


# ===================================================================
# 3. SkillRegistry 测试
# ===================================================================

class TestSkillRegistryDiscovery:
    """discover_skills() 目录扫描。"""

    def test_discover_single_skill(self, tmp_path):
        """扫描单个技能目录。"""
        _write_skill(tmp_path, name="skill-a", description="First skill")
        reg = SkillRegistry()
        count = reg.discover_skills([tmp_path])
        assert count == 1
        skills = reg.list_skills()
        assert len(skills) == 1
        assert skills[0].name == "skill-a"
        assert skills[0].description == "First skill"

    def test_discover_multiple_skills(self, tmp_path):
        """扫描多个技能。"""
        _write_skill(tmp_path, name="skill-a", description="Alpha")
        _write_skill(tmp_path, name="skill-b", description="Beta")
        _write_skill(tmp_path, name="skill-c", description="Gamma")
        reg = SkillRegistry()
        count = reg.discover_skills([tmp_path])
        assert count == 3
        skills = reg.list_skills()
        assert len(skills) == 3

    def test_discover_skips_files_without_frontmatter(self, tmp_path):
        """跳过没有前言的 SKILL.md。"""
        skill_dir = tmp_path / "no-fm-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Just markdown\nNo frontmatter.", encoding="utf-8")
        reg = SkillRegistry()
        count = reg.discover_skills([tmp_path])
        assert count == 0

    def test_discover_skips_empty_dir(self, tmp_path):
        """空目录不报错。"""
        reg = SkillRegistry()
        count = reg.discover_skills([tmp_path])
        assert count == 0

    def test_discover_nonexistent_dir(self, tmp_path):
        """不存在的目录静默跳过。"""
        reg = SkillRegistry()
        count = reg.discover_skills([tmp_path / "ghost"])
        assert count == 0

    def test_discover_deduplicates(self, tmp_path):
        """同一 skill 发现多次只注册一次。"""
        _write_skill(tmp_path, name="dup-skill", description="dup")
        reg = SkillRegistry()
        c1 = reg.discover_skills([tmp_path])
        c2 = reg.discover_skills([tmp_path])
        assert c1 == 1
        assert c2 == 0
        assert len(reg.list_skills()) == 1

    def test_constructor_accepts_roots(self, tmp_path):
        """构造函数传入 skill_roots 自动触发发现。"""
        _write_skill(tmp_path, name="auto-skill", description="auto")
        reg = SkillRegistry(skill_roots=[tmp_path])
        skills = reg.list_skills()
        assert len(skills) == 1
        assert skills[0].name == "auto-skill"

    def test_skill_md_lowercase_name(self, tmp_path):
        """skill.md (小写) 也能被发现。"""
        skill_dir = tmp_path / "lowercase-skill"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text(
            "---\nname: lowercase-skill\ndescription: lower case\n---\nbody",
            encoding="utf-8",
        )
        reg = SkillRegistry()
        count = reg.discover_skills([tmp_path])
        assert count == 1

    def test_subdirectory_scanning(self, tmp_path):
        """递归扫描子目录。"""
        sub_dir = tmp_path / "sub1" / "sub2"
        _write_skill(sub_dir, name="nested-skill", description="nested")
        reg = SkillRegistry()
        count = reg.discover_skills([tmp_path])
        assert count == 1
        skills = reg.list_skills()
        assert skills[0].name == "nested-skill"


class TestSkillRegistryExcludedDirs:
    """排除目录测试。"""

    def test_git_directory_excluded(self, tmp_path):
        """.git 目录被排除。"""
        git_dir = tmp_path / ".git" / "skills"
        _write_skill(git_dir, name="git-skill", description="should be excluded")
        reg = SkillRegistry()
        count = reg.discover_skills([tmp_path])
        assert count == 0

    def test_node_modules_excluded(self, tmp_path):
        """node_modules 目录被排除。"""
        nm_dir = tmp_path / "node_modules"
        _write_skill(nm_dir, name="nm-skill", description="should be excluded")
        reg = SkillRegistry()
        count = reg.discover_skills([tmp_path])
        assert count == 0

    def test_venv_excluded(self, tmp_path):
        """venv 目录被排除。"""
        venv_dir = tmp_path / "venv"
        _write_skill(venv_dir, name="venv-skill", description="should be excluded")
        reg = SkillRegistry()
        count = reg.discover_skills([tmp_path])
        assert count == 0

    def test_idea_excluded(self, tmp_path):
        """.idea 目录被排除。"""
        idea_dir = tmp_path / ".idea"
        _write_skill(idea_dir, name="idea-skill", description="excluded")
        reg = SkillRegistry()
        count = reg.discover_skills([tmp_path])
        assert count == 0

    def test_pytest_cache_excluded(self, tmp_path):
        """.pytest_cache 目录被排除。"""
        cache_dir = tmp_path / ".pytest_cache"
        _write_skill(cache_dir, name="cache-skill", description="excluded")
        reg = SkillRegistry()
        count = reg.discover_skills([tmp_path])
        assert count == 0

    def test_included_dir_not_affected(self, tmp_path):
        """正常目录不受影响。"""
        normal_dir = tmp_path / "my_skills"
        _write_skill(normal_dir, name="ok-skill", description="ok")
        reg = SkillRegistry()
        count = reg.discover_skills([tmp_path])
        assert count == 1


class TestSkillRegistryListSkills:
    """list_skills() 过滤。"""

    def test_list_all(self, tmp_path):
        """列出所有技能。"""
        _write_skill(tmp_path, name="a", category="cat-a")
        _write_skill(tmp_path, name="b", category="cat-b")
        reg = SkillRegistry(skill_roots=[tmp_path])
        all_skills = reg.list_skills()
        assert len(all_skills) == 2

    def test_filter_by_category(self, tmp_path):
        """按 category 过滤。"""
        _write_skill(tmp_path, name="a", category="dev")
        _write_skill(tmp_path, name="b", category="ops")
        _write_skill(tmp_path, name="c", category="dev")
        reg = SkillRegistry(skill_roots=[tmp_path])
        dev_skills = reg.list_skills(category="dev")
        assert len(dev_skills) == 2
        ops_skills = reg.list_skills(category="ops")
        assert len(ops_skills) == 1

    def test_filter_by_source(self, tmp_path):
        """按 source 过滤。"""
        _write_skill(tmp_path, name="a", source="builtin")
        _write_skill(tmp_path, name="b", source="user")
        reg = SkillRegistry(skill_roots=[tmp_path])
        builtin = reg.list_skills(source="builtin")
        assert len(builtin) == 1
        user = reg.list_skills(source="user")
        assert len(user) == 1

    def test_filter_combination(self, tmp_path):
        """category + source 组合过滤。"""
        _write_skill(tmp_path, name="a", category="dev", source="builtin")
        _write_skill(tmp_path, name="b", category="dev", source="user")
        _write_skill(tmp_path, name="c", category="ops", source="builtin")
        reg = SkillRegistry(skill_roots=[tmp_path])
        result = reg.list_skills(category="dev", source="builtin")
        assert len(result) == 1
        assert result[0].name == "a"

    def test_list_sorted_alphabetically(self, tmp_path):
        """结果按名称字母排序。"""
        _write_skill(tmp_path, name="charlie")
        _write_skill(tmp_path, name="alpha")
        _write_skill(tmp_path, name="bravo")
        reg = SkillRegistry(skill_roots=[tmp_path])
        names = [s.name for s in reg.list_skills()]
        assert names == ["alpha", "bravo", "charlie"]

    def test_empty_list(self):
        """空注册表返回空列表。"""
        reg = SkillRegistry()
        assert reg.list_skills() == []

    def test_get_skill_metadata(self, tmp_path):
        """get_skill_metadata() 按名称查询。"""
        _write_skill(tmp_path, name="find-me", description="target")
        reg = SkillRegistry(skill_roots=[tmp_path])
        meta = reg.get_skill_metadata("find-me")
        assert meta is not None
        assert meta.name == "find-me"
        assert meta.description == "target"
        assert reg.get_skill_metadata("nonexistent") is None


class TestSkillRegistryLoadSkill:
    """load_skill() 及 Tier-2 加载。"""

    def test_load_skill_returns_content(self, tmp_path):
        """load_skill 返回 SkillContent 含 body。"""
        _write_skill(tmp_path, name="loader", body="# Full Body\n\nContent here.")
        reg = SkillRegistry(skill_roots=[tmp_path])
        content = reg.load_skill("loader")
        assert content is not None
        assert isinstance(content, SkillContent)
        assert content.body == "# Full Body\n\nContent here."
        assert content.metadata.name == "loader"

    def test_load_skill_nonexistent(self):
        """加载不存在的技能返回 None。"""
        reg = SkillRegistry()
        assert reg.load_skill("ghost") is None

    def test_load_skill_caches(self, tmp_path):
        """第二次加载命中缓存。"""
        _write_skill(tmp_path, name="cacheable")
        reg = SkillRegistry(skill_roots=[tmp_path])
        c1 = reg.load_skill("cacheable")
        c2 = reg.load_skill("cacheable")
        assert c1 is c2

    def test_load_skill_bumps_usage(self, tmp_path):
        """加载时自动 bump usage — bump 发生在 content 的 metadata 上。"""
        _write_skill(tmp_path, name="use-me")
        reg = SkillRegistry(skill_roots=[tmp_path])
        meta = reg.get_skill_metadata("use-me")
        assert meta.usage_count == 0
        content = reg.load_skill("use-me")
        assert content is not None
        assert content.metadata.usage_count == 1

    def test_load_skill_collects_references(self, tmp_path):
        """加载时收集 references/ 目录中的文件。"""
        _write_skill(
            tmp_path,
            name="with-refs",
            references={"guide.md": "# Guide content"},
        )
        reg = SkillRegistry(skill_roots=[tmp_path])
        content = reg.load_skill("with-refs")
        assert "guide.md" in content.references
        assert content.references["guide.md"] == "# Guide content"

    def test_load_skill_collects_templates(self, tmp_path):
        """加载时收集 templates/ 目录中的文件。"""
        _write_skill(
            tmp_path,
            name="with-tmpl",
            templates={"email.j2": "Hello {{ name }}"},
        )
        reg = SkillRegistry(skill_roots=[tmp_path])
        content = reg.load_skill("with-tmpl")
        assert "email.j2" in content.templates
        assert content.templates["email.j2"] == "Hello {{ name }}"

    def test_load_skill_override_description(self, tmp_path):
        """加载时 frontmatter 中的 description 覆盖 metadata。"""
        _write_skill(
            tmp_path,
            name="override",
            description="discovery desc",
            body="body",
        )
        # 修改 SKILL.md 让 description 不同
        skill_file = tmp_path / "override" / "SKILL.md"
        text = skill_file.read_text(encoding="utf-8")
        text = text.replace("discovery desc", "overridden desc")
        skill_file.write_text(text, encoding="utf-8")

        reg = SkillRegistry(skill_roots=[tmp_path])
        content = reg.load_skill("override")
        assert content.metadata.description == "overridden desc"

    def test_load_skill_override_version(self, tmp_path):
        """加载时 frontmatter 中的 version 覆盖 metadata。"""
        _write_skill(tmp_path, name="ver", version="1.0.0")
        skill_file = tmp_path / "ver" / "SKILL.md"
        text = skill_file.read_text(encoding="utf-8")
        text = text.replace("version: 1.0.0", "version: 2.5.0")
        skill_file.write_text(text, encoding="utf-8")

        reg = SkillRegistry(skill_roots=[tmp_path])
        content = reg.load_skill("ver")
        assert content.metadata.version == "2.5.0"


class TestSkillRegistryLoadReference:
    """load_skill_reference() 测试。"""

    def test_load_reference_from_references_dir(self, tmp_path):
        """从 references/ 目录加载引用文件。"""
        _write_skill(
            tmp_path,
            name="ref-skill",
            references={"setup.md": "Setup instructions here."},
        )
        reg = SkillRegistry(skill_roots=[tmp_path])
        text = reg.load_skill_reference("ref-skill", "setup.md")
        assert text == "Setup instructions here."

    def test_load_reference_from_templates_dir(self, tmp_path):
        """从 templates/ 目录加载模板文件。"""
        _write_skill(
            tmp_path,
            name="tmpl-skill",
            templates={"report.j2": "Template content"},
        )
        reg = SkillRegistry(skill_roots=[tmp_path])
        text = reg.load_skill_reference("tmpl-skill", "report.j2")
        assert text == "Template content"

    def test_load_reference_by_explicit_subpath(self, tmp_path):
        """通过显式子路径加载（references/xxx）。"""
        _write_skill(
            tmp_path,
            name="sub-skill",
            references={"deep/file.txt": "Deep content"},
        )
        reg = SkillRegistry(skill_roots=[tmp_path])
        text = reg.load_skill_reference("sub-skill", "references/deep/file.txt")
        assert text == "Deep content"

    def test_load_reference_missing_file(self, tmp_path):
        """引用文件不存在返回 None。"""
        _write_skill(tmp_path, name="no-ref")
        reg = SkillRegistry(skill_roots=[tmp_path])
        text = reg.load_skill_reference("no-ref", "missing.md")
        assert text is None

    def test_load_reference_nonexistent_skill(self):
        """技能不存在返回 None。"""
        reg = SkillRegistry()
        assert reg.load_skill_reference("ghost", "file.md") is None

    def test_load_reference_blocks_path_traversal(self, tmp_path):
        """路径穿越攻击被阻止 — 返回 None。"""
        _write_skill(tmp_path, name="traversal")
        reg = SkillRegistry(skill_roots=[tmp_path])
        # 尝试用 ../ 跳出技能目录
        result = reg.load_skill_reference("traversal", "../../etc/passwd")
        assert result is None

    def test_load_reference_blocks_absolute_path(self, tmp_path):
        """绝对路径被阻止。"""
        _write_skill(tmp_path, name="abs-path")
        reg = SkillRegistry(skill_roots=[tmp_path])
        result = reg.load_skill_reference("abs-path", "/etc/passwd")
        assert result is None

    def test_load_reference_with_dot_dot(self, tmp_path):
        """包含 .. 的路径被阻止。"""
        _write_skill(tmp_path, name="dotdot")
        reg = SkillRegistry(skill_roots=[tmp_path])
        result = reg.load_skill_reference("dotdot", "sub/../../secret")
        assert result is None


class TestSkillRegistryIncrementUsage:
    """increment_usage() 测试。"""

    def test_increment_usage(self, tmp_path):
        """increment_usage 更新 usage_count。"""
        _write_skill(tmp_path, name="usage-skill")
        reg = SkillRegistry(skill_roots=[tmp_path])
        meta = reg.get_skill_metadata("usage-skill")
        assert meta.usage_count == 0
        reg.increment_usage("usage-skill")
        assert meta.usage_count == 1
        reg.increment_usage("usage-skill")
        assert meta.usage_count == 2

    def test_increment_usage_nonexistent(self):
        """对不存在的技能调用不报错。"""
        reg = SkillRegistry()
        reg.increment_usage("ghost")

    def test_increment_usage_cached(self, tmp_path):
        """increment_usage 同时更新缓存中的 metadata。"""
        _write_skill(tmp_path, name="cache-usage")
        reg = SkillRegistry(skill_roots=[tmp_path])
        reg.load_skill("cache-usage")
        reg.increment_usage("cache-usage")
        content = reg.load_skill("cache-usage")
        assert content.metadata.usage_count >= 2


class TestSkillRegistrySearch:
    """search_skills() 模糊匹配。"""

    def test_search_by_name_exact(self, tmp_path):
        """精确名称匹配得分最高。"""
        _write_skill(tmp_path, name="python-expert", description="Python skill")
        _write_skill(tmp_path, name="java-expert", description="Java skill")
        reg = SkillRegistry(skill_roots=[tmp_path])
        results = reg.search_skills("python-expert")
        assert len(results) >= 1
        assert results[0].name == "python-expert"

    def test_search_by_name_partial(self, tmp_path):
        """名称子串匹配。"""
        _write_skill(tmp_path, name="machine-learning-pro", description="ML")
        _write_skill(tmp_path, name="data-science-basic", description="DS")
        reg = SkillRegistry(skill_roots=[tmp_path])
        results = reg.search_skills("machine")
        assert len(results) >= 1
        assert any("machine-learning" in r.name for r in results)

    def test_search_by_description(self, tmp_path):
        """描述文本匹配。"""
        _write_skill(tmp_path, name="a", description="Python data analysis")
        _write_skill(tmp_path, name="b", description="Java web service")
        reg = SkillRegistry(skill_roots=[tmp_path])
        results = reg.search_skills("data analysis")
        assert len(results) >= 1
        assert results[0].name == "a"

    def test_search_by_category(self, tmp_path):
        """类别匹配。"""
        _write_skill(tmp_path, name="a", category="devops")
        _write_skill(tmp_path, name="b", category="frontend")
        reg = SkillRegistry(skill_roots=[tmp_path])
        results = reg.search_skills("devops")
        assert len(results) >= 1
        assert results[0].category == "devops"

    def test_search_empty_query_returns_all(self, tmp_path):
        """空查询返回全部技能。"""
        _write_skill(tmp_path, name="a")
        _write_skill(tmp_path, name="b")
        reg = SkillRegistry(skill_roots=[tmp_path])
        results = reg.search_skills("")
        assert len(results) == 2

    def test_search_no_match(self, tmp_path):
        """无匹配返回空列表。"""
        _write_skill(tmp_path, name="a", description="alpha")
        reg = SkillRegistry(skill_roots=[tmp_path])
        results = reg.search_skills("zzznonexistent")
        assert results == []

    def test_search_related_skills_match(self, tmp_path):
        """related_skills 字段匹配。"""
        _write_skill(tmp_path, name="main", extra_frontmatter="related_skills: [helper-tool]")
        _write_skill(tmp_path, name="other")
        reg = SkillRegistry(skill_roots=[tmp_path])
        results = reg.search_skills("helper-tool")
        assert len(results) >= 1
        assert results[0].name == "main"

    def test_search_scoring_order(self, tmp_path):
        """结果按得分降序排列。"""
        _write_skill(tmp_path, name="python", description="Python language")
        _write_skill(tmp_path, name="python-basic", description="Python basics")
        reg = SkillRegistry(skill_roots=[tmp_path])
        results = reg.search_skills("python")
        # python 精确匹配应该排在 python-basic 前面
        if len(results) >= 2:
            assert results[0].name == "python"
            assert results[1].name == "python-basic"


class TestSkillRegistryCategories:
    """categories() 返回唯一类别。"""

    def test_categories_multiple(self, tmp_path):
        """返回多个唯一类别。"""
        _write_skill(tmp_path, name="a", category="dev")
        _write_skill(tmp_path, name="b", category="ops")
        _write_skill(tmp_path, name="c", category="dev")
        reg = SkillRegistry(skill_roots=[tmp_path])
        cats = reg.categories()
        assert cats == ["dev", "ops"]

    def test_categories_sorted(self, tmp_path):
        """类别按字母排序。"""
        _write_skill(tmp_path, name="a", category="zebra")
        _write_skill(tmp_path, name="b", category="alpha")
        _write_skill(tmp_path, name="c", category="middle")
        reg = SkillRegistry(skill_roots=[tmp_path])
        cats = reg.categories()
        assert cats == ["alpha", "middle", "zebra"]

    def test_categories_empty(self):
        """空注册表返回空列表。"""
        reg = SkillRegistry()
        assert reg.categories() == []

    def test_default_category(self, tmp_path):
        """没有 category 字段的技能归入 general。"""
        _write_skill(tmp_path, name="no-cat")
        reg = SkillRegistry(skill_roots=[tmp_path])
        cats = reg.categories()
        assert cats == ["general"]


class TestSkillRegistryPlatform:
    """平台过滤测试。"""

    def test_skill_without_platform_discovered(self, tmp_path):
        """无 platform 字段的技能在所有平台都能发现。"""
        _write_skill(tmp_path, name="no-platform")
        reg = SkillRegistry(skill_roots=[tmp_path])
        skills = reg.list_skills()
        assert len(skills) == 1

    def test_skill_matching_platform(self, tmp_path):
        """platform 匹配当前平台时被发现。"""
        current_platform = "linux" if sys.platform.startswith("linux") else "macos" if sys.platform == "darwin" else "windows"
        _write_skill(tmp_path, name="matched", extra_frontmatter=f"platform: {current_platform}")
        reg = SkillRegistry(skill_roots=[tmp_path])
        skills = reg.list_skills()
        assert len(skills) == 1

    def test_skill_mismatched_platform(self, tmp_path):
        """platform 不匹配当前平台时被跳过。"""
        other_platform = "windows" if not sys.platform.startswith("win") else "linux"
        _write_skill(tmp_path, name="mismatched", extra_frontmatter=f"platform: {other_platform}")
        reg = SkillRegistry(skill_roots=[tmp_path])
        skills = reg.list_skills()
        assert len(skills) == 0

    def test_skill_platform_list_includes_current(self, tmp_path):
        """platform 列表包含当前平台时被发现。"""
        current_platform = "linux" if sys.platform.startswith("linux") else "macos" if sys.platform == "darwin" else "windows"
        _write_skill(tmp_path, name="multi-platform", extra_frontmatter=f'platform: [{current_platform}, "other"]')
        reg = SkillRegistry(skill_roots=[tmp_path])
        skills = reg.list_skills()
        assert len(skills) == 1

    def test_skill_platform_list_excludes_current(self, tmp_path):
        """platform 列表不含当前平台时被跳过。"""
        other_platform = "windows" if not sys.platform.startswith("win") else "linux"
        _write_skill(tmp_path, name="excluded", extra_frontmatter=f'platform: [{other_platform}]')
        reg = SkillRegistry(skill_roots=[tmp_path])
        skills = reg.list_skills()
        assert len(skills) == 0

    def test_skill_with_empty_platform(self, tmp_path):
        """空 platform 字段不排除技能。"""
        _write_skill(tmp_path, name="empty-platform", extra_frontmatter="platform: ''")
        reg = SkillRegistry(skill_roots=[tmp_path])
        skills = reg.list_skills()
        assert len(skills) == 1


class TestSkillRegistryEdgeCases:
    """SkillRegistry 其他边界场景。"""

    def test_skill_metadata_path_set(self, tmp_path):
        """发现的技能 path 字段指向 SKILL.md 文件。"""
        _write_skill(tmp_path, name="path-skill")
        reg = SkillRegistry(skill_roots=[tmp_path])
        meta = reg.get_skill_metadata("path-skill")
        assert meta is not None
        assert meta.path is not None
        assert meta.path.name == "SKILL.md"

    def test_usage_count_persists_in_registry(self, tmp_path):
        """usage_count 在注册表中持续累加。"""
        _write_skill(tmp_path, name="persist")
        reg = SkillRegistry(skill_roots=[tmp_path])
        reg.increment_usage("persist")
        reg.increment_usage("persist")
        reg.increment_usage("persist")
        meta = reg.get_skill_metadata("persist")
        assert meta.usage_count == 3

    def test_multiple_roots(self, tmp_path):
        """多个根目录同时扫描。"""
        root1 = tmp_path / "root1"
        root2 = tmp_path / "root2"
        _write_skill(root1, name="from-root1")
        _write_skill(root2, name="from-root2")
        reg = SkillRegistry(skill_roots=[root1, root2])
        skills = reg.list_skills()
        assert len(skills) == 2

    def test_excluded_dir_names_immutable(self):
        """EXCLUDED_DIR_NAMES 是 frozenset，不可变。"""
        assert isinstance(EXCLUDED_DIR_NAMES, frozenset)
        with pytest.raises(AttributeError):
            EXCLUDED_DIR_NAMES.add("new_dir")

    def test_registry_not_thread_safe(self, tmp_path):
        """文档说明注册表非线程安全 — 验证基本并发写入不崩溃。"""
        import threading

        _write_skill(tmp_path, name="thread-skill")
        reg = SkillRegistry(skill_roots=[tmp_path])
        errors = []

        def load_skill():
            try:
                reg.load_skill("thread-skill")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=load_skill) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0

    def test_skill_with_unicode_body(self, tmp_path):
        """Unicode body 正常加载。"""
        body = "# 技能标题\n\n这是一段中文描述。🎉"
        _write_skill(tmp_path, name="unicode", body=body)
        reg = SkillRegistry(skill_roots=[tmp_path])
        content = reg.load_skill("unicode")
        assert content is not None
        assert "技能标题" in content.body
        assert "中文描述" in content.body

    def test_skill_with_special_chars_in_frontmatter(self, tmp_path):
        """前言中包含特殊字符正常解析。"""
        _write_skill(
            tmp_path,
            name="special",
            description="描述含特殊字符: <>&\"'!@#$%",
        )
        reg = SkillRegistry(skill_roots=[tmp_path])
        meta = reg.get_skill_metadata("special")
        assert meta is not None
        assert "<>&\"'!@#$%" in meta.description