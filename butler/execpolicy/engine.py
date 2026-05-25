"""YAML prefix_rule engine with match/not_match regression (Codex execpolicy subset)."""

from __future__ import annotations

import logging
import shlex
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    PROMPT = "prompt"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True)
class PolicyResult:
    decision: PolicyDecision
    matched_rule: str = ""
    justification: str = ""


@dataclass(frozen=True)
class PrefixRule:
    name: str
    pattern: list[str | list[str]]
    decision: PolicyDecision
    justification: str
    match_examples: list[list[str]]
    not_match_examples: list[list[str]]


def execpolicy_enabled() -> bool:
    return env_truthy("BUTLER_EXECPOLICY", default=True)


def _tokenize_command(command: str) -> list[str]:
    text = (command or "").strip()
    if not text:
        return []
    try:
        return shlex.split(text, posix=True)
    except ValueError:
        return text.split()


def _normalize_example(example: Any) -> list[str]:
    if isinstance(example, list):
        return [str(x) for x in example]
    if isinstance(example, str):
        return _tokenize_command(example)
    return []


def _parse_rule(raw: dict[str, Any], index: int) -> PrefixRule | None:
    if not isinstance(raw, dict):
        return None
    pattern_raw = raw.get("pattern")
    if not isinstance(pattern_raw, list) or not pattern_raw:
        return None
    pattern: list[str | list[str]] = []
    for item in pattern_raw:
        if isinstance(item, list):
            alts = [str(a).strip() for a in item if str(a).strip()]
            if alts:
                pattern.append(alts)
        elif str(item).strip():
            pattern.append(str(item).strip())
    if not pattern:
        return None
    dec_raw = str(raw.get("decision") or "allow").strip().lower()
    try:
        decision = PolicyDecision(dec_raw)
    except ValueError:
        decision = PolicyDecision.ALLOW
    match_ex = [_normalize_example(x) for x in (raw.get("match") or [])]
    not_match_ex = [_normalize_example(x) for x in (raw.get("not_match") or [])]
    return PrefixRule(
        name=str(raw.get("name") or f"rule_{index}"),
        pattern=pattern,
        decision=decision,
        justification=str(raw.get("justification") or "").strip(),
        match_examples=[m for m in match_ex if m],
        not_match_examples=[m for m in not_match_ex if m],
    )


def _matches_pattern(tokens: list[str], pattern: list[str | list[str]]) -> bool:
    if len(tokens) < len(pattern):
        return False
    for i, spec in enumerate(pattern):
        tok = tokens[i]
        if isinstance(spec, list):
            if tok not in spec:
                return False
        elif tok != spec:
            return False
    return True


def _validate_rule(rule: PrefixRule) -> list[str]:
    errors: list[str] = []
    for ex in rule.match_examples:
        if not _matches_pattern(ex, rule.pattern):
            errors.append(f"{rule.name}: match example failed: {ex!r}")
    for ex in rule.not_match_examples:
        if _matches_pattern(ex, rule.pattern):
            errors.append(f"{rule.name}: not_match example incorrectly matched: {ex!r}")
    return errors


def _policy_paths(workspace: Path | None = None) -> list[Path]:
    paths: list[Path] = []
    if workspace is not None:
        ws = Path(workspace).expanduser().resolve()
        p = ws / ".butler" / "execpolicy.yaml"
        if p.is_file():
            paths.append(p)
    try:
        from butler.config import get_butler_home

        home = get_butler_home() / "execpolicy.yaml"
        if home.is_file():
            paths.append(home)
    except Exception:
        pass
    builtin = Path(__file__).resolve().parent / "builtin_rules.yaml"
    if builtin.is_file():
        paths.append(builtin)
    return paths


def load_policy_rules(*, workspace: Path | None = None) -> list[PrefixRule]:
    rules: list[PrefixRule] = []
    seen: set[str] = set()
    for path in _policy_paths(workspace):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            logger.warning("execpolicy %s unreadable: %s", path, exc)
            continue
        block = data.get("rules") if isinstance(data, dict) else data
        if not isinstance(block, list):
            continue
        for i, raw in enumerate(block):
            rule = _parse_rule(raw if isinstance(raw, dict) else {}, i)
            if rule is None or rule.name in seen:
                continue
            errs = _validate_rule(rule)
            for err in errs:
                logger.warning("execpolicy: %s", err)
            seen.add(rule.name)
            rules.append(rule)
    return rules


def evaluate_command(
    command: str,
    *,
    workspace: Path | None = None,
) -> PolicyResult | None:
    if not execpolicy_enabled():
        return None
    tokens = _tokenize_command(command)
    if not tokens:
        return None
    for rule in load_policy_rules(workspace=workspace):
        if _matches_pattern(tokens, rule.pattern):
            return PolicyResult(
                decision=rule.decision,
                matched_rule=rule.name,
                justification=rule.justification,
            )
    return None


__all__ = [
    "PolicyDecision",
    "PolicyResult",
    "PrefixRule",
    "evaluate_command",
    "execpolicy_enabled",
    "load_policy_rules",
]
