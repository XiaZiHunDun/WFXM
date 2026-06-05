"""R2-7 regression: post-session per-item errors must surface to result/diagnostics.

Audit (project-deep-audit-2026-06-r1to8 §R2-7):
``butler/session/post_session.py:357-358, 412-413`` swallowed per-item exceptions
into ``logger.warning`` only. Users could never tell that memory distillation or
skill extraction was silently failing for every conversation.

Required behavior:
1. Per-item exceptions are logged with ``logger.error(..., exc_info=exc)`` —
   never plain ``logger.warning`` for these two sites.
2. Per-item errors are appended to ``result["errors"]`` (via a shared list).
3. ``result["memory_failed"]`` and ``result["skills_failed"]`` expose the
   per-channel failure counts for ``/诊断``.
4. Existing keys ``memory_updates`` / ``skills_extracted`` remain ``int``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from unittest.mock import MagicMock

import pytest

from butler.session.post_session import PostSessionProcessor


def _long_messages() -> list[dict]:
    filler = "x" * 120
    return [
        {"role": "user", "content": filler},
        {"role": "assistant", "content": filler},
        {"role": "user", "content": filler},
        {"role": "assistant", "content": filler},
    ]


def _mem_response_two_updates() -> str:
    return json.dumps(
        {
            "updates": [
                {"target": "butler", "content": "prefers dark mode"},
                {"target": "butler", "content": "prefers a 27 inch monitor"},
            ]
        }
    )


def _skill_response_two_skills() -> str:
    return json.dumps(
        {
            "skills": [
                {
                    "name": "deploy-flow",
                    "description": "Deploy steps",
                    "triggers": ["deploy"],
                    "body": "Step 1: build\nStep 2: ship",
                },
                {
                    "name": "rollback-flow",
                    "description": "Rollback steps",
                    "triggers": ["rollback"],
                    "body": "Step 1: revert\nStep 2: verify",
                },
            ]
        }
    )


def _butler_memory_one_failing(failure_msg: str = "vector store offline"):
    bm = MagicMock()  # noqa: magicmock-no-spec — post_session memory facade
    # First add succeeds, second add raises -> per-item failure
    bm.profile.add.side_effect = [{"success": True}, RuntimeError(failure_msg)]
    return bm


def _skill_manager_one_failing(failure_msg: str = "disk full"):
    sm = MagicMock()  # noqa: magicmock-no-spec — post_session skill manager facade
    sm.list_skills.return_value = []
    # First create succeeds, second raises -> per-item failure
    sm.create.side_effect = [None, RuntimeError(failure_msg)]
    return sm


@pytest.mark.module_test
class TestMemoryPerItemErrors:
    def test_memory_per_item_error_appended_to_result_errors(self):
        async def llm_call(prompt):
            return _mem_response_two_updates()

        butler_memory = _butler_memory_one_failing("vector store offline")
        proc = PostSessionProcessor(llm_call=llm_call)

        result = asyncio.run(
            proc.process(
                messages=_long_messages(),
                butler_memory=butler_memory,
            )
        )

        joined = " | ".join(result["errors"])
        assert "vector store offline" in joined, (
            f"per-item failure should surface in result['errors']; got {result['errors']!r}"
        )

    def test_memory_failed_count_in_result(self):
        async def llm_call(prompt):
            return _mem_response_two_updates()

        butler_memory = _butler_memory_one_failing("kaboom")
        proc = PostSessionProcessor(llm_call=llm_call)

        result = asyncio.run(
            proc.process(
                messages=_long_messages(),
                butler_memory=butler_memory,
            )
        )

        assert "memory_failed" in result, "result must expose memory_failed for /诊断"
        assert result["memory_failed"] >= 1
        # Successful one still counted as applied
        assert result["memory_updates"] >= 1
        assert isinstance(result["memory_updates"], int)
        assert isinstance(result["memory_failed"], int)

    def test_memory_per_item_logs_error_with_exc_info(self, caplog):
        async def llm_call(prompt):
            return _mem_response_two_updates()

        butler_memory = _butler_memory_one_failing("vector kaboom")
        proc = PostSessionProcessor(llm_call=llm_call)

        with caplog.at_level(logging.DEBUG, logger="butler.session.post_session"):
            asyncio.run(
                proc.process(
                    messages=_long_messages(),
                    butler_memory=butler_memory,
                )
            )

        error_records = [
            r
            for r in caplog.records
            if r.name == "butler.session.post_session"
            and r.levelno >= logging.ERROR
            and r.exc_info is not None
        ]
        assert error_records, (
            "per-item memory failure must logger.error(..., exc_info=exc); "
            f"saw records {[(r.levelname, r.getMessage(), r.exc_info is not None) for r in caplog.records]}"
        )


@pytest.mark.module_test
class TestSkillPerItemErrors:
    def test_skill_per_item_error_appended_to_result_errors(self):
        async def llm_call(prompt):
            if "skill" in prompt.lower() or "skills" in prompt.lower():
                return _skill_response_two_skills()
            return '{"updates": []}'

        skill_manager = _skill_manager_one_failing("disk full")
        proc = PostSessionProcessor(llm_call=llm_call)

        result = asyncio.run(
            proc.process(
                messages=_long_messages(),
                skill_manager=skill_manager,
            )
        )

        joined = " | ".join(result["errors"])
        assert "disk full" in joined, (
            f"per-item skill failure should surface; got {result['errors']!r}"
        )

    def test_skill_failed_count_in_result(self):
        async def llm_call(prompt):
            if "skill" in prompt.lower() or "skills" in prompt.lower():
                return _skill_response_two_skills()
            return '{"updates": []}'

        skill_manager = _skill_manager_one_failing("disk kaboom")
        proc = PostSessionProcessor(llm_call=llm_call)

        result = asyncio.run(
            proc.process(
                messages=_long_messages(),
                skill_manager=skill_manager,
            )
        )

        assert "skills_failed" in result, "result must expose skills_failed for /诊断"
        assert result["skills_failed"] >= 1
        assert result["skills_extracted"] >= 1
        assert isinstance(result["skills_extracted"], int)
        assert isinstance(result["skills_failed"], int)

    def test_skill_per_item_logs_error_with_exc_info(self, caplog):
        async def llm_call(prompt):
            if "skill" in prompt.lower() or "skills" in prompt.lower():
                return _skill_response_two_skills()
            return '{"updates": []}'

        skill_manager = _skill_manager_one_failing("disk kaboom")
        proc = PostSessionProcessor(llm_call=llm_call)

        with caplog.at_level(logging.DEBUG, logger="butler.session.post_session"):
            asyncio.run(
                proc.process(
                    messages=_long_messages(),
                    skill_manager=skill_manager,
                )
            )

        error_records = [
            r
            for r in caplog.records
            if r.name == "butler.session.post_session"
            and r.levelno >= logging.ERROR
            and r.exc_info is not None
        ]
        assert error_records, (
            "per-item skill failure must logger.error(..., exc_info=exc); "
            f"saw records {[(r.levelname, r.getMessage(), r.exc_info is not None) for r in caplog.records]}"
        )


@pytest.mark.module_test
class TestNoWarningRegression:
    def test_no_warning_level_for_per_item_errors(self, caplog):
        """Both old logger.warning sites must be upgraded to logger.error."""

        async def llm_call(prompt):
            if "skill" in prompt.lower() or "skills" in prompt.lower():
                return _skill_response_two_skills()
            return _mem_response_two_updates()

        butler_memory = _butler_memory_one_failing("mem boom")
        skill_manager = _skill_manager_one_failing("skill boom")
        proc = PostSessionProcessor(llm_call=llm_call)

        with caplog.at_level(logging.DEBUG, logger="butler.session.post_session"):
            asyncio.run(
                proc.process(
                    messages=_long_messages(),
                    butler_memory=butler_memory,
                    skill_manager=skill_manager,
                )
            )

        warnings = [
            r
            for r in caplog.records
            if r.name == "butler.session.post_session"
            and r.levelno == logging.WARNING
            and (
                "Memory update error" in r.getMessage()
                or "Skill creation error" in r.getMessage()
            )
        ]
        assert not warnings, (
            "R2-7: per-item failures must not be downgraded to WARNING anymore; "
            f"saw {[r.getMessage() for r in warnings]}"
        )


@pytest.mark.module_test
class TestDiagnosticsSurfacesFailures:
    def test_diagnostics_surfaces_failure_counts(self):
        """End-to-end: one success + one failure per channel both reflected in /诊断 keys."""

        async def llm_call(prompt):
            if "skill" in prompt.lower() or "skills" in prompt.lower():
                return _skill_response_two_skills()
            return _mem_response_two_updates()

        butler_memory = _butler_memory_one_failing("mem went sideways")
        skill_manager = _skill_manager_one_failing("skill blew up")
        proc = PostSessionProcessor(llm_call=llm_call)

        result = asyncio.run(
            proc.process(
                messages=_long_messages(),
                butler_memory=butler_memory,
                skill_manager=skill_manager,
            )
        )

        assert result["memory_failed"] >= 1
        assert result["skills_failed"] >= 1
        assert result["memory_updates"] >= 1
        assert result["skills_extracted"] >= 1
        joined = " | ".join(result["errors"])
        assert "mem went sideways" in joined
        assert "skill blew up" in joined
