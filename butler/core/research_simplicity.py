"""Simplicity / keep-discard hints for research and post-compact anchors."""

from __future__ import annotations


from butler.env_parse import env_truthy


def simplicity_anchor_enabled() -> bool:
    return env_truthy("BUTLER_RESEARCH_SIMPLICITY_ANCHOR", default=True)


def format_simplicity_anchor() -> str:
    if not simplicity_anchor_enabled():
        return ""
    return (
        "## 简洁性 / 实验纪律（锚点）\n"
        "- 同等指标优先更简单实现\n"
        "- 删代码且指标不低于基线 → 记 keep\n"
        "- 微小提升 + 明显复杂度 → 倾向 discard\n"
        "- 长日志用 grep `METRIC` / 读 `.butler/last_run.log`，勿整段贴回模型\n"
    )


__all__ = ["format_simplicity_anchor", "simplicity_anchor_enabled"]
