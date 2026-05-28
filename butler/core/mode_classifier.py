"""Plan vs do mode suggestion (Kiro classifier subset — heuristic-first, optional aux)."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Literal

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

ModeLabel = Literal["plan", "do"]

_PLAN_PATTERNS: list[tuple[str, int]] = [
    (r"(方案|规划一下|实施计划|路线图|可?行性)", 3),
    (r"(架构|怎么设计|如何设计|技术选型)", 3),
    (r"(先分析|别改|不要改|不要动|只分析|只读|先别写)", 4),
    (r"(调研|评估一下|对比一下|该不该|是否值得)", 2),
    (r"(拆解|分步骤|怎么做比较好)", 2),
]

_DO_PATTERNS: list[tuple[str, int]] = [
    (r"(修|修复|改掉|实现|写完|加上|删除|创建)", 3),
    (r"(跑(一下)?测试|部署|提交|push|merge)", 3),
    (r"(委派|交给|开发代理|写进项目|改项目)", 4),
    (r"(read_file|patch|terminal)", 1),
    (r"(现在|马上|直接|立刻).{0,8}(改|做|写|跑)", 3),
]


def mode_classifier_enabled() -> bool:
    return env_truthy("BUTLER_MODE_CLASSIFIER", default=True)


def mode_classifier_aux_enabled() -> bool:
    return env_truthy("BUTLER_MODE_CLASSIFIER_AUX", default=False)


def mode_classifier_auto_plan() -> bool:
    """When true, high-confidence plan turns on plan_mode (risky on WeChat)."""
    return env_truthy("BUTLER_MODE_CLASSIFIER_AUTO_PLAN", default=False)


def _min_chars() -> int:
    try:
        return max(20, int(os.getenv("BUTLER_MODE_CLASSIFIER_MIN_CHARS", "") or "36"))
    except ValueError:
        return 36


def score_mode(text: str) -> tuple[int, int]:
    """Return (plan_score, do_score)."""
    body = (text or "").strip()
    if not body:
        return 0, 0
    plan = 0
    do = 0
    for pat, w in _PLAN_PATTERNS:
        if re.search(pat, body, re.IGNORECASE):
            plan += w
    for pat, w in _DO_PATTERNS:
        if re.search(pat, body, re.IGNORECASE):
            do += w
    return plan, do


def classify_mode_heuristic(text: str) -> ModeLabel | None:
    """Classify without LLM. None = inconclusive / skip."""
    body = (text or "").strip()
    if len(body) < _min_chars():
        return None
    if body.startswith("/"):
        return None
    plan, do = score_mode(body)
    if plan >= 4 and plan >= do + 2:
        return "plan"
    if do >= 4 and do >= plan + 2:
        return "do"
    if plan >= 3 and plan > do:
        return "plan"
    if do >= 3 and do > plan:
        return "do"
    return None


def classify_mode_auxiliary(text: str) -> ModeLabel | None:
    """Optional small aux model for borderline cases."""
    if not mode_classifier_aux_enabled():
        return None
    plan, do = score_mode(text)
    if abs(plan - do) > 3:
        return None
    if plan + do < 2:
        return None
    try:
        from butler.transport.auxiliary_client import auxiliary_complete

        prompt = (
            "Classify the user message for a coding assistant.\n"
            '- "plan": explore, design, or write an implementation plan only; no code changes yet.\n'
            '- "do": execute, edit files, run commands, or delegate implementation.\n'
            "Reply with JSON only: {\"mode\":\"plan\"|\"do\",\"confidence\":0.0-1.0}\n\n"
            f"User message:\n{(text or '')[:800]}"
        )
        raw = auxiliary_complete(
            prompt,
            task="mode_classify",
            system="You output compact JSON only.",
        )
        m = re.search(r"\{[^{}]*\}", raw)
        if not m:
            return None
        data = json.loads(m.group(0))
        if not isinstance(data, dict):
            return None
        mode = str(data.get("mode") or "").strip().lower()
        conf = float(data.get("confidence") or 0)
        if conf < 0.55:
            return None
        if mode in ("plan", "do"):
            return mode  # type: ignore[return-value]
    except Exception as exc:
        logger.debug("mode classifier aux skipped: %s", exc)
    return None


def classify_turn_mode(text: str) -> ModeLabel | None:
    if not mode_classifier_enabled():
        return None
    label = classify_mode_heuristic(text)
    if label is not None:
        return label
    return classify_mode_auxiliary(text)


def detect_mode_suggestion_banner(
    user_text: str,
    *,
    session_key: str = "",
) -> str | None:
    """Ephemeral system hint: suggest /规划 or confirm execution mode."""
    if not mode_classifier_enabled():
        return None
    text = (user_text or "").strip()
    if not text or text.startswith("/"):
        return None
    try:
        from butler.plan_mode import is_plan_mode

        if is_plan_mode(session_key):
            return None
    except Exception as exc:
        logger.debug("detect mode suggestion banner skipped: %s", exc)
    label = classify_turn_mode(text)
    if label is None:
        return None

    if label == "plan":
        if mode_classifier_auto_plan():
            try:
                from butler.plan_mode import set_plan_mode

                set_plan_mode(session_key, True)
                return (
                    "[Mode: plan] 已根据消息内容自动进入规划模式（只读 + 可写 plan 文件）。"
                    "发 /执行 退出后再改代码或委派。"
                )
            except Exception as exc:
                logger.debug("detect mode suggestion banner skipped: %s", exc)
        return (
            "[Mode: plan] 本条更像「先规划再动手」。建议发 **/规划** 进入只读规划；"
            "若你就是要直接改代码，请说明「直接执行」或具体改动目标。"
        )
    return (
        "[Mode: do] 本条更像「直接执行」。将按常规模式处理；"
        "若你只想先出方案、暂不改代码，请发 **/规划**。"
    )


__all__ = [
    "classify_mode_heuristic",
    "classify_turn_mode",
    "detect_mode_suggestion_banner",
    "mode_classifier_auto_plan",
    "mode_classifier_aux_enabled",
    "mode_classifier_enabled",
    "score_mode",
]
