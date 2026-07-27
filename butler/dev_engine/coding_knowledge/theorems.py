"""CD2 + CD3: Theorem Library (CA2)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Set

from butler.dev_engine.coding_knowledge.elements import BASELINE_THEOREMS, CodingElement, _normalize_keywords
from butler.dev_engine.coding_knowledge.ast_analysis import (
    _ast_composability_violation,
    _ast_external_input_without_validation,
    _ast_has_bare_except_pass,
    _ast_has_eval_call,
    _ast_has_global_stmt,
    _ast_has_nondeterministic_call,
    _ast_http_request_without_status_check,
    _ast_idempotency_violation,
    _ast_open_without_context_manager,
    _ast_try_without_handler,
    _ast_while_true_missing_break,
    _try_parse_ast,
)


@dataclass
class TheoremCheckResult:
    """Result of checking a single theorem against code."""

    theorem_id: str
    passed: bool
    detail: str = ""


TheoremChecker = Callable[[str], TheoremCheckResult]


def _check_t01_determinism(code: str) -> TheoremCheckResult:
    """T01: Pure functions must be deterministic (AST-based)."""
    tree = _try_parse_ast(code)
    if tree is not None:
        hit = _ast_has_nondeterministic_call(tree)
        if hit:
            return TheoremCheckResult("T01", False,
                                      f"nondeterministic call: {hit}")
        return TheoremCheckResult("T01", True, "ok")
    nondeterministic = [
        r"\brandom\b", r"\brandint\b", r"\bchoice\b",
        r"datetime\.now\b", r"time\.time\b", r"\buuid\b",
    ]
    for pat in nondeterministic:
        if re.search(pat, code):
            return TheoremCheckResult("T01", False,
                                      f"nondeterministic pattern: {pat}")
    return TheoremCheckResult("T01", True, "ok")


def _check_t02_composability(code: str) -> TheoremCheckResult:
    """T02: Composition type compatibility — functions must return consistent types."""
    tree = _try_parse_ast(code)
    if tree is not None:
        violation = _ast_composability_violation(tree)
        if violation:
            return TheoremCheckResult("T02", False, violation)
        return TheoremCheckResult("T02", True, "ok")
    if re.search(r"return\s+\d+.*\n.*return\s+['\"]", code, re.MULTILINE):
        return TheoremCheckResult("T02", False, "mixed return types detected (int + str)")
    return TheoremCheckResult("T02", True, "ok")


def _check_t03_type_safety(code: str) -> TheoremCheckResult:
    """T03: Type safety — no eval/exec bypasses (AST-based)."""
    tree = _try_parse_ast(code)
    if tree is not None:
        if _ast_has_eval_call(tree):
            return TheoremCheckResult("T03", False, "eval()/exec() bypasses type safety")
        return TheoremCheckResult("T03", True, "ok")
    if re.search(r"\beval\s*\(", code):
        return TheoremCheckResult("T03", False, "eval() bypasses type safety")
    return TheoremCheckResult("T03", True, "ok")


def _check_t04_termination(code: str) -> TheoremCheckResult:
    """T04: Loops/recursion must terminate (AST-based)."""
    tree = _try_parse_ast(code)
    if tree is not None:
        if _ast_while_true_missing_break(tree):
            return TheoremCheckResult("T04", False, "while True without break")
        return TheoremCheckResult("T04", True, "ok")
    if re.search(r"while\s+True\s*:", code):
        has_break = bool(re.search(r"\bbreak\b", code))
        if not has_break:
            return TheoremCheckResult("T04", False, "while True without break")
    return TheoremCheckResult("T04", True, "ok")


def _check_t05_state_isolation(code: str) -> TheoremCheckResult:
    """T05: Mutable state scope minimized (AST-based)."""
    tree = _try_parse_ast(code)
    if tree is not None:
        if _ast_has_global_stmt(tree):
            return TheoremCheckResult("T05", False,
                                      "global keyword — state isolation violation")
        return TheoremCheckResult("T05", True, "ok")
    if "global " in code:
        for line in code.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if stripped.startswith("global "):
                return TheoremCheckResult("T05", False,
                                          "global keyword — state isolation violation")
    return TheoremCheckResult("T05", True, "ok")


def _check_t06_exception_safety(code: str) -> TheoremCheckResult:
    """T06: Strong exception safety (AST-based)."""
    tree = _try_parse_ast(code)
    if tree is not None:
        if _ast_try_without_handler(tree):
            return TheoremCheckResult("T06", False, "try without catch/except")
        if _ast_has_bare_except_pass(tree):
            return TheoremCheckResult("T06", False,
                                      "bare except:pass swallows all errors")
        return TheoremCheckResult("T06", True, "ok")
    has_try = "try:" in code or "try {" in code
    has_handler = ("except " in code or "except:" in code
                   or "catch " in code or "catch(" in code)
    if has_try and not has_handler:
        return TheoremCheckResult("T06", False, "try without catch/except")
    if re.search(r"except\s*:\s*pass", code):
        return TheoremCheckResult("T06", False,
                                  "bare except:pass swallows all errors")
    return TheoremCheckResult("T06", True, "ok")


def _check_t07_idempotency(code: str) -> TheoremCheckResult:
    """T07: Idempotent operations — op(op(s)) = op(s)."""
    tree = _try_parse_ast(code)
    if tree is not None:
        violation = _ast_idempotency_violation(tree)
        if violation:
            return TheoremCheckResult("T07", False, violation)
        return TheoremCheckResult("T07", True, "ok")
    if re.search(r"\.append\s*\(", code):
        return TheoremCheckResult("T07", False,
                                  "append() mutates state non-idempotently")
    if re.search(r"open\s*\([^)]*['\"]a['\"]", code):
        return TheoremCheckResult("T07", False,
                                  "file opened in append mode — non-idempotent")
    return TheoremCheckResult("T07", True, "ok")


def _check_t08_resource_lifecycle(code: str) -> TheoremCheckResult:
    """T08: Every acquire must pair with release (AST-based)."""
    tree = _try_parse_ast(code)
    if tree is not None:
        if _ast_open_without_context_manager(tree):
            return TheoremCheckResult("T08", False,
                                      "resource opened without with/close/finally")
        return TheoremCheckResult("T08", True, "ok")
    for line in code.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if re.search(r"\bopen\s*\(", stripped):
            is_with = stripped.lstrip().startswith("with ")
            is_assigned_close = "close()" in code or ".close()" in code
            is_finally = "finally:" in code
            if not (is_with or is_assigned_close or is_finally):
                return TheoremCheckResult("T08", False,
                                          "resource opened without with/close/finally")
    return TheoremCheckResult("T08", True, "ok")


def _check_t09_contract_adherence(code: str) -> TheoremCheckResult:
    """T09: API contract adherence (AST-based)."""
    tree = _try_parse_ast(code)
    if tree is not None:
        if _ast_http_request_without_status_check(tree):
            return TheoremCheckResult("T09", False,
                                      "HTTP request without status check")
        return TheoremCheckResult("T09", True, "ok")
    has_request = bool(re.search(r"requests\.(get|post|put|delete)\s*\(", code))
    if has_request:
        has_status_check = bool(re.search(
            r"(status_code|raise_for_status|\.ok\b)", code))
        if not has_status_check:
            return TheoremCheckResult("T09", False,
                                      "HTTP request without status check")
    return TheoremCheckResult("T09", True, "ok")


def _check_t10_trust_boundary(code: str) -> TheoremCheckResult:
    """T10: External data must be validated (AST-based)."""
    tree = _try_parse_ast(code)
    if tree is not None:
        if _ast_external_input_without_validation(tree):
            return TheoremCheckResult("T10", False,
                                      "external input used without validation")
        return TheoremCheckResult("T10", True, "ok")
    has_external = bool(re.search(
        r"\binput\s*\(|request\.(args|form|json|data)\b|sys\.argv\b", code))
    if has_external:
        has_validation = bool(re.search(
            r"(validate|sanitize|isinstance|int\(|float\(|strip\(|\.get\()", code))
        if not has_validation:
            return TheoremCheckResult("T10", False,
                                      "external input used without validation")
    return TheoremCheckResult("T10", True, "ok")


THEOREM_CHECKERS: Dict[str, TheoremChecker] = {
    "T01": _check_t01_determinism,
    "T02": _check_t02_composability,
    "T03": _check_t03_type_safety,
    "T04": _check_t04_termination,
    "T05": _check_t05_state_isolation,
    "T06": _check_t06_exception_safety,
    "T07": _check_t07_idempotency,
    "T08": _check_t08_resource_lifecycle,
    "T09": _check_t09_contract_adherence,
    "T10": _check_t10_trust_boundary,
}


@dataclass
class CodingTheorem:
    """A coding theorem: an eternal programming truth (CA2, CD2)."""

    id: str
    name: str
    layer: str  # "computation", "effect_state", "resource_boundary"
    triggers: Set[str]
    statement: str
    element_triggers: Set[CodingElement] = field(default_factory=set)

    @property
    def checker(self) -> TheoremChecker:
        return THEOREM_CHECKERS.get(self.id, lambda code: TheoremCheckResult(
            self.id, True, "ok (no checker)"))

    def check(self, code: str) -> TheoremCheckResult:
        return self.checker(code)

    def is_activated_by(self, keywords: Set[str],
                        elements: Set[CodingElement]) -> bool:
        kw_hit = bool(self.triggers & keywords)
        elem_hit = bool(self.element_triggers & elements)
        return kw_hit or elem_hit


def build_default_theorem_library() -> Dict[str, CodingTheorem]:
    """Build the default T01-T10 theorem library (CD3)."""
    theorems = [
        CodingTheorem(
            id="T01", name="确定性定理", layer="computation",
            triggers={"pure", "deterministic", "idempotent", "cache"},
            statement="纯函数对同一输入永返回同一输出",
            element_triggers={CodingElement.DATA_FLOW},
        ),
        CodingTheorem(
            id="T02", name="组合性定理", layer="computation",
            triggers={"compose", "chain", "pipeline", "decorator"},
            statement="若 f: A→B 正确且 g: B→C 正确，则 g∘f: A→C 正确",
            element_triggers={CodingElement.COMPOSITION},
        ),
        CodingTheorem(
            id="T03", name="类型安全定理", layer="computation",
            triggers={"type", "cast", "convert", "schema"},
            statement="值只能按类型声明的契约使用",
            element_triggers={CodingElement.TYPE_SCHEMA},
        ),
        CodingTheorem(
            id="T04", name="终止性义务", layer="computation",
            triggers={"loop", "recursive", "while", "for"},
            statement="循环/递归必须存在单调递减度量函数保证有限步终止",
            element_triggers={CodingElement.CONTROL_FLOW},
        ),
        CodingTheorem(
            id="T05", name="状态隔离定理", layer="effect_state",
            triggers={"state", "mutable", "cache", "closure"},
            statement="可变状态作用域最小化；内部状态不影响外部",
            element_triggers={CodingElement.STATE_MANAGEMENT},
        ),
        CodingTheorem(
            id="T06", name="异常安全定理", layer="effect_state",
            triggers={"exception", "try", "catch", "error", "throw",
                       "transaction"},
            statement="操作要么成功并提交全部副作用，要么失败不产生任何副作用",
            element_triggers={CodingElement.ERROR_HANDLING},
        ),
        CodingTheorem(
            id="T07", name="幂等性定理", layer="effect_state",
            triggers={"idempotent", "retry"},
            statement="幂等操作 op(op(s)) = op(s)",
            element_triggers={CodingElement.STATE_MANAGEMENT},
        ),
        CodingTheorem(
            id="T08", name="资源生命周期定理", layer="resource_boundary",
            triggers={"open", "close", "acquire", "release", "file",
                       "connection"},
            statement="每个 acquire() 必须与唯一的 release() 配对",
            element_triggers={CodingElement.BOUNDARY_INTERFACE},
        ),
        CodingTheorem(
            id="T09", name="契约遵守定理", layer="resource_boundary",
            triggers={"api", "contract", "http", "database", "protocol"},
            statement="与外部接口交互必须满足逻辑层面的前置/后置/不变量",
            element_triggers={CodingElement.BOUNDARY_INTERFACE},
        ),
        CodingTheorem(
            id="T10", name="信任边界定理", layer="resource_boundary",
            triggers={"input", "external", "user", "network", "validate",
                       "sanitize"},
            statement="外部数据不可信，使用前必须校验",
            element_triggers={CodingElement.BOUNDARY_INTERFACE},
        ),
    ]
    return {t.id: t for t in theorems}


class TheoremLibrary:
    """Manages the coding theorem library (CA2, CD3)."""

    def __init__(self) -> None:
        self._theorems: Dict[str, CodingTheorem] = build_default_theorem_library()

    @property
    def theorems(self) -> Dict[str, CodingTheorem]:
        return dict(self._theorems)

    def get(self, theorem_id: str) -> Optional[CodingTheorem]:
        return self._theorems.get(theorem_id)

    def activate(self, keywords: Set[str],
                 elements: Set[CodingElement]) -> Dict[str, CodingTheorem]:
        """CD5: Activate theorems matching keywords or elements."""
        normalized = _normalize_keywords(keywords)
        result = {
            tid: t for tid, t in self._theorems.items()
            if t.is_activated_by(normalized, elements)
        }
        if not result:
            for baseline_id in BASELINE_THEOREMS:
                t = self._theorems.get(baseline_id)
                if t:
                    result[baseline_id] = t
        return result

    def all_ids(self) -> Set[str]:
        return set(self._theorems.keys())


__all__ = [
    "TheoremCheckResult",
    "TheoremChecker",
    "THEOREM_CHECKERS",
    "CodingTheorem",
    "build_default_theorem_library",
    "TheoremLibrary",
    "BASELINE_THEOREMS",
]