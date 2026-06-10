"""Engineering bridge tests — validates G1-G3 integration.

G1: CodingKnowledge ↔ DevLoop bridge (D3-7)
G2: PIM state injection into memory prefetch
G3: Experience library persistence + candidate extraction
"""

from __future__ import annotations

import json
import os
import tempfile
import time

import pytest


# ═══════════════════════════════════════════════════════════════════
# G1: DevState + CodingKnowledgeSummary
# ═══════════════════════════════════════════════════════════════════

class TestG1DevStateCodingKnowledge:

    def test_default_coding_knowledge_empty(self) -> None:
        from butler.dev_engine.dev_state import DevState
        ds = DevState()
        assert ds.coding_knowledge.mode == ""
        assert ds.coding_knowledge.activated_theorem_ids == []

    def test_coding_knowledge_summary_to_dict(self) -> None:
        from butler.dev_engine.dev_state import CodingKnowledgeSummary
        ck = CodingKnowledgeSummary(
            mode="theorem_only",
            activated_theorem_ids=["T05", "T06"],
            activated_elements=["StateManagement", "ErrorHandling"],
        )
        d = ck.to_dict()
        assert d["mode"] == "theorem_only"
        assert d["theorems"] == ["T05", "T06"]
        assert "experience" not in d

    def test_coding_knowledge_with_experience(self) -> None:
        from butler.dev_engine.dev_state import CodingKnowledgeSummary
        ck = CodingKnowledgeSummary(
            mode="experience_guided",
            activated_theorem_ids=["T05"],
            experience_id="EX_abc",
            experience_title="cache pattern",
        )
        d = ck.to_dict()
        assert d["experience"]["id"] == "EX_abc"

    def test_devstate_includes_knowledge_in_dict(self) -> None:
        from butler.dev_engine.dev_state import CodingKnowledgeSummary, DevState
        ds = DevState()
        ds.coding_knowledge = CodingKnowledgeSummary(
            mode="theorem_only",
            activated_theorem_ids=["T03", "T10"],
        )
        d = ds.to_dict()
        assert "coding_knowledge" in d
        assert d["coding_knowledge"]["mode"] == "theorem_only"

    def test_devstate_summary_includes_knowledge(self) -> None:
        from butler.dev_engine.dev_state import CodingKnowledgeSummary, DevState
        ds = DevState()
        ds.coding_knowledge = CodingKnowledgeSummary(
            mode="theorem_only",
            activated_theorem_ids=["T05", "T06", "T08"],
        )
        summary = ds.summary()
        assert "知识层" in summary
        assert "3 定理" in summary

    def test_devstate_empty_knowledge_not_in_dict(self) -> None:
        from butler.dev_engine.dev_state import DevState
        ds = DevState()
        d = ds.to_dict()
        assert "coding_knowledge" not in d


class TestG1ContextBlockInjection:

    def test_context_block_includes_theorems(self) -> None:
        from butler.dev_engine.dev_context import dev_state_context_block
        from butler.dev_engine.dev_state import CodingKnowledgeSummary, DevState

        ds = DevState()
        ds.coding_knowledge = CodingKnowledgeSummary(
            mode="theorem_only",
            activated_theorem_ids=["T05", "T06"],
            activated_elements=["StateManagement"],
        )
        block = dev_state_context_block(ds)
        assert "coding_knowledge_mode: theorem_only" in block
        assert "T05" in block
        assert "StateManagement" in block

    def test_context_block_includes_violations(self) -> None:
        from butler.dev_engine.dev_context import dev_state_context_block
        from butler.dev_engine.dev_state import CodingKnowledgeSummary, DevState

        ds = DevState()
        ds.coding_knowledge = CodingKnowledgeSummary(
            mode="theorem_only",
            activated_theorem_ids=["T05"],
            violated_theorems=["T05"],
        )
        block = dev_state_context_block(ds)
        assert "violated_theorems" in block
        assert "T05" in block

    def test_context_block_empty_knowledge_no_extras(self) -> None:
        from butler.dev_engine.dev_context import dev_state_context_block
        from butler.dev_engine.dev_state import DevState

        ds = DevState()
        block = dev_state_context_block(ds)
        assert "coding_knowledge_mode" not in block


class TestG1DualVerifyInDevTools:

    def test_tool_dev_verify_returns_theorem_violations_key(self) -> None:
        """Verify that theorem_violations key appears when violations exist."""
        from butler.dev_engine.dev_state import (
            CodingKnowledgeSummary,
            DevState,
            EditRecord,
        )
        from butler.dev_engine.dev_tools import _active_states, set_state

        ds = DevState(task_description="test task")
        ds.coding_knowledge = CodingKnowledgeSummary(
            mode="theorem_only",
            activated_theorem_ids=["T05"],
        )
        from butler.dev_engine.coding_knowledge import TheoremLibrary
        ds._coding_knowledge_theorems = {
            "T05": TheoremLibrary().get("T05"),
        }
        ds.edit_history.append(EditRecord(
            operation="write",
            path="test.py",
            new_content="global shared\nshared = {}",
        ))

        set_state("_test_g1", ds)
        try:
            from unittest.mock import patch
            with patch("butler.dev_engine.verify.verify_layered") as mock_verify:
                from butler.dev_engine.dev_state import VerifyResult, VerifyStatus
                mock_verify.return_value = VerifyResult(status=VerifyStatus.PASS)
                result = __import__(
                    "butler.dev_engine.dev_tools", fromlist=["tool_dev_verify"]
                ).tool_dev_verify("/tmp", session_key="_test_g1")
            assert "theorem_violations" in result
            assert "T05" in result["theorem_violations"]
        finally:
            _active_states.pop("_test_g1", None)


# ═══════════════════════════════════════════════════════════════════
# G2: PIM State Injection
# ═══════════════════════════════════════════════════════════════════

class TestG2PIMStateInjection:

    def test_pim_summary_line_nonempty(self) -> None:
        from butler.core.pim_state import DomainIndex, PIMState
        state = PIMState()
        state.memos = DomainIndex(count=5, last_modified=time.time())
        line = state.summary_line()
        assert "memos=5" in line

    def test_pim_summary_line_empty(self) -> None:
        from butler.core.pim_state import PIMState
        assert PIMState().summary_line() == "(empty)"


# ═══════════════════════════════════════════════════════════════════
# G3: Experience Library Persistence
# ═══════════════════════════════════════════════════════════════════

class TestG3ExperiencePersistence:

    def test_save_and_load_roundtrip(self) -> None:
        from butler.dev_engine.coding_knowledge import (
            CodingExperience,
            ExperienceLibrary,
        )

        lib = ExperienceLibrary()
        lib.add(CodingExperience(
            id="E001", title="Cache", domain=["Python"],
            theorem_basis={"T05", "T06"}, context="caching",
            pattern="def cache(f): pass",
            validity_start=100.0, validity_end=999999.0,
        ), skip_validation=True)
        lib.add(CodingExperience(
            id="E002", title="File IO", domain=["Python"],
            theorem_basis={"T08"}, context="file handling",
            pattern="with open(f) as fh: pass",
        ), skip_validation=True)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            lib.save_to_file(path)

            loaded = ExperienceLibrary.load_from_file(path)
            assert loaded.count == 2
            assert loaded.get("E001") is not None
            assert loaded.get("E001").title == "Cache"
            assert loaded.get("E002").theorem_basis == {"T08"}
        finally:
            os.unlink(path)

    def test_load_nonexistent_returns_empty(self) -> None:
        from butler.dev_engine.coding_knowledge import ExperienceLibrary
        lib = ExperienceLibrary.load_from_file("/nonexistent/path.json")
        assert lib.count == 0

    def test_load_corrupted_returns_empty(self) -> None:
        from butler.dev_engine.coding_knowledge import ExperienceLibrary
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w",
                                          delete=False) as f:
            f.write("not valid json {{{")
            path = f.name
        try:
            lib = ExperienceLibrary.load_from_file(path)
            assert lib.count == 0
        finally:
            os.unlink(path)

    def test_save_creates_parent_dirs(self) -> None:
        from butler.dev_engine.coding_knowledge import ExperienceLibrary
        lib = ExperienceLibrary()
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "sub", "deep", "lib.json")
            lib.save_to_file(path)
            assert os.path.isfile(path)


class TestG3ExperienceCandidateExtraction:

    def test_extract_from_successful_task(self) -> None:
        from butler.dev_engine.coding_knowledge import (
            TheoremLibrary,
            extract_experience_candidate,
        )
        tlib = TheoremLibrary()
        activated = {"T05": tlib.get("T05")}
        code = "def safe_fn():\n    _local = {}\n    return _local"

        candidate = extract_experience_candidate(
            "implement local cache", [code], activated,
        )
        assert candidate is not None
        assert candidate.id.startswith("EX_")
        assert "T05" in candidate.theorem_basis
        assert candidate.validity_end > time.time()

    def test_extract_rejects_violating_code(self) -> None:
        from butler.dev_engine.coding_knowledge import (
            TheoremLibrary,
            extract_experience_candidate,
        )
        tlib = TheoremLibrary()
        activated = {"T05": tlib.get("T05")}
        code = "global shared\nshared = {}"

        candidate = extract_experience_candidate(
            "bad task", [code], activated,
        )
        assert candidate is None

    def test_extract_returns_none_for_empty(self) -> None:
        from butler.dev_engine.coding_knowledge import extract_experience_candidate
        assert extract_experience_candidate("", [], {}) is None

    def test_extract_returns_none_for_short_snippet(self) -> None:
        from butler.dev_engine.coding_knowledge import (
            TheoremLibrary,
            extract_experience_candidate,
        )
        tlib = TheoremLibrary()
        activated = {"T03": tlib.get("T03")}
        assert extract_experience_candidate("x", ["x=1"], activated) is None
