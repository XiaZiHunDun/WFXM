"""Fix strategy selector — diagnostic → fix classification.

Formal model from v4-dev-engine-theory.md §2.6:
  Fix: Diagnostics × DevState → [Edit]
  Levels: direct_fix | context_fix | structural_fix | rollback_fix
"""

from __future__ import annotations

from enum import Enum

from butler.dev_engine.dev_state import DevState, Diagnostic, DiagSeverity


class FixLevel(str, Enum):
    DIRECT = "direct"
    CONTEXT = "context"
    STRUCTURAL = "structural"
    ROLLBACK = "rollback"


def classify_fix(diagnostic: Diagnostic) -> FixLevel:
    """Classify a diagnostic into a fix strategy level.

    Direct: linter rules with clear fix (unused import, missing semicolon)
    Context: type errors, undefined names requiring local context
    Structural: test failures, assertion errors requiring re-planning
    """
    msg = diagnostic.message.lower()
    rule = diagnostic.rule.lower()

    if _is_direct_fix(msg, rule, diagnostic.source):
        return FixLevel.DIRECT
    if _is_structural_fix(msg, diagnostic.source):
        return FixLevel.STRUCTURAL
    return FixLevel.CONTEXT


def suggest_fix_action(
    diagnostics: list[Diagnostic],
    state: DevState,
) -> FixLevel:
    """Determine overall fix strategy given diagnostics and current state.

    If fix_count >= K_max/2 and no progress, recommend ROLLBACK.
    """
    if not diagnostics:
        return FixLevel.DIRECT

    half_max = state.max_fix_rounds / 2
    if state.fix_count >= half_max:
        prev_errors = state.verify_result.error_count
        current_errors = sum(
            1 for d in diagnostics if d.severity == DiagSeverity.ERROR
        )
        if current_errors >= prev_errors:
            return FixLevel.ROLLBACK

    levels = [classify_fix(d) for d in diagnostics]
    priority = {
        FixLevel.ROLLBACK: 4,
        FixLevel.STRUCTURAL: 3,
        FixLevel.CONTEXT: 2,
        FixLevel.DIRECT: 1,
    }
    return max(levels, key=lambda l: priority.get(l, 0))


def _is_direct_fix(msg: str, rule: str, source: str) -> bool:
    direct_patterns = [
        "unused import",
        "imported but unused",
        "missing trailing newline",
        "missing semicolon",
        "trailing whitespace",
        "blank line at end",
        "line too long",
        "expected newline",
        "indentation",
    ]
    direct_rules = {"F401", "W291", "W292", "W293", "E501", "E302", "E303"}
    if any(p in msg for p in direct_patterns):
        return True
    if rule.upper() in direct_rules:
        return True
    return False


def enrich_fix_hint(fix_level: FixLevel, state: DevState) -> str:
    """Append experience pattern for structural fixes when guidance is available."""
    hint = fix_level.value
    if fix_level != FixLevel.STRUCTURAL:
        return hint
    ctx = getattr(state, "_coding_knowledge_ctx", None)
    if ctx is None or ctx.selected_experience is None:
        return hint
    pattern = str(ctx.selected_experience.pattern or "").strip()
    if not pattern:
        return hint
    return f"{hint}: {pattern[:240]}"


def _is_structural_fix(msg: str, source: str) -> bool:
    structural_patterns = [
        "assert",
        "assertionerror",
        "test failed",
        "expected",
        "actual",
        "not equal",
        "failed",
    ]
    if source in ("pytest",):
        return True
    return any(p in msg for p in structural_patterns)
