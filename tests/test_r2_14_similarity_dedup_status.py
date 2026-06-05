"""R2-14 [H] similarity dedup 主路径异常 — 区分 LLM 不可用 vs 响应损坏.

`butler/skills/similarity.py:218-221` (`_llm_similarity_score`):

    try:
        response = llm_fn(prompt).strip()
        m = re.search(r"\{[^{}]*\}", response, re.DOTALL)
        if not m: m = re.search(r"\{.*\}", response, re.DOTALL)
        if not m: return None
        data = json.loads(m.group())
        score = float(data.get("score", 0.0))
        ...
        return score
    except Exception as e:
        logger.warning("LLM similarity failed: %s", e)
        return None

问题:
1) llm_fn 抛异常 (网络/超时/401) → logger.warning + return None
2) 响应里压根没 JSON (LLM 返回 garbage) → return None
3) JSON 损坏 (json.loads 抛) → except → return None
4) 以上三种全部 → 后续 consolidator 把近似重复技能当作不同保留
5) 技能膨胀但用户无感, /诊断看不到 dedup 已降级

修复:
1) 区分 "LLM unavailable" (warn+None) vs "response corrupt" (raise)
2) 引入 SimilarityResponseCorrupt 异常
3) find_similar 捕获 corrupt → 记入 _dedup_status, 退到 medium_score (而不是默默)
4) Module-level diagnostics buffer + public reader recent_dedup_status()
5) Buffer 满后按 FIFO 丢弃旧 entry (与 R2-12/R2-13 一致)

行为保证:
1) LLM 抛异常 (unavailable) → 记入 status unavailable, 退到 medium_score
2) LLM 返回非 JSON (corrupt) → 记入 status corrupt, 退到 medium_score, log at ERROR with exc_info
3) 正常 LLM 响应 → 不污染 status buffer
4) Public reader + reset 接口可独立测试
5) Buffer cap FIFO 严格
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import pytest

from butler.skills.similarity import (
    _MAX_DEDUP_STATUS_ENTRIES,
    SimilarityLLMUnavailable,
    SimilarityResponseCorrupt,
    SkillSimilarity,
    _llm_similarity_score,
    recent_dedup_status,
    reset_dedup_status,
)


@pytest.fixture(autouse=True)
def _reset_dedup():
    """Reset the dedup status buffer between tests."""
    reset_dedup_status()
    yield
    reset_dedup_status()


# Helper: build a LLM function that returns a fixed string
def _llm_returning(text: str) -> Callable[[str], str]:
    return lambda _prompt: text


def _llm_raising(exc: Exception) -> Callable[[str], str]:
    def _fn(_prompt: str) -> str:
        raise exc
    return _fn


# A pair of skills that the deterministic (Jaccard / TF-IDF) layers will
# rank as similar — so we exercise the LLM tier when llm_fn is provided.
_SKILL_A = {
    "name": "alpha",
    "description": "Skill A handles python debugging workflow.",
    "triggers": ["python", "debug", "traceback"],
    "content": "Step 1: read the traceback carefully. Step 2: identify root cause.",
}
_SKILL_B = {
    "name": "alpha-2",
    "description": "Skill A-2 handles python debugging workflow.",
    "triggers": ["python", "debug", "exception"],
    "content": "Step 1: read the traceback carefully. Step 2: identify root cause.",
}


# -----------------------------------------------------------------------
# Test 1: distinguish unavailable (warn+None) from corrupt (raise+record)
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestCorruptRaises:
    """LLM 响应损坏 (没 JSON) 必须 raise SimilarityResponseCorrupt, 不能 return None 静默吞."""

    def test_no_json_in_response_raises(self):
        """LLM 返回纯文本 (无 JSON 块) → SimilarityResponseCorrupt."""
        llm = _llm_returning("Sorry, I cannot help with that.")
        with pytest.raises(SimilarityResponseCorrupt) as excinfo:
            _llm_similarity_score(_SKILL_A, _SKILL_B, llm)
        assert "no JSON" in str(excinfo.value) or "no json" in str(excinfo.value).lower()

    def test_garbage_braces_but_not_json_raises(self):
        """LLM 返回有花括号但非 JSON → raise (json.JSONDecodeError)."""
        llm = _llm_returning("{not valid json at all}")
        with pytest.raises(SimilarityResponseCorrupt):
            _llm_similarity_score(_SKILL_A, _SKILL_B, llm)

    def test_valid_json_returns_score(self):
        """正常 JSON 响应 → 返回 score, 不 raise."""
        llm = _llm_returning('{"score": 0.7, "similar": true, "reason": "very similar"}')
        score = _llm_similarity_score(_SKILL_A, _SKILL_B, llm)
        assert score == pytest.approx(0.7, abs=0.01)

    def test_exception_type_is_value_error_subclass(self):
        """SimilarityResponseCorrupt 应是 ValueError 子类 (catch-all 兼容)."""
        assert issubclass(SimilarityResponseCorrupt, ValueError)


@pytest.mark.unit
class TestUnavailableRaises:
    """LLM 抛异常 (网络/超时) → 抛 SimilarityLLMUnavailable, 保留原始 cause 信息."""

    def test_llm_raises_similarity_llm_unavailable(self):
        llm = _llm_raising(ConnectionError("network down"))
        with pytest.raises(SimilarityLLMUnavailable) as excinfo:
            _llm_similarity_score(_SKILL_A, _SKILL_B, llm)
        assert "network down" in str(excinfo.value)
        # __cause__ 保留原始异常
        assert isinstance(excinfo.value.__cause__, ConnectionError)

    def test_llm_raises_logs_warning(self, caplog):
        llm = _llm_raising(ConnectionError("network down"))
        with caplog.at_level(logging.DEBUG, logger="butler.skills.similarity"):
            with pytest.raises(SimilarityLLMUnavailable):
                _llm_similarity_score(_SKILL_A, _SKILL_B, llm)
        warning_records = [
            r for r in caplog.records
            if r.levelno == logging.WARNING and "similar" in r.message.lower()
        ]
        assert warning_records, (
            f"LLM unavailable 必须 log WARNING, 实际: "
            f"{[(r.levelname, r.message) for r in caplog.records]}"
        )


# -----------------------------------------------------------------------
# Test 2: find_similar catches corrupt, records status, falls back
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestFindSimilarRecordsStatus:
    """find_similar 捕获 corrupt → 记入 status, 退到 medium_score."""

    def test_corrupt_response_records_status_and_falls_back(self):
        llm = _llm_returning("Sorry I cannot help.")
        sim = SkillSimilarity(llm_fn=llm)
        results = sim.find_similar(_SKILL_A, [_SKILL_B], threshold=0.3)
        # 不抛异常, 走完流程
        assert isinstance(results, list)
        # 仍能返回结果 (退到 medium_score — Jaccard / TF-IDF)
        status = recent_dedup_status()
        corrupt = [e for e in status if e["kind"] == "corrupt"]
        assert len(corrupt) == 1, (
            f"corrupt 响应必须记入 status buffer, 实际: {status!r}"
        )
        assert "no JSON" in corrupt[0]["message"] or "corrupt" in corrupt[0]["message"].lower()

    def test_unavailable_records_status_with_unavailable_kind(self):
        llm = _llm_raising(ConnectionError("network down"))
        sim = SkillSimilarity(llm_fn=llm)
        sim.find_similar(_SKILL_A, [_SKILL_B], threshold=0.3)
        status = recent_dedup_status()
        unavailable = [e for e in status if e["kind"] == "unavailable"]
        assert len(unavailable) == 1
        assert "connection" in unavailable[0]["message"].lower() or "network" in unavailable[0]["message"].lower()

    def test_valid_response_does_not_pollute_buffer(self):
        llm = _llm_returning('{"score": 0.8, "similar": true}')
        sim = SkillSimilarity(llm_fn=llm)
        sim.find_similar(_SKILL_A, [_SKILL_B], threshold=0.3)
        assert recent_dedup_status() == [], (
            f"合法响应不应污染 status buffer, 实际: {recent_dedup_status()!r}"
        )

    def test_corrupt_logs_error_with_exc_info(self, caplog):
        llm = _llm_returning("not json at all")
        sim = SkillSimilarity(llm_fn=llm)
        with caplog.at_level(logging.DEBUG, logger="butler.skills.similarity"):
            sim.find_similar(_SKILL_A, [_SKILL_B], threshold=0.3)
        error_records = [
            r for r in caplog.records
            if r.levelno >= logging.ERROR and "dedup" in r.message.lower()
        ]
        assert error_records, (
            f"corrupt 必须 log at ERROR, 实际: "
            f"{[(r.levelname, r.message) for r in caplog.records]}"
        )
        assert any(r.exc_info is not None for r in error_records), (
            "corrupt 的 ERROR log 必须含 exc_info (traceback)"
        )


# -----------------------------------------------------------------------
# Test 3: public reader API
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestPublicReader:
    """recent_dedup_status / reset_dedup_status 必须存在并可独立测试."""

    def test_reader_empty_initially(self):
        assert recent_dedup_status() == []

    def test_reset_clears_buffer(self):
        sim = SkillSimilarity(llm_fn=_llm_returning("garbage"))
        sim.find_similar(_SKILL_A, [_SKILL_B], threshold=0.3)
        assert recent_dedup_status()
        reset_dedup_status()
        assert recent_dedup_status() == []

    def test_buffer_is_bounded(self, monkeypatch):
        """buffer 满后按 FIFO 丢弃旧 entry (防止长会话无限增长)."""
        from butler.skills import similarity as sim_mod
        original_cap = _MAX_DEDUP_STATUS_ENTRIES
        sim_mod._MAX_DEDUP_STATUS_ENTRIES = 3
        try:
            # 触发 5 次 corrupt, 验证最新 3 个保留
            sim = SkillSimilarity(llm_fn=_llm_returning("garbage"))
            for i in range(5):
                sim.find_similar(
                    {**_SKILL_A, "name": f"a-{i}"},
                    [{**_SKILL_B, "name": f"b-{i}"}],
                    threshold=0.0,
                )
            entries = recent_dedup_status()
            assert len(entries) == 3, (
                f"buffer 满后应严格 cap=3, 实际: {len(entries)}"
            )
            # FIFO: 最旧 2 个 (a-0, a-1) 应被丢弃
            assert all(
                "a-0" not in e["message"] and "a-1" not in e["message"]
                for e in entries
            ), f"最旧 2 个 entry 应被 FIFO 丢弃, 实际: {entries!r}"
        finally:
            sim_mod._MAX_DEDUP_STATUS_ENTRIES = original_cap


# -----------------------------------------------------------------------
# Test 4: constant is exposed
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestConstantExposed:
    """SimilarityResponseCorrupt 异常类必须导出 (供 caller 捕获)."""

    def test_exception_class_is_importable(self):
        assert SimilarityResponseCorrupt is not None
        # 异常类可实例化并保留 message
        e = SimilarityResponseCorrupt("test")
        assert "test" in str(e)
