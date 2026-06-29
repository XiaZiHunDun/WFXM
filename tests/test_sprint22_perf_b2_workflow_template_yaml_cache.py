"""Sprint 22-3 PERF-21-B-2: workflow/template YAML 缓存 (HIGH perf).

`butler/workflows/loader.py:36-69` 两个 load 函数 (load_builtin_workflow
+ load_workspace_workflow) 每次调用都 `yaml.safe_load(path.read_text(...))`,
**无缓存**. `butler/orchestrator.py:245-252, 386-396` 两个 system prompt
helper 也每次 `template.read_text(encoding="utf-8")`. 这些函数在
每个 message / 每个 lead 入口被调 (resolve_workflow 在
list_workflows_for_project / format_workflows_for_prompt /
format_workflow_preview 多处触发), 频繁 IO + YAML parse.

修复: mtime+size-keyed cache (Sprint 18-3 / 20-4 / 21-3 模式). 用
`(str(path), mtime_ns, size)` 作 key, 文件未变直接返 cache, 文件
变自动失效.

行为保证:
1) 同一文件调多次, 第二次起返 cache, yaml.safe_load / read_text 都不再被调
2) 文件 mtime / size 变, cache 失效, 重新 parse
3) 缓存的是解析后的 dataclass (`WorkflowDef`) 与 text (`str`), 都不是
   raw bytes (raw bytes 在 mtime 变化时需要重读; 但 parse 结果稳定
   就不再 reparse)
4) 失败路径 (OSError / YAMLError) 不污染 cache
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest import mock

import pytest

from butler.workflows import loader as wf_loader


# ---------- helpers ----------

@pytest.fixture
def workspace_with_workflow(tmp_path: Path) -> Path:
    """Create workspace with one workflow yaml."""
    wf_dir = tmp_path / ".butler" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "demo.yaml").write_text(
        "name: demo\ndescription: test\nsteps:\n  - id: s1\n    role: butler\n    task: do thing\n",
        encoding="utf-8",
    )
    return tmp_path


# ---------- tests ----------

@pytest.mark.unit
class TestLoadBuiltinWorkflowCache:
    """`load_builtin_workflow` 必须缓存 YAML parse 结果."""

    def test_uses_module_level_cache(self):
        """源码中必须有模块级 cache dict (key 由 path/mtime/size 组成)."""
        src = inspect.getsource(wf_loader)
        # 应有 cache dict 字段
        assert "_FILE_CACHE" in src or "_YAML_CACHE" in src or "_CACHE" in src, (
            "loader.py 必须有模块级 cache, 实际源码:\n" + src[:600]
        )

    def test_second_call_hits_cache_no_reparse(self, tmp_path: Path, monkeypatch):
        """第二次调用同一文件, yaml.safe_load 不应被再调."""
        wf = tmp_path / "x.yaml"
        wf.write_text("name: x\nsteps: []\n", encoding="utf-8")

        # Mock the yaml.safe_load in the loader module
        call_count = {"n": 0}
        original_safe_load = wf_loader.yaml.safe_load
        def counting_safe_load(text):
            call_count["n"] += 1
            return original_safe_load(text)
        monkeypatch.setattr(wf_loader.yaml, "safe_load", counting_safe_load)

        # Direct the function to our test file (since it builds path internally)
        # We patch the _BUILTIN_DIR or test with a builtin that exists.
        # Simpler: call with a name that does NOT exist, then patch path.
        # Even simpler: use load_workspace_workflow on our test workspace.
        pass  # see workspace test below

    def test_workspace_workflow_second_call_no_reparse(self, workspace_with_workflow, monkeypatch):
        """load_workspace_workflow 二次调用同一文件, safe_load 不应被重调."""
        call_count = {"n": 0}
        original = wf_loader.yaml.safe_load
        def counting(text):
            call_count["n"] += 1
            return original(text)
        monkeypatch.setattr(wf_loader.yaml, "safe_load", counting)

        wf1 = wf_loader.load_workspace_workflow(workspace_with_workflow, "demo")
        assert wf1 is not None
        first_count = call_count["n"]
        assert first_count >= 1, "首次加载必须 parse 一次"

        wf2 = wf_loader.load_workspace_workflow(workspace_with_workflow, "demo")
        assert wf2 is not None
        # 第二次不再 parse
        assert call_count["n"] == first_count, (
            f"二次调用未触发 reparse, 实际 safe_load 调用次数: "
            f"first={first_count}, after second={call_count['n']}"
        )

    def test_workspace_workflow_reparses_on_file_modification(self, workspace_with_workflow, monkeypatch):
        """文件 mtime 变化 → cache 失效 → 重新 parse."""
        call_count = {"n": 0}
        original = wf_loader.yaml.safe_load
        def counting(text):
            call_count["n"] += 1
            return original(text)
        monkeypatch.setattr(wf_loader.yaml, "safe_load", counting)

        wf1 = wf_loader.load_workspace_workflow(workspace_with_workflow, "demo")
        first_count = call_count["n"]

        # 修改文件 (会更新 mtime, 大小也可能变)
        wf_path = workspace_with_workflow / ".butler" / "workflows" / "demo.yaml"
        wf_path.write_text(
            "name: demo\ndescription: UPDATED\nsteps: []\n",
            encoding="utf-8",
        )
        wf2 = wf_loader.load_workspace_workflow(workspace_with_workflow, "demo")
        # 第二次必须重 parse (cache miss)
        assert call_count["n"] > first_count, (
            f"文件修改后应重 parse, 实际 safe_load 次数不变: {call_count['n']}"
        )
        assert wf2.description == "UPDATED", "新内容应被读到"

    def test_failed_parse_does_not_pollute_cache(self, workspace_with_workflow, monkeypatch):
        """YAML parse 失败时不应缓存 None (避免错误状态污染)."""
        # 把文件改成无效 YAML
        wf_path = workspace_with_workflow / ".butler" / "workflows" / "demo.yaml"
        wf_path.write_text("invalid: : :\n  - not closed", encoding="utf-8")

        # 第一次返 None (解析失败)
        wf1 = wf_loader.load_workspace_workflow(workspace_with_workflow, "demo")
        assert wf1 is None

        # 修好文件
        wf_path.write_text(
            "name: demo\ndescription: fixed\nsteps: []\n",
            encoding="utf-8",
        )

        # 第二次必须重新尝试 parse (不能因为上次失败就 cache None)
        wf2 = wf_loader.load_workspace_workflow(workspace_with_workflow, "demo")
        assert wf2 is not None, "修复后必须能成功加载, 不能 cache 失败状态"
        assert wf2.description == "fixed"


@pytest.mark.unit
class TestSystemTemplateCache:
    """`orchestrator._system_prompt_placeholders` + `build_lead_system_prompt`
    用的模板文件 (butler_system.md / lingwen_lead_system.md) 也必须缓存."""

    def test_orchestrator_uses_template_cache(self):
        """源码中应存在模板 cache dict 字段."""
        from butler.orchestrator import templates

        src_path = Path(templates.__file__)
        text = src_path.read_text(encoding="utf-8")
        assert "_TEMPLATE_CACHE" in text or "_PROMPT_CACHE" in text or "_FILE_CACHE" in text, (
            "templates.py 必须有模板 cache 字段, 源码:\n" + text[:800]
        )

    def test_template_second_call_no_reread(self, monkeypatch):
        """`read_template_cached` 二次调用, read_text 不应被再调."""
        from butler.orchestrator import templates

        template = templates.template_path()
        if not template.is_file():
            pytest.skip(f"template not present: {template}")

        monkeypatch.setattr(templates, "_TEMPLATE_CACHE", {})

        read_count = {"n": 0}
        original_read_text = Path.read_text

        def counting_read_text(self, *a, **kw):
            if str(self) == str(template):
                read_count["n"] += 1
            return original_read_text(self, *a, **kw)

        monkeypatch.setattr(Path, "read_text", counting_read_text)

        templates.read_template_cached(template)
        first = read_count["n"]
        templates.read_template_cached(template)
        assert read_count["n"] == first, (
            f"二次调 read_template_cached 必须不重读, 实际 {read_count['n']} > {first}"
        )


@pytest.mark.unit
class TestCacheKeyFormat:
    """cache key 必须是 (str(path), mtime_ns, size) 三元组."""

    def test_cache_key_includes_mtime_and_size(self):
        """源码中应通过 stat() 取 mtime_ns + size 来构造 key."""
        from butler.workflows import loader as wf_loader

        # cache key 在 _cached_load helper 里 (DRY)
        src = inspect.getsource(wf_loader._cached_load)
        assert "st_mtime_ns" in src, (
            "_cached_load 必须用 st_mtime_ns 作 cache key, 源码:\n" + src
        )
        assert "st_size" in src, (
            "_cached_load 必须用 st_size 作 cache key, 源码:\n" + src
        )

    def test_module_level_cache_dict(self):
        """loader 模块必须有 _FILE_CACHE 字段."""
        from butler.workflows import loader as wf_loader

        assert hasattr(wf_loader, "_FILE_CACHE"), (
            "loader 必须有模块级 _FILE_CACHE 字段"
        )
        assert isinstance(wf_loader._FILE_CACHE, dict), (
            f"_FILE_CACHE 必须是 dict, 实际 {type(wf_loader._FILE_CACHE)}"
        )
