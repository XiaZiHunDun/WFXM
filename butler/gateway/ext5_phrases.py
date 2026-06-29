"""EXT-5 微信话术卡 — 可复制短语 SSOT（与 docs/guides/ext5-wechat-phrases-card 对齐）。"""

from __future__ import annotations

# 准备
PHRASE_SWITCH_LINGWEN = "/切换 灵文1号"

# EXT-5 真机四句
PHRASE_DIAG_DETAIL = "/诊断 详细"
PHRASE_TXT_TO_MD = "把 docs/ext5-fixture-sample.txt 转成 Markdown"
PHRASE_TXT_TO_MD_INGEST = "把 docs/ext5-fixture-sample.txt 转成 Markdown 放进记忆"
PHRASE_PDF_TO_MD_INGEST = "把这份 PDF 转成 Markdown 放进记忆"
PHRASE_REFERENCE_BOOK = "用 MarkItDown 转换项目里的参考书 docs/ext5-fixture-sample.txt"

# Owner 首周补条
PHRASE_BRIEF = "/简报"
PHRASE_FEEDBACK_OT2 = "/反馈 真机验收：EXT-5 话术卡走通"

FIXTURE_REL = "docs/ext5-fixture-sample.txt"
FIXTURE_MD_REL = "docs/ext5-fixture-sample.md"

EXT5_PHRASE_CASES: tuple[tuple[str, str], ...] = (
    ("switch", PHRASE_SWITCH_LINGWEN),
    ("diag", PHRASE_DIAG_DETAIL),
    ("txt_to_md", PHRASE_TXT_TO_MD),
    ("txt_to_md_ingest", PHRASE_TXT_TO_MD_INGEST),
    ("reference_book", PHRASE_REFERENCE_BOOK),
)

__all__ = [
    "EXT5_PHRASE_CASES",
    "FIXTURE_MD_REL",
    "FIXTURE_REL",
    "PHRASE_BRIEF",
    "PHRASE_DIAG_DETAIL",
    "PHRASE_FEEDBACK_OT2",
    "PHRASE_PDF_TO_MD_INGEST",
    "PHRASE_REFERENCE_BOOK",
    "PHRASE_SWITCH_LINGWEN",
    "PHRASE_TXT_TO_MD",
    "PHRASE_TXT_TO_MD_INGEST",
]
