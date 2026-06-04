"""Static security scan for Butler skill files (simplified skills_guard)."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

# Zero-width chars used to evade whitespace-aware regexes (Sprint 20-1 SEC-20-A-3).
_ZERO_WIDTH_CHARS = "​‌‍⁠﻿"


def _normalize_skill_text(text: str) -> str:
    """NFKC + collapse whitespace + treat zero-width chars as whitespace.

    Sprint 20-1 SEC-20-A-3: 防 `re.\\s+` 绕过 (extra spaces / tabs / newlines /
    NBSP / 零宽空格) 和全角 unicode 混淆. 在所有 DANGEROUS_PATTERNS 匹配前
    一次性 normalize, 既保护现有 7 条英文 pattern, 也让新加的中文 pattern
    在 ASCII/全角之间统一比较.

    零宽字符 (ZWSP / ZWNJ / ZWJ / WORD JOINER / BYTE ORDER MARK) 替换为
    普通空格而非 remove, 否则 "ignore[ZWSP]previous[ZWSP]instructions" 折叠后
    变 "ignorepreviousinstructions", 反让 \\s+ 模式失去匹配能力.
    """
    if not text:
        return text
    out = unicodedata.normalize("NFKC", text)
    if _ZERO_WIDTH_CHARS:
        out = out.translate(str.maketrans(_ZERO_WIDTH_CHARS, " " * len(_ZERO_WIDTH_CHARS)))
    out = re.sub(r"\s+", " ", out, flags=re.UNICODE)
    return out


DANGEROUS_PATTERNS = [
    (re.compile(r"ignore\s+previous\s+instructions", re.I), "prompt_injection"),
    (re.compile(r"you\s+are\s+now\s+", re.I), "role_override"),
    (re.compile(r"<\s*script\b", re.I), "html_script"),
    (re.compile(r"eval\s*\(", re.I), "code_eval"),
    # Sprint 20-1 SEC-20-A-3: os.<ws>system 允许 token 内任意空白, 防 `os.\nsystem(` 绕过.
    (re.compile(r"os\s*\.\s*system\s*\(", re.I), "shell_exec"),
    # subprocess. / __import__ 同样放宽, 防止 `subprocess\n.Popen` 之类.
    (re.compile(r"subprocess\s*\.", re.I), "subprocess"),
    (re.compile(r"__import__\s*\(", re.I), "dynamic_import"),
    # Sprint 20-1 SEC-20-A-3: 中文 prompt_injection 显式 pattern. 常见模板:
    # "忽略此前的指示", "忽略先前的指令", "无视以上", "无视上述指示".
    # normalize 阶段会 NFKC 折叠全角空格, 这些 pattern 在 normalize 后的
    # 字符串上跑.
    (re.compile(r"忽略\s*(?:此前|先前|上面|上述|以上)?\s*(?:的)?\s*(?:指示|指令|说明|内容)"), "prompt_injection"),
    (re.compile(r"无视\s*(?:以上|上述|前面|先前|此前|上文)?\s*(?:的)?\s*(?:指示|指令|说明|内容)"), "prompt_injection"),
]


def scan_skill_text(text: str) -> list[str]:
    """Return list of issue codes found in skill content."""
    issues: list[str] = []
    normalized = _normalize_skill_text(text)
    for pattern, code in DANGEROUS_PATTERNS:
        if pattern.search(normalized):
            issues.append(code)
    return issues


def scan_skill_file(path: Path) -> tuple[bool, list[str]]:
    """Return (is_safe, issue_codes)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False, ["unreadable"]
    issues = scan_skill_text(text)
    return len(issues) == 0, issues


def validate_skill_install(path: Path) -> None:
    """Raise ValueError if skill file fails guard scan."""
    safe, issues = scan_skill_file(path)
    if not safe:
        raise ValueError(f"Skill failed security scan: {', '.join(issues)}")
