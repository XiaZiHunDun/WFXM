"""Static security scan for Butler skill files (simplified skills_guard)."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Literal

TrustLevel = Literal["builtin", "project", "hub"]
Verdict = Literal["pass", "warn", "block"]
LoadPolicy = Literal["inject", "warn_inject", "tools_only", "block"]

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


def scan_verdict(issues: list[str]) -> Verdict:
    if not issues:
        return "pass"
    if "unreadable" in issues or "prompt_injection" in issues or "role_override" in issues:
        return "block"
    return "warn"


def infer_trust_level(path: Path) -> TrustLevel:
    parts = [p.lower() for p in path.parts]
    if "registry" in parts or "hub" in parts:
        return "hub"
    if ".butler" in parts:
        return "project"
    return "builtin"


def resolve_skill_load_policy(verdict: Verdict, trust: TrustLevel) -> LoadPolicy:
    """verdict × trust matrix for inject / tools_bridge / block."""
    if verdict == "block":
        return "block"
    if trust == "builtin":
        return "inject" if verdict == "pass" else "warn_inject"
    if trust == "project":
        return "inject" if verdict == "pass" else "warn_inject"
    if trust == "hub":
        if verdict == "pass":
            return "warn_inject"
        return "block"
    return "block"


def infer_trust_from_source(source: str, path: Path) -> TrustLevel:
    """Map SkillManager source label + path heuristics to trust tier."""
    path_trust = infer_trust_level(path)
    if path_trust == "hub":
        return "hub"
    if source == "global":
        return "builtin"
    if source == "project":
        return "project"
    return path_trust


def evaluate_skill_load_policy(path: Path, *, source: str = "project") -> LoadPolicy:
    """Full path: scan file → verdict × trust → load policy."""
    _safe, issues = scan_skill_file(path)
    verdict = scan_verdict(issues)
    trust = infer_trust_from_source(source, path)
    return resolve_skill_load_policy(verdict, trust)


def skill_allows_injection(policy: LoadPolicy) -> bool:
    return policy in ("inject", "warn_inject")


def skill_requires_trust_disclaimer(policy: LoadPolicy) -> bool:
    return policy == "warn_inject"


def validate_skill_install(path: Path) -> None:
    """Raise ValueError if skill file fails guard scan or load policy."""
    policy = evaluate_skill_load_policy(path, source="hub")
    if policy == "block":
        _safe, issues = scan_skill_file(path)
        raise ValueError(f"Skill blocked by load policy: {', '.join(issues) or policy}")
