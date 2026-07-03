"""Natural-language routing hints (Butler Lead vs local CC) — heuristic only."""

from __future__ import annotations

import re

from butler.env_parse import env_truthy

_CC_HEAVY_PATTERNS: tuple[tuple[str, int], ...] = (
    (r"(全量|大规模|整个代码库|整库|全项目).{0,12}(重构|迁移|改写|重写)", 4),
    (r"(重构|refactor).{0,16}(整个|全部|所有|全库)", 4),
    (r"(rewrite|re-?architect).{0,20}(codebase|repo|project)", 3),
    (r"(npm install|pip install).{0,20}(全部|所有依赖|整个)", 2),
)


def cc_route_hints_enabled() -> bool:
    return env_truthy("BUTLER_CC_ROUTE_HINTS", default=True)


def score_heavy_coding_intent(text: str) -> int:
    body = (text or "").strip()
    if not body or body.startswith("/"):
        return 0
    score = 0
    for pat, w in _CC_HEAVY_PATTERNS:
        if re.search(pat, body, re.IGNORECASE):
            score += w
    return score


def detect_cc_route_banner(user_text: str) -> str | None:
    """Suggest local CC + acceptance checklist for heavy refactor (non-blocking)."""
    if not cc_route_hints_enabled():
        return None
    if score_heavy_coding_intent(user_text) < 4:
        return None
    from butler.core.task_route_hints_ops import cc_bridge_enabled_for_hints_safe

    cc_on = cc_bridge_enabled_for_hints_safe()
    cc_line = (
        "可发 **/cc-bridge <任务摘要>**（需已开启 CC 桥接）。"
        if cc_on
        else "本机 Claude Code / Cursor 更适合；我可在微信列验收清单。"
    )
    return (
        "[路由提示] 这条像大改码/全库重构，手机委派容易慢且难验收。\n"
        f"建议：本机 CC 执行；我负责派工与验收。{cc_line}\n"
        "若仍要远程改：请说明「交给开发代理」并限定文件范围。"
    )


__all__ = [
    "cc_route_hints_enabled",
    "detect_cc_route_banner",
    "score_heavy_coding_intent",
]
