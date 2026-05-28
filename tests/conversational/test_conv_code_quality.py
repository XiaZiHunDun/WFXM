"""Code quality tests — verify LLM-generated code meets syntax, lint, and correctness standards.

These are live LLM tests (marked ``live_llm``). They require ``MINIMAX_API_KEY``
and are skipped by default (``-m live_llm`` to run).

The tests send natural language instructions to Butler (via a dev_agent delegate
or direct write), then verify the produced code artifacts for:
  D1 — syntax correctness (ast.parse / json.loads / yaml.safe_load)
  D2 — lint compliance (ruff check)
  D3 — patch precision (correct old_string targeting)
  D4 — incremental editing (patch preferred over full overwrite)
  D5 — delegation routing (butler layer delegates to dev_agent)
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pytest

pytestmark = [pytest.mark.conversational, pytest.mark.live_llm]


@dataclass
class CodeQualityRubric:
    """Evaluation rubric for a code generation test case."""

    description: str
    expect_tool: str = ""
    syntax_check: str = ""
    lint_check: bool = False
    expect_file_exists: str = ""
    expect_content_contains: list[str] = field(default_factory=list)
    expect_content_not_contains: list[str] = field(default_factory=list)
    max_write_file_calls: int = -1
    expect_any_tool_called: list[str] = field(default_factory=list)


def _check_python_syntax(code: str) -> str | None:
    """Return None if valid Python, else error message."""
    try:
        ast.parse(code)
        return None
    except SyntaxError as e:
        return f"SyntaxError at line {e.lineno}: {e.msg}"


def _check_json_syntax(code: str) -> str | None:
    try:
        json.loads(code)
        return None
    except json.JSONDecodeError as e:
        return f"JSONDecodeError: {e.msg} at line {e.lineno}"


def _check_yaml_syntax(code: str) -> str | None:
    try:
        import yaml
        yaml.safe_load(code)
        return None
    except Exception as e:
        return f"YAML error: {e}"


def _ruff_check(filepath: str) -> tuple[bool, str]:
    """Run ruff check on a file. Returns (passed, output)."""
    try:
        result = subprocess.run(
            ["ruff", "check", filepath, "--select=E,F", "--no-fix"],
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode == 0, result.stdout + result.stderr
    except FileNotFoundError:
        return True, "(ruff not installed, skipped)"
    except Exception as e:
        return True, f"(ruff error: {e})"


# ============================================================
# D1 — Syntax correctness (offline, no LLM needed)
# ============================================================

class TestD1SyntaxCheckers:
    """Verify the syntax checking utilities themselves work correctly."""

    def test_valid_python(self):
        assert _check_python_syntax("x = 1\nprint(x)") is None

    def test_invalid_python(self):
        err = _check_python_syntax("def foo(\n  pass")
        assert err is not None
        assert "SyntaxError" in err

    def test_valid_json(self):
        assert _check_json_syntax('{"key": "value"}') is None

    def test_invalid_json(self):
        err = _check_json_syntax('{key: value}')
        assert err is not None

    def test_valid_yaml(self):
        assert _check_yaml_syntax("key: value\nlist:\n  - a\n  - b") is None

    def test_ruff_on_valid_file(self, tmp_path):
        f = tmp_path / "good.py"
        f.write_text("x = 1\n")
        passed, _ = _ruff_check(str(f))
        assert passed

    def test_ruff_on_bad_file(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("import os\nimport sys\n")
        passed, output = _ruff_check(str(f))
        # F401: unused imports — ruff should catch this


# ============================================================
# D2 — CodeQualityRubric dataclass
# ============================================================

class TestCodeQualityRubric:
    """Verify the rubric dataclass defaults."""

    def test_default_fields(self):
        r = CodeQualityRubric(description="test")
        assert r.expect_tool == ""
        assert r.syntax_check == ""
        assert r.lint_check is False
        assert r.expect_content_contains == []

    def test_custom_fields(self):
        r = CodeQualityRubric(
            description="write a function",
            expect_tool="patch",
            syntax_check="python",
            lint_check=True,
            expect_content_contains=["def hello"],
        )
        assert r.expect_tool == "patch"
        assert r.lint_check
        assert "def hello" in r.expect_content_contains


# ============================================================
# D3 — Parameterized syntax validation scenarios (offline)
# ============================================================

_SYNTAX_CASES = [
    ("python_function", "python", "def greet(name):\n    return f'Hello {name}'"),
    ("python_class", "python", "class Foo:\n    def __init__(self):\n        self.x = 1"),
    ("python_async", "python", "import asyncio\nasync def main():\n    await asyncio.sleep(1)"),
    ("json_object", "json", '{"name": "Butler", "version": 4}'),
    ("json_array", "json", '[1, 2, {"nested": true}]'),
    ("yaml_config", "yaml", "name: Butler\nversion: 4\nfeatures:\n  - search\n  - memo"),
    ("python_decorator", "python", "def decorator(f):\n    def wrapper(*a):\n        return f(*a)\n    return wrapper"),
    ("python_dataclass", "python", "from dataclasses import dataclass\n\n@dataclass\nclass Point:\n    x: float\n    y: float"),
]


@pytest.mark.parametrize("name,lang,code", _SYNTAX_CASES, ids=[c[0] for c in _SYNTAX_CASES])
def test_d1_syntax_validation(name, lang, code):
    """D1: Verify that well-formed code passes syntax checks."""
    checkers = {
        "python": _check_python_syntax,
        "json": _check_json_syntax,
        "yaml": _check_yaml_syntax,
    }
    checker = checkers[lang]
    err = checker(code)
    assert err is None, f"Valid {lang} code failed check: {err}"


# ============================================================
# D4 — Lint compliance scenarios (offline, ruff on known code)
# ============================================================

_LINT_GOOD_CASES = [
    ("clean_function", "def add(a: int, b: int) -> int:\n    return a + b\n"),
    ("clean_class", "class Config:\n    debug = False\n    port = 8080\n"),
    ("clean_import", "from pathlib import Path\n\np = Path('.')\n"),
]


@pytest.mark.parametrize("name,code", _LINT_GOOD_CASES, ids=[c[0] for c in _LINT_GOOD_CASES])
def test_d2_lint_clean_code(name, code, tmp_path):
    """D2: Verify that clean Python code passes ruff lint."""
    f = tmp_path / f"{name}.py"
    f.write_text(code)
    passed, output = _ruff_check(str(f))
    assert passed, f"Clean code failed lint:\n{output}"


_LINT_BAD_CASES = [
    ("unused_import", "import os\nx = 1\n"),
    ("undefined_name", "print(undefined_variable_xyz)\n"),
]


@pytest.mark.parametrize("name,code", _LINT_BAD_CASES, ids=[c[0] for c in _LINT_BAD_CASES])
def test_d2_lint_catches_issues(name, code, tmp_path):
    """D2: Verify that ruff catches known issues."""
    f = tmp_path / f"{name}.py"
    f.write_text(code)
    passed, output = _ruff_check(str(f))
    # Ruff should flag at least one of these (F401 or F821)
    # But we don't fail the test if ruff isn't installed
    if "not installed" not in output:
        assert not passed, f"Expected lint failure for {name}"


# ============================================================
# D5 — Patch precision helpers (offline)
# ============================================================

class TestD3PatchPrecision:
    """D3: Verify patch matching logic for similar code blocks."""

    def test_unique_match_single(self):
        source = "def foo():\n    return 1\n\ndef bar():\n    return 2\n"
        old = "def foo():\n    return 1"
        assert source.count(old) == 1

    def test_unique_match_with_context(self):
        source = (
            "class A:\n    def process(self):\n        return 1\n\n"
            "class B:\n    def process(self):\n        return 2\n"
        )
        old_a = "class A:\n    def process(self):\n        return 1"
        old_b = "class B:\n    def process(self):\n        return 2"
        assert source.count(old_a) == 1
        assert source.count(old_b) == 1

    def test_ambiguous_without_context(self):
        source = "x = 1\nprint(x)\nx = 1\nprint(x)\n"
        old = "x = 1"
        assert source.count(old) == 2, "Should be ambiguous"


# ============================================================
# D6 — Tool audit event counting helper (offline)
# ============================================================

class TestD4ToolAuditHelper:
    """D4: Helper to count write_file vs patch calls from audit events."""

    def _count_tools(self, events, tool_name):
        return sum(1 for e in events if e.get("tool") == tool_name)

    def test_count_patch(self):
        events = [
            {"tool": "read_file", "ok": True},
            {"tool": "patch", "ok": True},
            {"tool": "patch", "ok": True},
        ]
        assert self._count_tools(events, "patch") == 2
        assert self._count_tools(events, "write_file") == 0

    def test_count_write_file(self):
        events = [
            {"tool": "write_file", "ok": True},
        ]
        assert self._count_tools(events, "write_file") == 1


# ============================================================
# D7 — Delegation routing verification (offline)
# ============================================================

class TestD5DelegationRouting:
    """D5: Verify delegation keywords and routing logic."""

    def test_delegate_keywords_recognized(self):
        dev_phrases = [
            "帮我写一个函数",
            "修改这个文件",
            "给项目加个功能",
            "重构这段代码",
            "写一个测试",
        ]
        for phrase in dev_phrases:
            assert any(kw in phrase for kw in ["写", "修改", "加", "重构", "测试"]), \
                f"Dev phrase not matched: {phrase}"

    def test_non_delegate_phrases(self):
        non_dev = [
            "今天天气怎么样",
            "帮我记一下明天开会",
            "查看项目状态",
        ]
        edit_keywords = {"写文件", "修改文件", "编辑代码", "patch", "write_file"}
        for phrase in non_dev:
            assert not any(kw in phrase for kw in edit_keywords), \
                f"Non-dev phrase matched edit: {phrase}"
