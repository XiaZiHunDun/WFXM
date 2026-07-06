"""Post-LLM output grounding: memory prefetch overlap + simple arithmetic."""

from __future__ import annotations

import re
from typing import Any

from butler.env_parse import env_truthy

_DISCLAIMER = "（注：本轮回答与已检索记忆重叠较低，涉及事实请以项目文件/记忆为准。）"
_ARITH_RE = re.compile(
    r"(?P<a>\d+(?:\.\d+)?)\s*(?P<op>[+\-*/×÷])\s*(?P<b>\d+(?:\.\d+)?)"
)
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def memory_prefetch_grounding_enabled() -> bool:
    return bool(env_truthy("BUTLER_MEMORY_PREFETCH_GROUNDING", default=True))


def calc_grounding_enabled() -> bool:
    return bool(env_truthy("BUTLER_CALC_GROUNDING", default=True))


def _apply_memory_prefetch_grounding(text: str, diagnostics: dict[str, Any] | None) -> str:
    if not memory_prefetch_grounding_enabled() or diagnostics is None:
        return text
    total = int(diagnostics.get("memory_prefetch_retrieval_total") or 0)
    snippets = diagnostics.get("memory_prefetch_snippets")
    if total < 2 or not isinstance(snippets, list) or not snippets:
        return text
    reply = (text or "").strip()
    if len(reply) < 80:
        return text
    from butler.core.output_grounding_ops import estimate_prefetch_used_count_safe

    used = estimate_prefetch_used_count_safe(reply, [str(s) for s in snippets])
    if used is None:
        return text
    diagnostics["memory_prefetch_grounding_used"] = used
    if used > 0:
        diagnostics["memory_prefetch_grounding"] = "ok"
        return text
    diagnostics["memory_prefetch_grounding"] = "low_overlap_disclaimer"
    if _DISCLAIMER in reply:
        return text
    return reply.rstrip() + "\n\n" + _DISCLAIMER


def _eval_simple(a: float, op: str, b: float) -> float | None:
    op = op.replace("×", "*").replace("÷", "/")
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        if b == 0:
            return None
        return a / b
    return None


def _try_correct_arithmetic(user_text: str, reply: str) -> str | None:
    if not calc_grounding_enabled():
        return None
    user = str(user_text or "")
    m = _ARITH_RE.search(user)
    if not m:
        return None
    expected = _eval_simple(float(m.group("a")), m.group("op"), float(m.group("b")))
    if expected is None:
        return None
    nums = [float(x) for x in _NUM_RE.findall(str(reply or ""))]
    if not nums:
        return None
    if any(abs(n - expected) < 1e-6 for n in nums):
        return None
    if abs(expected - round(expected)) < 1e-6:
        shown = str(int(round(expected)))
    else:
        shown = f"{expected:g}"
    expr = f"{m.group('a')} {m.group('op')} {m.group('b')}"
    note = f"（演算校验：{expr} = {shown}）"
    body = str(reply or "").rstrip()
    if note in body:
        return None
    return f"{body}\n\n{note}"


def apply_output_grounding(
    user_text: str,
    assistant_text: str,
    diagnostics: dict[str, Any] | None = None,
) -> str:
    """Apply lightweight post-LLM grounding (memory overlap + simple arithmetic)."""
    text = str(assistant_text or "")
    corrected = _try_correct_arithmetic(user_text, text)
    if corrected:
        text = corrected
        if diagnostics is not None:
            diagnostics["calc_grounding"] = True
    return _apply_memory_prefetch_grounding(text, diagnostics)


__all__ = [
    "apply_output_grounding",
    "calc_grounding_enabled",
    "memory_prefetch_grounding_enabled",
]
