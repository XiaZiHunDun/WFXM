"""RAGAS memory suite — real metrics (v0.4) with heuristic fallback."""

from __future__ import annotations

import json
import math
import os
import re
import sys
import types
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

from butler.utilities.env_parse import float_env, int_env

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ragas_memory_cases.yaml"

_DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _install_vertexai_shim() -> None:
    """ragas 0.4 imports `langchain_community.chat_models.vertexai`, which was
    removed in langchain-community 0.4. We never use ChatVertexAI, so inject a
    minimal placeholder instead of pinning the whole community package."""
    module_name = "langchain_community.chat_models.vertexai"
    if module_name in sys.modules:
        return
    try:
        __import__(module_name)
        return
    except Exception:  # noqa: BLE001 - any import failure is handled by the shim
        pass

    class ChatVertexAI:  # pragma: no cover - only used to satisfy ragas import
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("ChatVertexAI is not available in this environment")

    shim = types.ModuleType(module_name)
    shim.ChatVertexAI = ChatVertexAI  # type: ignore[attr-defined]
    sys.modules[module_name] = shim


def ragas_available() -> bool:
    _install_vertexai_shim()
    try:
        import ragas  # noqa: F401

        return True
    except Exception:  # noqa: BLE001 - optional dependency
        return False


def _load_cases() -> list[dict[str, Any]]:
    trace_dir = os.environ.get("BUTLER_EVAL_RAGAS_TRACE_DIR", "").strip()
    if trace_dir:
        traced = _load_trace_cases(Path(trace_dir))
        if traced:
            return traced
    from butler.eval_integration.oss.prefetch_audit_loader import load_prefetch_audit_cases

    audit = load_prefetch_audit_cases()
    if audit:
        return cast(list[dict[str, Any]], audit)
    if not _FIXTURES.is_file():
        return []
    data = yaml.safe_load(_FIXTURES.read_text(encoding="utf-8")) or {}
    return list(data.get("cases") or [])


def _trace_case_id(trace_path: Path) -> str:
    """repeats>1 时 trace 位于 `<task>/attempt-N/`，用两级目录保证 id 唯一。"""
    parent = trace_path.parent
    if parent.name.startswith("attempt-") and parent.parent.name:
        return f"{parent.parent.name}/{parent.name}"
    return parent.name


def _load_trace_cases(root: Path) -> list[dict[str, Any]]:
    """Build Ragas cases from agent-eval artifacts.

    Each `<task>/trace.jsonl` contributes one case:
    question = first turn.start input; contexts = rag.retrieve hits[].text;
    answer = `<task>/result.json.reply`; reference / expectedDocTitles 来自
    任务注入的 `rag.expectation` 事件。缺 question/contexts/answer 的跳过。
    """
    cases: list[dict[str, Any]] = []
    for trace_path in sorted(root.glob("**/trace.jsonl")):
        try:
            events = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (OSError, json.JSONDecodeError):
            continue

        question = ""
        for event in events:
            if event.get("type") != "turn.start":
                continue
            payload = event.get("payload") or {}
            question = str(payload.get("content") or payload.get("input") or "").strip()
            if question:
                break

        contexts: list[str] = []
        retrieval_hits: list[dict[str, Any]] = []
        for event in events:
            if event.get("type") != "rag.retrieve":
                continue
            payload = event.get("payload") or {}
            scoped = str(payload.get("scope") or "") == "document"
            for rank, hit in enumerate(payload.get("hits") or [], start=1):
                text = str(hit.get("text") or "").strip()
                if text and text not in contexts:
                    contexts.append(text)
                if scoped:
                    retrieval_hits.append(
                        {
                            "rank": int(hit.get("rank") or rank),
                            "title": str(hit.get("title") or ""),
                            "docId": str(hit.get("docId") or ""),
                            "score": hit.get("score"),
                            "scoreKind": hit.get("scoreKind"),
                        }
                    )

        reference = ""
        expected_doc_titles: list[str] = []
        for event in events:
            if event.get("type") != "rag.expectation":
                continue
            payload = event.get("payload") or {}
            reference = str(payload.get("reference") or "").strip()
            expected_doc_titles = [
                str(title).strip()
                for title in payload.get("expectedDocTitles") or []
                if str(title).strip()
            ]

        answer = ""
        result_path = trace_path.parent / "result.json"
        if result_path.is_file():
            try:
                answer = str(json.loads(result_path.read_text(encoding="utf-8")).get("reply") or "")
            except (OSError, json.JSONDecodeError):
                answer = ""

        if question and contexts and answer:
            cases.append(
                {
                    "id": _trace_case_id(trace_path),
                    "question": question,
                    "contexts": contexts[:10],
                    "answer": answer,
                    "source": "agent_eval_trace",
                    "retrieval_hits": retrieval_hits,
                    "expected_doc_titles": expected_doc_titles,
                    **({"reference": reference} if reference else {}),
                }
            )
    return cases


def _retrieval_metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """检索层指标：Hit@1 / Hit@3 / MRR / precision@k。

    命中判定用任务声明的 expectedDocTitles 对 hit.title 精确匹配；
    只统计有真值的用例，避免把探索性调用算成漏检。
    """
    rows: list[dict[str, Any]] = []
    for case in cases:
        expected = {title for title in case.get("expected_doc_titles") or [] if title}
        if not expected:
            continue
        hits = case.get("retrieval_hits") or []
        ranks = [index for index, hit in enumerate(hits, start=1) if hit.get("title") in expected]
        rows.append(
            {
                "id": case.get("id"),
                "expected": sorted(expected),
                "returned": [hit.get("title") for hit in hits],
                "firstRank": ranks[0] if ranks else None,
                "relevant": len(ranks),
                "returnedCount": len(hits),
            }
        )

    total = len(rows)
    if total == 0:
        return {"cases_total": 0, "reason": "no retrieval ground truth"}

    def _avg(key: str) -> float:
        return round(sum(float(row[key]) for row in rows) / total, 4)

    hit1 = sum(1 for row in rows if row["firstRank"] == 1)
    hit3 = sum(1 for row in rows if (row["firstRank"] or 99) <= 3)
    mrr = sum(1.0 / row["firstRank"] for row in rows if row["firstRank"])
    precision = sum(
        (row["relevant"] / row["returnedCount"]) if row["returnedCount"] else 0.0 for row in rows
    )
    return {
        "cases_total": total,
        "hit_at_1": round(hit1 / total, 4),
        "hit_at_3": round(hit3 / total, 4),
        "mrr": round(mrr / total, 4),
        "precision_at_k": round(precision / total, 4),
        "misses": [row["id"] for row in rows if row["firstRank"] is None],
        "details": rows,
    }


def _tokenize(text: str) -> set[str]:
    parts = re.findall(r"[\w/.-]+", text.lower())
    return {p for p in parts if len(p) >= 3}


def heuristic_faithfulness(context: str, answer: str) -> float:
    """Context–answer token overlap ratio (0–1), no LLM."""
    ctx_tokens = _tokenize(context)
    if not ctx_tokens:
        return 0.0
    ans_tokens = _tokenize(answer)
    if not ans_tokens:
        return 0.0
    overlap = len(ctx_tokens & ans_tokens)
    return overlap / len(ctx_tokens)


def run_heuristic(*, warn_only: bool = False) -> tuple[bool, dict[str, Any]]:
    cases = _load_cases()
    if not cases:
        return True, {"mode": "heuristic", "skipped": True, "reason": "no fixtures"}

    threshold = float_env("BUTLER_EVAL_RAGAS_FAITHFULNESS_MIN", 0.5)
    details: list[dict[str, Any]] = []

    for case in cases:
        ctx = str(case.get("context", "")).strip() or "\n".join(_contexts_of(case))
        ans = str(case.get("answer", ""))
        score = heuristic_faithfulness(ctx, ans)
        min_f = case.get("min_faithfulness")
        max_f = case.get("max_faithfulness")
        passed = True
        if min_f is not None and score < float(min_f):
            passed = False
        if max_f is not None and score > float(max_f):
            passed = False
        details.append(
            {
                "id": case.get("id"),
                "faithfulness": round(score, 4),
                "passed": passed,
            }
        )

    avg = (
        sum(
            heuristic_faithfulness(
                str(c.get("context", "")).strip() or "\n".join(_contexts_of(c)),
                str(c.get("answer", "")),
            )
            for c in cases
        )
        / len(cases)
        if cases
        else 0.0
    )
    cases_passed = sum(1 for d in details if d["passed"])
    ok = cases_passed == len(cases) or warn_only
    mode = "audit" if any(c.get("source") == "transcript_audit" for c in cases) else "heuristic"
    return ok, {
        "mode": mode,
        "faithfulness_avg": round(avg, 4),
        "threshold": threshold,
        "cases_total": len(cases),
        "cases_passed": cases_passed,
        "details": details,
        "ragas_installed": ragas_available(),
    }


def _contexts_of(case: dict[str, Any]) -> list[str]:
    raw = case.get("contexts")
    if isinstance(raw, list) and raw:
        return [str(item) for item in raw if str(item).strip()]
    context = str(case.get("context", "")).strip()
    return [context] if context else []


def _build_llm() -> tuple[Any | None, str | None]:
    """Build a ChatOpenAI-compatible judge from env.

    Order: explicit BUTLER_EVAL_RAGAS_* → DeepSeek → OpenAI.
    """
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        return None, None

    model = os.environ.get("BUTLER_EVAL_RAGAS_MODEL", "").strip()
    base_url = os.environ.get("BUTLER_EVAL_RAGAS_BASE_URL", "").strip()
    api_key = os.environ.get("BUTLER_EVAL_RAGAS_API_KEY", "").strip()

    if not api_key:
        deepseek = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if deepseek:
            api_key = deepseek
            model = model or os.environ.get("DEEPSEEK_MODEL", "").strip() or "deepseek-chat"
            base_url = base_url or _DEEPSEEK_BASE_URL
    if not api_key:
        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if openai_key:
            api_key = openai_key
            model = model or "gpt-4o-mini"
    if not api_key:
        return None, None

    kwargs: dict[str, Any] = {
        "model": model or "deepseek-chat",
        "api_key": api_key,
        "temperature": 0,
    }
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs), str(kwargs["model"])


def _build_embeddings() -> tuple[Any | None, str | None]:
    """Embeddings are only required by answer relevancy."""
    try:
        from langchain_openai import OpenAIEmbeddings
    except ImportError:
        return None, None

    model = os.environ.get("BUTLER_EVAL_RAGAS_EMBEDDING_MODEL", "").strip()
    base_url = os.environ.get("BUTLER_EVAL_RAGAS_EMBEDDING_BASE_URL", "").strip()
    api_key = os.environ.get("BUTLER_EVAL_RAGAS_EMBEDDING_API_KEY", "").strip()

    if not api_key:
        dashscope = os.environ.get("DASHSCOPE_API_KEY", "").strip()
        if dashscope:
            api_key = dashscope
            model = model or "text-embedding-v3"
            base_url = base_url or _DASHSCOPE_BASE_URL
    if not api_key:
        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if openai_key:
            api_key = openai_key
            model = model or "text-embedding-3-small"
    if not api_key:
        return None, None

    kwargs: dict[str, Any] = {
        "model": model or "text-embedding-v3",
        "api_key": api_key,
        # DashScope 不接受 token 数组输入，必须关闭 tiktoken 预切分。
        "check_embedding_ctx_length": False,
    }
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAIEmbeddings(**kwargs), str(kwargs["model"])


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _case_passes(
    row: dict[str, Any],
    case: dict[str, Any],
    *,
    faithfulness_min: float,
    relevancy_min: float,
    precision_min: float,
) -> tuple[bool, list[str]]:
    failures: list[str] = []
    # Ragas 的 judge 结果带浮点噪声（如 0.49999999995），阈值比较留 1e-6
    # 容差，避免“数学上等于阈值”被判失败。
    eps = 1e-6
    faithfulness = _finite(row.get("faithfulness"))
    if faithfulness is None:
        failures.append("faithfulness missing")
    else:
        min_f = case.get("min_faithfulness")
        max_f = case.get("max_faithfulness")
        if min_f is not None and faithfulness + eps < float(min_f):
            failures.append(f"faithfulness {faithfulness:.2f} < {float(min_f):.2f}")
        if max_f is not None and faithfulness - eps > float(max_f):
            failures.append(f"faithfulness {faithfulness:.2f} > {float(max_f):.2f}")
        if min_f is None and max_f is None and faithfulness + eps < faithfulness_min:
            failures.append(f"faithfulness {faithfulness:.2f} < {faithfulness_min:.2f}")

    # 反例（max_faithfulness）只验证“低忠实度能被识别”。answer 是故意错误的，
    # 其它质量指标对反例没有意义，也容易受 judge 波动影响。
    if case.get("max_faithfulness") is not None:
        return len(failures) == 0, failures

    relevancy = _finite(row.get("answer_relevancy"))
    if relevancy is not None and relevancy + eps < relevancy_min:
        failures.append(f"answer_relevancy {relevancy:.2f} < {relevancy_min:.2f}")

    precision = _finite(row.get("llm_context_precision_with_reference"))
    if precision is None:
        precision = _finite(row.get("llm_context_precision_without_reference"))
    if precision is not None and precision + eps < precision_min:
        failures.append(f"context_precision {precision:.2f} < {precision_min:.2f}")

    recall = _finite(row.get("context_recall"))
    if recall is None:
        recall = _finite(row.get("llm_context_recall"))
    recall_min_case = case.get("min_context_recall")
    if (
        recall is not None
        and recall_min_case is not None
        and recall + eps < float(recall_min_case)
    ):
        failures.append(f"context_recall {recall:.2f} < {float(recall_min_case):.2f}")
    return len(failures) == 0, failures


def run_ragas_memory(*, warn_only: bool = False) -> tuple[bool, dict[str, Any]]:
    """Run real Ragas metrics when the judge + embeddings are configured.

    Falls back to `run_heuristic` only when the optional dependency or LLM
    credentials are missing, and always reports which mode produced the score.
    """
    if not ragas_available():
        ok, result = run_heuristic(warn_only=warn_only)
        result["mode"] = "heuristic_fallback"
        result["reason"] = "ragas not importable"
        return ok, result

    cases = _load_cases()
    if not cases:
        return True, {"mode": "ragas", "skipped": True, "reason": "no fixtures"}

    llm, judge_model = _build_llm()
    embeddings, embedding_model = _build_embeddings()
    if llm is None or embeddings is None:
        ok, result = run_heuristic(warn_only=warn_only)
        result["mode"] = "heuristic_fallback"
        result["reason"] = "ragas llm/embeddings not configured"
        return ok, result

    try:
        from datasets import Dataset  # type: ignore[import-untyped]
        from ragas import evaluate
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import (
            Faithfulness,
            LLMContextPrecisionWithReference,
            LLMContextPrecisionWithoutReference,
            LLMContextRecall,
            ResponseRelevancy,
        )

        with_reference = all(str(case.get("reference", "")).strip() for case in cases)
        # DeepSeek 等兼容端点只支持 n=1；Ragas 默认 strictness=3 会请求 n=3，
        # 并发时部分 Job 直接 400，导致 answer_relevancy 缺失。
        relevancy_strictness = int_env("BUTLER_EVAL_RAGAS_RELEVANCY_STRICTNESS", 1, min=1)
        metrics: list[Any] = [Faithfulness(), ResponseRelevancy(strictness=relevancy_strictness)]
        if with_reference:
            metrics.extend([LLMContextPrecisionWithReference(), LLMContextRecall()])
        else:
            metrics.append(LLMContextPrecisionWithoutReference())

        payload: dict[str, Any] = {
            "question": [str(case.get("question", "")) for case in cases],
            "contexts": [_contexts_of(case) for case in cases],
            "answer": [str(case.get("answer", "")) for case in cases],
        }
        if with_reference:
            payload["reference"] = [str(case.get("reference", "")) for case in cases]

        result = evaluate(
            Dataset.from_dict(payload),
            metrics=metrics,
            llm=LangchainLLMWrapper(llm),
            embeddings=LangchainEmbeddingsWrapper(embeddings),
            show_progress=False,
            raise_exceptions=False,
        )
        rows = result.to_pandas().to_dict(orient="records")
    except Exception as exc:  # noqa: BLE001 - infra failure must be visible
        ok, fallback = run_heuristic(warn_only=warn_only)
        fallback["mode"] = "heuristic_fallback"
        fallback["ragas_error"] = f"{type(exc).__name__}: {exc}"[:400]
        return ok, fallback

    faithfulness_min = float_env("BUTLER_EVAL_RAGAS_FAITHFULNESS_MIN", 0.5)
    relevancy_min = float_env("BUTLER_EVAL_RAGAS_ANSWER_RELEVANCY_MIN", 0.5)
    precision_min = float_env("BUTLER_EVAL_RAGAS_CONTEXT_PRECISION_MIN", 0.5)
    recall_min = float_env("BUTLER_EVAL_RAGAS_CONTEXT_RECALL_MIN", 0.5)

    details: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        row = rows[index] if index < len(rows) else {}
        passed, failures = _case_passes(
            row,
            case,
            faithfulness_min=faithfulness_min,
            relevancy_min=relevancy_min,
            precision_min=precision_min,
        )
        precision = _finite(row.get("llm_context_precision_with_reference"))
        if precision is None:
            precision = _finite(row.get("llm_context_precision_without_reference"))
        recall = _finite(row.get("context_recall"))
        if recall is None:
            recall = _finite(row.get("llm_context_recall"))
        details.append(
            {
                "id": case.get("id"),
                "faithfulness": _finite(row.get("faithfulness")),
                "answer_relevancy": _finite(row.get("answer_relevancy")),
                "context_precision": precision,
                "context_recall": recall,
                "passed": passed,
                "failures": failures,
            }
        )

    def _avg(key: str) -> float | None:
        values = [d[key] for d in details if isinstance(d.get(key), float)]
        return round(sum(values) / len(values), 4) if values else None

    cases_passed = sum(1 for detail in details if detail["passed"])
    ok = cases_passed == len(cases) or warn_only
    import ragas as ragas_module

    return ok, {
        "mode": "ragas",
        "retrieval": _retrieval_metrics(cases),
        "ragas_version": getattr(ragas_module, "__version__", "?"),
        "judge_model": judge_model,
        "embedding_model": embedding_model,
        "metrics": [metric.name for metric in metrics],
        "relevancy_strictness": relevancy_strictness,
        "reference_available": with_reference,
        "trace_source": os.environ.get("BUTLER_EVAL_RAGAS_TRACE_DIR", "").strip() or None,
        "faithfulness_avg": _avg("faithfulness"),
        "answer_relevancy_avg": _avg("answer_relevancy"),
        "context_precision_avg": _avg("context_precision"),
        "context_recall_avg": _avg("context_recall"),
        "thresholds": {
            "faithfulness": faithfulness_min,
            "answer_relevancy": relevancy_min,
            "context_precision": precision_min,
            "context_recall": recall_min,
        },
        "cases_total": len(cases),
        "cases_passed": cases_passed,
        "details": details,
    }
