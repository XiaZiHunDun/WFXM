"""BFCL v4 simple (Python) external anchor.

只做轻量对照：把官方 400 条 simple_python 按固定步长抽 limit 条，经生产模型
(MiniMax) 走一次 tool-calling，按“函数名 + 参数取值集合”打分。
这不是官方 AST checker 分数，不能与 BFCL 排行榜直接比较。
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Sequence

from butler.utilities.env_parse import float_env, int_env

_DATA_BASE = (
    "https://raw.githubusercontent.com/ShishirPatil/gorilla/main/"
    "berkeley-function-call-leaderboard/bfcl_eval/data"
)
DEFAULT_DATASET = "BFCL_v4_simple_python"
_DEFAULT_CACHE = Path.home() / ".cache" / "butler-eval" / "bfcl"

_SCHEMA_TYPES = {
    "dict": "object",
    "float": "number",
    "tuple": "array",
    "any": "string",
}


def bfcl_available() -> bool:
    """生产模型与 openai SDK 都可用时才跑真实基准。"""
    key = os.environ.get("MINIMAX_CN_API_KEY") or os.environ.get("MINIMAX_API_KEY")
    return bool(key and os.environ.get("MINIMAX_BASE_URL") and os.environ.get("MINIMAX_MODEL"))


def load_bfcl_cases(
    *,
    limit: int = 50,
    dataset: str = DEFAULT_DATASET,
    cache_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """下载/缓存官方数据，按固定步长抽样，返回可直接评测的用例。"""
    cache = cache_dir or Path(os.environ.get("BUTLER_EVAL_BFCL_CACHE_DIR", _DEFAULT_CACHE))
    questions = _load_jsonl(cache / f"{dataset}.json", f"{_DATA_BASE}/{dataset}.json")
    answers = _load_jsonl(
        cache / "possible_answer" / f"{dataset}.json",
        f"{_DATA_BASE}/possible_answer/{dataset}.json",
    )
    truth = {row["id"]: row["ground_truth"] for row in answers}
    rows = [row for row in questions if row["id"] in truth]
    if limit > 0 and limit < len(rows):
        step = len(rows) / limit
        rows = [rows[int(index * step)] for index in range(limit)]
    return [
        {
            "id": row["id"],
            "question": _flatten_question(row["question"]),
            "functions": row["function"],
            "ground_truth": truth[row["id"]],
        }
        for row in rows
    ]


def _flatten_question(raw: Sequence[Any]) -> list[dict[str, Any]]:
    """BFCL 的 question 是 turn 列表（每个 turn 又是 message 列表）。"""
    messages: list[dict[str, Any]] = []
    for turn in raw:
        if isinstance(turn, list):
            messages.extend(turn)
        else:
            messages.append(turn)
    return messages


def _load_jsonl(path: Path, url: str) -> list[dict[str, Any]]:
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=30) as response:
            path.write_bytes(response.read())
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalize_schema(node: Any) -> Any:
    """BFCL 用 dict/float/tuple/any，转成 OpenAI tools 接受的 JSON Schema。"""
    if isinstance(node, list):
        return [normalize_schema(item) for item in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key == "type" and isinstance(value, str):
            out[key] = _SCHEMA_TYPES.get(value, value)
        elif key in ("properties",):
            out[key] = {name: normalize_schema(spec) for name, spec in value.items()}
        elif key in ("items", "parameters", "additionalProperties"):
            out[key] = normalize_schema(value)
        elif key in ("description", "required", "enum"):
            out[key] = value
    if "type" not in out and isinstance(node.get("properties"), dict):
        out["type"] = "object"
    return out


def build_tools(functions: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": item["name"],
                "description": item.get("description", ""),
                "parameters": normalize_schema(item.get("parameters", {"type": "object"})),
            },
        }
        for item in functions
    ]


def _norm_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        try:
            return float(stripped)
        except ValueError:
            return stripped.casefold()
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _values_equal(predicted: Any, candidate: Any) -> bool:
    """递归比较；candidate 里的列表表示“可选值”，也兼容嵌套参数。"""
    if isinstance(predicted, list) and isinstance(candidate, list):
        if len(predicted) != len(candidate):
            return False
        return all(_values_equal(item, want) for item, want in zip(predicted, candidate))
    if isinstance(predicted, dict) and isinstance(candidate, dict):
        if set(predicted) != set(candidate):
            return False
        return all(_values_equal(predicted[key], candidate[key]) for key in predicted)
    if isinstance(candidate, list) and not isinstance(predicted, list):
        return any(_values_equal(predicted, item) for item in candidate)
    return _norm_value(predicted) == _norm_value(candidate)


def _value_matches(predicted: Any, allowed: Sequence[Any]) -> bool:
    for candidate in allowed:
        if candidate in ("", None) and predicted is None:
            return True
        if _values_equal(predicted, candidate):
            return True
    return False


def score_prediction(
    predicted: dict[str, Any] | None,
    ground_truth: Sequence[dict[str, Any]],
) -> tuple[bool, bool]:
    """返回 (函数名命中, 名称+参数全中)。"""
    name_hit = False
    for entry in ground_truth:
        if len(entry) != 1:
            continue
        name, expected = next(iter(entry.items()))
        if predicted is None or predicted.get("name") != name:
            continue
        name_hit = True
        arguments = predicted.get("arguments") or {}
        if not isinstance(arguments, dict):
            continue
        args_ok = True
        for key, allowed in expected.items():
            if key not in arguments:
                if any(item == "" for item in allowed):
                    continue
                args_ok = False
                break
            if not _value_matches(arguments[key], allowed):
                args_ok = False
                break
        if args_ok:
            return True, True
    return name_hit, False


def _make_completer() -> Callable[[list[dict[str, Any]], list[dict[str, Any]]], dict[str, Any] | None]:
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ.get("MINIMAX_CN_API_KEY") or os.environ.get("MINIMAX_API_KEY"),
        base_url=os.environ["MINIMAX_BASE_URL"],
    )
    model = os.environ["MINIMAX_MODEL"]

    def complete(
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        response = client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            tools=tools,  # type: ignore[arg-type]
            tool_choice="auto",
            temperature=0,
            max_tokens=512,
        )
        calls = response.choices[0].message.tool_calls or []
        if not calls:
            return None
        function = calls[0].function
        try:
            arguments = json.loads(function.arguments or "{}")
        except json.JSONDecodeError:
            arguments = {}
        return {"name": function.name, "arguments": arguments}

    return complete


def run_bfcl_tool_eval(
    *,
    limit: int | None = None,
    cases: Sequence[dict[str, Any]] | None = None,
    complete: Callable[[list[dict[str, Any]], list[dict[str, Any]]], dict[str, Any] | None] | None = None,
    warn_only: bool = False,
) -> tuple[bool, dict[str, Any]]:
    limit = int_env("BUTLER_EVAL_BFCL_LIMIT", 50, min=1) if limit is None else limit
    threshold = float_env("BUTLER_EVAL_BFCL_ACCURACY_MIN", 0.5)
    try:
        rows = list(cases) if cases is not None else load_bfcl_cases(limit=limit)
    except Exception as error:  # 下载/解析失败不炸整个 eval 进程
        return warn_only, {"mode": "bfcl", "error": f"{type(error).__name__}: {error}"}

    completer = complete or _make_completer()
    passed = 0
    name_hits = 0
    tool_called = 0
    durations: list[int] = []
    failures: list[dict[str, Any]] = []

    for row in rows:
        started = time.monotonic()
        predicted = completer(row["question"], build_tools(row["functions"]))
        durations.append(int((time.monotonic() - started) * 1000))
        if predicted is not None:
            tool_called += 1
        name_ok, case_ok = score_prediction(predicted, row["ground_truth"])
        name_hits += int(name_ok)
        passed += int(case_ok)
        if not case_ok and len(failures) < 10:
            failures.append(
                {
                    "id": row["id"],
                    "predicted": predicted,
                    "expected": row["ground_truth"],
                }
            )

    total = len(rows)
    accuracy = passed / total if total else 0.0
    durations.sort()
    what = "bfcl_v4_simple_python"
    metrics: dict[str, Any] = {
        "mode": "bfcl",
        "dataset": what,
        "scoring": "name+args membership (simplified, not official AST)",
        "cases_total": total,
        "cases_passed": passed,
        "name_accuracy": round(name_hits / total, 4) if total else 0.0,
        "args_accuracy": round(accuracy, 4),
        "tool_call_rate": round(tool_called / total, 4) if total else 0.0,
        "duration_ms_p50": durations[len(durations) // 2] if durations else 0,
        "accuracy_min": threshold,
        "limit": limit,
        "failures": failures,
    }
    return (warn_only or accuracy >= threshold), metrics
