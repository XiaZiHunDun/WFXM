"""Enhanced tests for Coding Knowledge Layer — covers audit gaps.

Covers:
- AST helper function direct tests
- T07 fail case
- Regex fallback path (invalid syntax → AST parse fails)
- CA4 strict mode env gate (BUTLER_CODING_STRICT)
- auto_verify theorem gate integration
- Experience persistence round-trip with validation
- ChromaDB integration (if available)
"""

from __future__ import annotations

import json
import os
import tempfile
import time

import pytest

from butler.dev_engine.coding_knowledge import (
    CodingElement,
    CodingExperience,
    ExperienceLibrary,
    TheoremLibrary,
    _ast_external_input_without_validation,
    _ast_has_bare_except_pass,
    _ast_has_eval_call,
    _ast_has_global_stmt,
    _ast_has_nondeterministic_call,
    _ast_http_request_without_status_check,
    _ast_open_without_context_manager,
    _ast_try_without_handler,
    _ast_while_true_missing_break,
    _check_t01_determinism,
    _check_t03_type_safety,
    _check_t04_termination,
    _check_t05_state_isolation,
    _check_t06_exception_safety,
    _check_t07_idempotency,
    _check_t08_resource_lifecycle,
    _check_t09_contract_adherence,
    _check_t10_trust_boundary,
    _try_parse_ast,
    dual_verify,
    extract_experience_candidate,
    process_task,
    verify_theorems,
)


# ═══════════════════════════════════════════════════════════════════
# AST Helper Direct Tests
# ═══════════════════════════════════════════════════════════════════

class TestASTHelperDirect:
    """Direct unit tests for each AST helper function."""

    def test_try_parse_ast_valid(self) -> None:
        tree = _try_parse_ast("x = 1")
        assert tree is not None

    def test_try_parse_ast_invalid_returns_none(self) -> None:
        assert _try_parse_ast("def f( :::") is None

    def test_nondeterministic_random_random(self) -> None:
        tree = _try_parse_ast("import random\nx = random.random()")
        assert tree is not None
        assert _ast_has_nondeterministic_call(tree) is not None

    def test_nondeterministic_datetime_now(self) -> None:
        tree = _try_parse_ast("import datetime\nt = datetime.now()")
        assert tree is not None
        assert _ast_has_nondeterministic_call(tree) is not None

    def test_nondeterministic_clean(self) -> None:
        tree = _try_parse_ast("def f(x): return x + 1")
        assert tree is not None
        assert _ast_has_nondeterministic_call(tree) is None

    def test_while_true_no_break(self) -> None:
        tree = _try_parse_ast("while True:\n    do_work()")
        assert tree is not None
        assert _ast_while_true_missing_break(tree) is True

    def test_while_true_with_break(self) -> None:
        tree = _try_parse_ast("while True:\n    if done:\n        break")
        assert tree is not None
        assert _ast_while_true_missing_break(tree) is False

    def test_while_condition_not_flagged(self) -> None:
        tree = _try_parse_ast("while x > 0:\n    x -= 1")
        assert tree is not None
        assert _ast_while_true_missing_break(tree) is False

    def test_global_stmt_present(self) -> None:
        tree = _try_parse_ast("def f():\n    global x\n    x = 1")
        assert tree is not None
        assert _ast_has_global_stmt(tree) is True

    def test_global_stmt_absent(self) -> None:
        tree = _try_parse_ast("def f():\n    _local = 1")
        assert tree is not None
        assert _ast_has_global_stmt(tree) is False

    def test_bare_except_pass(self) -> None:
        tree = _try_parse_ast("try:\n    x()\nexcept:\n    pass")
        assert tree is not None
        assert _ast_has_bare_except_pass(tree) is True

    def test_typed_except_not_flagged(self) -> None:
        tree = _try_parse_ast("try:\n    x()\nexcept ValueError:\n    pass")
        assert tree is not None
        assert _ast_has_bare_except_pass(tree) is False

    def test_try_without_handler(self) -> None:
        code = "try:\n    x()\nexcept ValueError:\n    pass"
        tree = _try_parse_ast(code)
        assert tree is not None
        assert _ast_try_without_handler(tree) is False

    def test_try_without_handler_via_checker(self) -> None:
        """Standalone try without except/finally — detected via checker."""
        result = _check_t06_exception_safety("try:\n    x()")
        assert not result.passed

    def test_try_with_except(self) -> None:
        tree = _try_parse_ast("try:\n    x()\nexcept Exception:\n    pass")
        assert tree is not None
        assert _ast_try_without_handler(tree) is False

    def test_try_with_finally(self) -> None:
        tree = _try_parse_ast("try:\n    x()\nfinally:\n    cleanup()")
        assert tree is not None
        assert _ast_try_without_handler(tree) is False

    def test_eval_call(self) -> None:
        tree = _try_parse_ast("result = eval(user_input)")
        assert tree is not None
        assert _ast_has_eval_call(tree) is True

    def test_exec_call(self) -> None:
        tree = _try_parse_ast("exec(code_string)")
        assert tree is not None
        assert _ast_has_eval_call(tree) is True

    def test_no_eval(self) -> None:
        tree = _try_parse_ast("result = int(user_input)")
        assert tree is not None
        assert _ast_has_eval_call(tree) is False

    def test_open_without_with(self) -> None:
        tree = _try_parse_ast("f = open('test.txt')\ndata = f.read()")
        assert tree is not None
        assert _ast_open_without_context_manager(tree) is True

    def test_open_with_with(self) -> None:
        tree = _try_parse_ast("with open('test.txt') as f:\n    data = f.read()")
        assert tree is not None
        assert _ast_open_without_context_manager(tree) is False

    def test_open_with_close(self) -> None:
        tree = _try_parse_ast("f = open('x')\ndata = f.read()\nf.close()")
        assert tree is not None
        assert _ast_open_without_context_manager(tree) is False

    def test_open_with_finally_close(self) -> None:
        tree = _try_parse_ast("f = open('x')\ntry:\n    pass\nfinally:\n    f.close()")
        assert tree is not None
        assert _ast_open_without_context_manager(tree) is False

    def test_http_without_status_check(self) -> None:
        tree = _try_parse_ast("import requests\nr = requests.get(url)\ndata = r.json()")
        assert tree is not None
        assert _ast_http_request_without_status_check(tree) is True

    def test_http_with_raise_for_status(self) -> None:
        tree = _try_parse_ast("import requests\nr = requests.get(url)\nr.raise_for_status()")
        assert tree is not None
        assert _ast_http_request_without_status_check(tree) is False

    def test_http_with_status_code(self) -> None:
        tree = _try_parse_ast("import requests\nr = requests.get(url)\nif r.status_code == 200: pass")
        assert tree is not None
        assert _ast_http_request_without_status_check(tree) is False

    def test_external_input_without_validation(self) -> None:
        tree = _try_parse_ast("x = input('cmd: ')\nos.system(x)")
        assert tree is not None
        assert _ast_external_input_without_validation(tree) is True

    def test_external_input_with_validation(self) -> None:
        tree = _try_parse_ast("x = input('num: ')\nval = int(x)")
        assert tree is not None
        assert _ast_external_input_without_validation(tree) is False

    def test_request_args_without_validation(self) -> None:
        tree = _try_parse_ast("data = request.args['key']\nos.system(data)")
        assert tree is not None
        assert _ast_external_input_without_validation(tree) is True


# ═══════════════════════════════════════════════════════════════════
# Regex Fallback Path (invalid syntax triggers regex)
# ═══════════════════════════════════════════════════════════════════

class TestRegexFallbackPath:
    """When AST parsing fails, checkers should fall back to regex."""

    INVALID_SYNTAX = "def f( ::: broken syntax"

    def test_t01_regex_detects_random(self) -> None:
        code = self.INVALID_SYNTAX + "\nimport random\nrandom.choice([1,2])"
        result = _check_t01_determinism(code)
        assert not result.passed

    def test_t01_regex_passes_clean(self) -> None:
        code = self.INVALID_SYNTAX + "\nresult = 42"
        result = _check_t01_determinism(code)
        assert result.passed

    def test_t03_regex_detects_eval(self) -> None:
        code = self.INVALID_SYNTAX + "\nresult = eval(x)"
        result = _check_t03_type_safety(code)
        assert not result.passed

    def test_t04_regex_detects_while_true(self) -> None:
        code = self.INVALID_SYNTAX + "\nwhile True:\n    work()"
        result = _check_t04_termination(code)
        assert not result.passed

    def test_t04_regex_while_true_with_break_passes(self) -> None:
        code = self.INVALID_SYNTAX + "\nwhile True:\n    break"
        result = _check_t04_termination(code)
        assert result.passed

    def test_t05_regex_detects_global(self) -> None:
        code = self.INVALID_SYNTAX + "\nglobal x\nx = 1"
        result = _check_t05_state_isolation(code)
        assert not result.passed

    def test_t06_regex_detects_bare_except(self) -> None:
        code = self.INVALID_SYNTAX + "\nexcept: pass"
        result = _check_t06_exception_safety(code)
        assert not result.passed

    def test_t08_regex_detects_unguarded_open(self) -> None:
        code = self.INVALID_SYNTAX + "\nf = open('x')\ndata = f.read()"
        result = _check_t08_resource_lifecycle(code)
        assert not result.passed

    def test_t08_regex_with_statement_passes(self) -> None:
        code = self.INVALID_SYNTAX + "\nwith open('x') as f:\n    data = f.read()"
        result = _check_t08_resource_lifecycle(code)
        assert result.passed

    def test_t09_regex_detects_no_status_check(self) -> None:
        code = self.INVALID_SYNTAX + "\nrequests.get(url)\ndata = r.json()"
        result = _check_t09_contract_adherence(code)
        assert not result.passed

    def test_t10_regex_detects_raw_input(self) -> None:
        code = self.INVALID_SYNTAX + "\nx = input('>')\nos.system(x)"
        result = _check_t10_trust_boundary(code)
        assert not result.passed


# ═══════════════════════════════════════════════════════════════════
# T07 Fail Case (audit gap: was missing)
# ═══════════════════════════════════════════════════════════════════

class TestT07IdempotencyFail:
    """T07 checker should detect non-idempotent patterns."""

    def test_t07_fail_append_in_idempotent_context(self) -> None:
        code = "# idempotent operation\ndef apply(lst, val):\n    lst.append(val)"
        result = _check_t07_idempotency(code)
        assert not result.passed

    def test_t07_pass_no_mutating_append(self) -> None:
        code = "def add_item(lst, val):\n    return lst + [val]"
        result = _check_t07_idempotency(code)
        assert result.passed

    def test_t07_pass_set_operation(self) -> None:
        code = "def f(x):\n    return abs(x)"
        result = _check_t07_idempotency(code)
        assert result.passed


# ═══════════════════════════════════════════════════════════════════
# CA4 Strict Mode Environment Gate
# ═══════════════════════════════════════════════════════════════════

class TestCA4StrictMode:
    """BUTLER_CODING_STRICT env gate (CA4)."""

    def test_coding_strict_default_off(self) -> None:
        from butler.dev_engine.dev_tools import coding_strict_enabled
        old = os.environ.pop("BUTLER_CODING_STRICT", None)
        try:
            assert coding_strict_enabled() is False
        finally:
            if old is not None:
                os.environ["BUTLER_CODING_STRICT"] = old

    def test_coding_strict_on(self) -> None:
        from butler.dev_engine.dev_tools import coding_strict_enabled
        old = os.environ.get("BUTLER_CODING_STRICT")
        os.environ["BUTLER_CODING_STRICT"] = "1"
        try:
            assert coding_strict_enabled() is True
        finally:
            if old is None:
                del os.environ["BUTLER_CODING_STRICT"]
            else:
                os.environ["BUTLER_CODING_STRICT"] = old

    def test_coding_strict_accepts_true(self) -> None:
        from butler.dev_engine.dev_tools import coding_strict_enabled
        old = os.environ.get("BUTLER_CODING_STRICT")
        os.environ["BUTLER_CODING_STRICT"] = "true"
        try:
            assert coding_strict_enabled() is True
        finally:
            if old is None:
                del os.environ["BUTLER_CODING_STRICT"]
            else:
                os.environ["BUTLER_CODING_STRICT"] = old


# ═══════════════════════════════════════════════════════════════════
# auto_verify Theorem Gate Integration
# ═══════════════════════════════════════════════════════════════════

class TestAutoVerifyTheoremGate:
    """Verify that auto_verify includes theorem checking (CA4 integration)."""

    def test_auto_verify_with_activated_theorems(self) -> None:
        from butler.dev_engine.dev_state import (
            CodingKnowledgeSummary,
            DevPhase,
            DevState,
            EditRecord,
        )

        state = DevState()
        state.phase = DevPhase.EDIT
        state.coding_knowledge = CodingKnowledgeSummary(mode="theorem_only")

        tlib = TheoremLibrary()
        state._coding_knowledge_theorems = {"T05": tlib.get("T05")}

        state.edit_history = [
            EditRecord(
                path="/tmp/test.py",
                operation="write",
                timestamp=time.time(),
                new_content="global shared\nshared = {}",
            )
        ]

        from butler.core.tool_batch import _run_auto_verify
        _run_auto_verify(state, "/tmp/test.py")

        assert "T05" in state.coding_knowledge.violated_theorems


# ═══════════════════════════════════════════════════════════════════
# Experience Persistence Round-Trip with Validation
# ═══════════════════════════════════════════════════════════════════

class TestExperiencePersistenceEnhanced:
    """Extended round-trip and validation tests."""

    def test_roundtrip_preserves_benchmarks(self) -> None:
        xlib = ExperienceLibrary()
        exp = CodingExperience(
            id="E_bench", title="Benchmarked",
            domain=["Python"], theorem_basis={"T05", "T06"},
            context="cache with bench", pattern="pass",
            benchmarks={"latency_ms": "12", "throughput": "1000/s"},
            validity_start=100.0, validity_end=999999.0,
        )
        xlib.add(exp, skip_validation=True)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            xlib.save_to_file(path)
            loaded = ExperienceLibrary.load_from_file(path)
            reloaded = loaded.get("E_bench")
            assert reloaded is not None
            assert reloaded.benchmarks == {"latency_ms": "12", "throughput": "1000/s"}
            assert reloaded.validity_start == 100.0
            assert reloaded.validity_end == 999999.0
        finally:
            os.unlink(path)

    def test_roundtrip_preserves_supersedes(self) -> None:
        xlib = ExperienceLibrary()
        old = CodingExperience(
            id="E_old", title="Old", domain=["Python"],
            theorem_basis={"T05"}, context="old", pattern="pass",
        )
        new = CodingExperience(
            id="E_new", title="New", domain=["Python"],
            theorem_basis={"T05", "T06"}, context="new", pattern="pass",
        )
        xlib.add(old, skip_validation=True)
        xlib.replace("E_old", new, skip_validation=True)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            xlib.save_to_file(path)
            loaded = ExperienceLibrary.load_from_file(path)
            reloaded = loaded.get("E_new")
            assert reloaded is not None
            assert reloaded.supersedes == "E_old"
        finally:
            os.unlink(path)

    def test_extract_then_persist_then_select(self) -> None:
        """Full pipeline: extract → save → load → select in process_task."""
        tlib = TheoremLibrary()
        activated = {"T05": tlib.get("T05")}
        code = "def cached_fn():\n    _cache = {}\n    return _cache.get('key', None)"

        candidate = extract_experience_candidate(
            task_description="cache state management pattern",
            code_snippets=[code],
            activated_theorems=activated,
            domain=["Python", "cache"],
        )
        assert candidate is not None

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            xlib = ExperienceLibrary(theorem_lib=tlib)
            ok, _ = xlib.add(candidate, skip_validation=True)
            assert ok
            xlib.save_to_file(path)

            loaded_xlib = ExperienceLibrary.load_from_file(path, theorem_lib=tlib)
            assert loaded_xlib.count == 1

            ctx = process_task(
                ["cache", "state"], tlib, loaded_xlib,
                strict_experience=False,
            )
            assert ctx.selected_experience is not None
            assert ctx.mode == "experience_guided"
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════
# ChromaDB Integration (conditional — skip if not installed)
# ═══════════════════════════════════════════════════════════════════

class TestChromaDBIntegration:
    """ChromaDB vector store integration tests."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_chromadb(self) -> None:
        try:
            import chromadb  # noqa: F401
        except ImportError:
            pytest.skip("chromadb not installed")

    def test_get_vector_store_returns_chroma(self) -> None:
        from butler.memory.vector_store import get_vector_store
        store = get_vector_store()
        assert "chroma" in type(store).__name__.lower() or hasattr(store, "_collection")

    def test_chroma_add_and_query(self) -> None:
        from butler.memory.vector_store import get_vector_store
        store = get_vector_store()
        store.add("test-chroma-1", "Hello world embedding test", {"source": "test"})
        results = store.query("Hello world", top_k=1)
        assert len(results) >= 1

    def test_chroma_delete(self) -> None:
        from butler.memory.vector_store import get_vector_store
        store = get_vector_store()
        store.add("test-chroma-del", "Delete me", {"source": "test"})
        store.delete("test-chroma-del")


# ═══════════════════════════════════════════════════════════════════
# fastembed Integration (conditional — skip if not installed)
# ═══════════════════════════════════════════════════════════════════

class TestFastembedIntegration:
    """fastembed local embedding integration tests."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_fastembed(self) -> None:
        try:
            import fastembed  # noqa: F401
        except ImportError:
            pytest.skip("fastembed not installed")

    def test_fastembed_provider_creates(self) -> None:
        old = os.environ.get("BUTLER_EMBEDDING_PROVIDER")
        os.environ["BUTLER_EMBEDDING_PROVIDER"] = "fastembed"
        try:
            from butler.memory.embedding import get_embedder
            embedder = get_embedder()
            name = type(embedder).__name__.lower()
            inner = getattr(embedder, "_inner", None)
            inner_name = type(inner).__name__.lower() if inner else ""
            assert "fastembed" in name or "fastembed" in inner_name or \
                   "cached" in name, \
                f"Expected fastembed-backed embedder, got {name}"
        finally:
            if old is None:
                del os.environ["BUTLER_EMBEDDING_PROVIDER"]
            else:
                os.environ["BUTLER_EMBEDDING_PROVIDER"] = old

    def test_fastembed_produces_vectors(self) -> None:
        old = os.environ.get("BUTLER_EMBEDDING_PROVIDER")
        os.environ["BUTLER_EMBEDDING_PROVIDER"] = "fastembed"
        try:
            from butler.memory.embedding import get_embedder
            embedder = get_embedder()
            vec = embedder.embed("Hello world test")
            assert len(vec) > 0
            assert all(isinstance(v, float) for v in vec)
        finally:
            if old is None:
                del os.environ["BUTLER_EMBEDDING_PROVIDER"]
            else:
                os.environ["BUTLER_EMBEDDING_PROVIDER"] = old

    def test_fastembed_dimension_consistency(self) -> None:
        old = os.environ.get("BUTLER_EMBEDDING_PROVIDER")
        os.environ["BUTLER_EMBEDDING_PROVIDER"] = "fastembed"
        try:
            from butler.memory.embedding import get_embedder
            embedder = get_embedder()
            v1 = embedder.embed("First text")
            v2 = embedder.embed("Second text")
            assert len(v1) == len(v2)
        finally:
            if old is None:
                del os.environ["BUTLER_EMBEDDING_PROVIDER"]
            else:
                os.environ["BUTLER_EMBEDDING_PROVIDER"] = old
