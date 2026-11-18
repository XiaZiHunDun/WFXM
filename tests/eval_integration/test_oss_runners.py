"""OSS eval runner and sync policy tests."""

from __future__ import annotations

import json
from unittest.mock import patch

from butler.eval_integration.oss.bfcl_runner import (
    normalize_schema,
    run_bfcl_tool_eval,
    score_prediction,
)
from butler.eval_integration.oss.deepeval_runner import run_deterministic
from butler.eval_integration.oss.ragas_runner import (
    _case_passes,
    _contexts_of,
    _finite,
    _load_trace_cases,
    _retrieval_metrics,
    heuristic_faithfulness,
    run_heuristic,
)
from butler.eval_integration.sync_policy import evaluate_sync


def test_heuristic_faithfulness_overlap():
    ctx = "项目根目录为 /home/ailearn/projects/WFXM"
    ans = "根目录是 /home/ailearn/projects/WFXM"
    score = heuristic_faithfulness(ctx, ans)
    assert score > 0.3


def test_run_heuristic_passes_fixtures():
    ok, metrics = run_heuristic()
    assert ok
    assert metrics["mode"] in ("heuristic", "audit")
    assert metrics["cases_passed"] == metrics["cases_total"]


def test_load_prefetch_audit_cases_from_transcript(tmp_path, monkeypatch):
    from butler.eval_integration.oss.prefetch_audit_loader import load_prefetch_audit_cases

    sessions = tmp_path / "sessions" / "sess1"
    sessions.mkdir(parents=True)
    rows = [
        {"type": "user", "content_preview": "项目 Loop 在哪？"},
        {
            "type": "knowledge_inject",
            "source": "memory_prefetch",
            "chars": 120,
            "terms": ["butler/core/agent_loop.py"],
        },
        {"type": "assistant", "content_preview": "Loop 在 butler/core/agent_loop.py"},
    ]
    (sessions / "transcript.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "butler.eval_integration.oss.prefetch_audit_loader.get_butler_home",
        lambda: tmp_path,
    )
    cases = load_prefetch_audit_cases(limit_sessions=5)
    assert len(cases) == 1
    assert cases[0]["source"] == "transcript_audit"
    assert "agent_loop" in cases[0]["context"]


@patch("butler.eval_integration.oss.deepeval_runner.deepeval_available", return_value=True)
def test_deepeval_deterministic_passes(_mock_avail):
    ok, metrics = run_deterministic()
    assert ok
    assert metrics["mode"] == "deterministic"
    assert metrics["pass_rate"] == 1.0


def test_sync_check_missing_audit():
    out = evaluate_sync(
        "tcr",
        {"audit": None, "junit": {"ok": True}, "langfuse": None},
    )
    assert out["ok"] is False
    assert any("audit" in w for w in out["warnings"])


def test_sync_check_ok_mismatch():
    out = evaluate_sync(
        "tcr",
        {
            "audit": {"ok": True, "ts": 1.0},
            "junit": {"ok": False},
        },
    )
    assert out["ok"] is False
    assert any("mismatch" in w for w in out["warnings"])


def test_sync_check_all_present():
    out = evaluate_sync(
        "tcr",
        {
            "audit": {"ok": True, "ts": 1.0},
            "junit": {"ok": True},
        },
    )
    assert out["ok"] is True
    assert out["warnings"] == []


def test_ragas_contexts_and_finite_helpers():
    assert _contexts_of({"contexts": ["a", " ", "b"]}) == ["a", "b"]
    assert _contexts_of({"context": "ctx"}) == ["ctx"]
    assert _finite(float("nan")) is None
    assert _finite("bad") is None
    assert _finite(0.25) == 0.25


def test_ragas_case_thresholds():
    # 幻觉样例：faithfulness 低是预期结果，max 阈值不应误判。
    passed, failures = _case_passes(
        {"faithfulness": 0.0, "answer_relevancy": 0.9, "llm_context_precision_with_reference": 1.0},
        {"id": "reject", "max_faithfulness": 0.4},
        faithfulness_min=0.5,
        relevancy_min=0.5,
        precision_min=0.5,
    )
    assert passed, failures


def test_ragas_thresholds_tolerate_float_noise():
    # Ragas 可能返回 0.49999999995，数学上等于阈值，不应判失败。
    passed, failures = _case_passes(
        {
            "faithfulness": 1.0,
            "answer_relevancy": 1.0,
            "llm_context_precision_with_reference": 0.49999999995,
        },
        {"id": "edge"},
        faithfulness_min=0.5,
        relevancy_min=0.5,
        precision_min=0.5,
    )
    assert passed, failures


def test_ragas_negative_case_ignores_other_metrics():
    # 反例的 answer 故意错误，其它指标不应参与判定。
    passed, failures = _case_passes(
        {"faithfulness": 0.0, "answer_relevancy": 0.0, "llm_context_precision_with_reference": 0.0},
        {"id": "reject", "max_faithfulness": 0.4},
        faithfulness_min=0.5,
        relevancy_min=0.5,
        precision_min=0.5,
    )
    assert passed, failures

    passed, failures = _case_passes(
        {"faithfulness": 1.0, "answer_relevancy": 0.9, "llm_context_precision_with_reference": 0.0},
        {"id": "positive"},
        faithfulness_min=0.5,
        relevancy_min=0.5,
        precision_min=0.5,
    )
    assert not passed
    assert any("context_precision" in failure for failure in failures)


    passed, failures = _case_passes(
        {"faithfulness": 1.0, "answer_relevancy": 0.8, "llm_context_precision_with_reference": 0.2},
        {"id": "low-precision"},
        faithfulness_min=0.5,
        relevancy_min=0.5,
        precision_min=0.5,
    )
    assert not passed
    assert any("context_precision" in item for item in failures)


def test_load_trace_cases_from_agent_eval_artifacts(tmp_path):
    task = tmp_path / "run-1" / "cap-rag"
    task.mkdir(parents=True)
    events = [
        {"type": "turn.start", "payload": {"index": 0, "input": "部署流程是什么？"}},
        {
            "type": "rag.retrieve",
            "payload": {
                "scope": "document",
                "hits": [
                    {"text": "先灰度再全量。", "docId": "d1", "chunkId": "d1#0"},
                    {"text": "先灰度再全量。", "docId": "d1", "chunkId": "d1#0"},
                ],
            },
        },
    ]
    (task / "trace.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in events) + "\n",
        encoding="utf-8",
    )
    (task / "result.json").write_text(
        json.dumps({"reply": "先灰度再全量。"}, ensure_ascii=False),
        encoding="utf-8",
    )

    cases = _load_trace_cases(tmp_path)
    assert len(cases) == 1
    assert cases[0]["id"] == "cap-rag"
    assert cases[0]["question"] == "部署流程是什么？"
    assert cases[0]["contexts"] == ["先灰度再全量。"]
    assert cases[0]["answer"] == "先灰度再全量。"
    assert cases[0]["source"] == "agent_eval_trace"


def test_load_trace_cases_reads_rag_expectation_and_hits(tmp_path):
    task = tmp_path / "run-1" / "rag-task" / "attempt-1"
    task.mkdir(parents=True)
    events = [
        {"type": "turn.start", "payload": {"index": 0, "input": "端口是多少？"}},
        {
            "type": "rag.expectation",
            "payload": {
                "expectedDocTitles": ["部署手册"],
                "reference": "端口 18080。",
            },
        },
        {
            "type": "rag.retrieve",
            "payload": {
                "scope": "document",
                "hits": [
                    {"rank": 1, "title": "无关文档", "text": "别的上下文"},
                    {"rank": 2, "title": "部署手册", "text": "端口 18080", "docId": "d1"},
                ],
            },
        },
    ]
    (task / "trace.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in events) + "\n",
        encoding="utf-8",
    )
    (task / "result.json").write_text(
        json.dumps({"reply": "端口 18080。"}, ensure_ascii=False),
        encoding="utf-8",
    )

    cases = _load_trace_cases(tmp_path)
    assert len(cases) == 1
    case = cases[0]
    assert case["id"] == "rag-task/attempt-1"
    assert case["reference"] == "端口 18080。"
    assert case["expected_doc_titles"] == ["部署手册"]
    assert [hit["title"] for hit in case["retrieval_hits"]] == ["无关文档", "部署手册"]

    retrieval = _retrieval_metrics(cases)
    assert retrieval["cases_total"] == 1
    assert retrieval["hit_at_1"] == 0.0
    assert retrieval["hit_at_3"] == 1.0
    assert retrieval["mrr"] == 0.5


def test_retrieval_metrics_without_ground_truth_is_skipped():
    empty = _retrieval_metrics([{"id": "x", "expected_doc_titles": []}])
    assert empty == {"cases_total": 0, "reason": "no retrieval ground truth"}


def test_bfcl_score_prediction_accepts_defaults_and_numbers():
    ground_truth = [
        {
            "calculate_triangle_area": {
                "base": [10],
                "height": [5],
                "unit": ["units", ""],
            }
        }
    ]
    predicted = {"name": "calculate_triangle_area", "arguments": {"base": 10.0, "height": 5}}
    assert score_prediction(predicted, ground_truth) == (True, True)

    wrong_unit = {"name": "calculate_triangle_area", "arguments": {"base": 10, "height": 5, "unit": "cm"}}
    assert score_prediction(wrong_unit, ground_truth) == (True, False)

    wrong_name = {"name": "other", "arguments": {"base": 10, "height": 5}}
    assert score_prediction(wrong_name, ground_truth) == (False, False)


def test_bfcl_score_prediction_nested_and_numeric_strings():
    ground_truth = [
        {
            "database.query": {
                "table": ["user"],
                "limit": ["52"],
                "conditions": [
                    [
                        {"field": ["age"], "operation": [">"], "value": ["25"]},
                        {"field": ["job"], "operation": ["="], "value": ["engineer"]},
                    ]
                ],
            }
        }
    ]
    predicted = {
        "name": "database.query",
        "arguments": {
            "table": "user",
            "limit": 52,
            "conditions": [
                {"field": "age", "operation": ">", "value": "25"},
                {"field": "job", "operation": "=", "value": "engineer"},
            ],
        },
    }
    assert score_prediction(predicted, ground_truth) == (True, True)


def test_bfcl_normalize_schema_converts_bfcl_types():
    schema = normalize_schema(
        {
            "type": "dict",
            "properties": {
                "value": {"type": "float"},
                "items": {"type": "tuple", "items": {"type": "dict"}},
            },
            "required": ["value"],
        }
    )
    assert schema["type"] == "object"
    assert schema["properties"]["value"]["type"] == "number"
    assert schema["properties"]["items"]["items"]["type"] == "object"


def test_run_bfcl_with_fake_completer():
    cases = [
        {
            "id": "case-1",
            "question": [{"role": "user", "content": "call f with x=1"}],
            "functions": [
                {
                    "name": "f",
                    "description": "",
                    "parameters": {
                        "type": "dict",
                        "properties": {"x": {"type": "integer"}},
                        "required": ["x"],
                    },
                }
            ],
            "ground_truth": [{"f": {"x": [1]}}],
        }
    ]
    ok, metrics = run_bfcl_tool_eval(
        limit=1,
        cases=cases,
        complete=lambda messages, tools: {"name": "f", "arguments": {"x": 1}},
    )
    assert ok
    assert metrics["cases_total"] == 1
    assert metrics["cases_passed"] == 1
    assert metrics["name_accuracy"] == 1.0
    assert metrics["args_accuracy"] == 1.0
    assert metrics["tool_call_rate"] == 1.0
