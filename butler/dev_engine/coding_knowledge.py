"""Butler v4 L4 Coding Knowledge Layer — 定理库 + 经验库 + 双重验证门.

Theory: docs/architecture/v4-dev-engine-theory.md Chapter 9 (v1.4)
Axioms: CA1-CA4 | Definitions: CD0-CD8 | Theorems: CT1-CT5
"""

from __future__ import annotations

import ast
import math
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# ═══════════════════════════════════════════════════════════════════
# CD1: Seven Coding Elements (CA1)
# ═══════════════════════════════════════════════════════════════════

class CodingElement(str, Enum):
    """Seven fundamental coding elements (CA1)."""

    DATA_FLOW = "DataFlow"
    CONTROL_FLOW = "ControlFlow"
    STATE_MANAGEMENT = "StateManagement"
    COMPOSITION = "Composition"
    BOUNDARY_INTERFACE = "BoundaryInterface"
    ERROR_HANDLING = "ErrorHandling"
    TYPE_SCHEMA = "TypeSchema"


ELEMENT_VERIFICATION_PROPERTIES: Dict[CodingElement, List[str]] = {
    CodingElement.DATA_FLOW: [
        "no_state_mutation",
        "input_immutable",
        "pipeline_direction_consistent",
    ],
    CodingElement.CONTROL_FLOW: [
        "termination_guaranteed",
        "branch_completeness",
        "no_dead_code",
    ],
    CodingElement.STATE_MANAGEMENT: [
        "scope_minimized",
        "change_predictable",
        "no_accidental_sharing",
    ],
    CodingElement.COMPOSITION: [
        "type_compatible",
        "effect_order_correct",
        "no_cyclic_dependency",
    ],
    CodingElement.BOUNDARY_INTERFACE: [
        "contract_coverage",
        "resource_release",
        "input_validation",
    ],
    CodingElement.ERROR_HANDLING: [
        "exception_coverage",
        "error_not_lost",
        "recovery_consistency",
    ],
    CodingElement.TYPE_SCHEMA: [
        "type_closed",
        "pattern_match_complete",
        "constraint_satisfied",
    ],
}

ELEMENT_THEOREM_MAP: Dict[CodingElement, Set[str]] = {
    CodingElement.DATA_FLOW: {"T01"},
    CodingElement.CONTROL_FLOW: {"T04"},
    CodingElement.STATE_MANAGEMENT: {"T05", "T07"},
    CodingElement.COMPOSITION: {"T02"},
    CodingElement.BOUNDARY_INTERFACE: {"T08", "T09", "T10"},
    CodingElement.ERROR_HANDLING: {"T06"},
    CodingElement.TYPE_SCHEMA: {"T03"},
}

BASELINE_THEOREMS = {"T03", "T10"}


def decompose_task(keywords: List[str]) -> Set[CodingElement]:
    """Decompose a coding task into activated elements based on keywords."""
    keyword_element_map: Dict[str, Set[CodingElement]] = {
        "filter": {CodingElement.DATA_FLOW, CodingElement.CONTROL_FLOW},
        "map": {CodingElement.DATA_FLOW},
        "reduce": {CodingElement.DATA_FLOW},
        "transform": {CodingElement.DATA_FLOW},
        "pipeline": {CodingElement.DATA_FLOW, CodingElement.COMPOSITION},
        "pure": {CodingElement.DATA_FLOW},
        "if": {CodingElement.CONTROL_FLOW},
        "loop": {CodingElement.CONTROL_FLOW},
        "while": {CodingElement.CONTROL_FLOW},
        "for": {CodingElement.CONTROL_FLOW},
        "recursive": {CodingElement.CONTROL_FLOW},
        "cache": {CodingElement.STATE_MANAGEMENT},
        "store": {CodingElement.STATE_MANAGEMENT},
        "counter": {CodingElement.STATE_MANAGEMENT},
        "accumulate": {CodingElement.STATE_MANAGEMENT, CodingElement.DATA_FLOW},
        "compose": {CodingElement.COMPOSITION},
        "chain": {CodingElement.COMPOSITION},
        "decorator": {CodingElement.COMPOSITION},
        "api": {CodingElement.BOUNDARY_INTERFACE},
        "fetch": {CodingElement.BOUNDARY_INTERFACE},
        "file": {CodingElement.BOUNDARY_INTERFACE},
        "database": {CodingElement.BOUNDARY_INTERFACE},
        "network": {CodingElement.BOUNDARY_INTERFACE},
        "try": {CodingElement.ERROR_HANDLING},
        "catch": {CodingElement.ERROR_HANDLING},
        "exception": {CodingElement.ERROR_HANDLING},
        "error": {CodingElement.ERROR_HANDLING},
        "fallback": {CodingElement.ERROR_HANDLING},
        "type": {CodingElement.TYPE_SCHEMA},
        "schema": {CodingElement.TYPE_SCHEMA},
        "validate": {CodingElement.TYPE_SCHEMA},
        "struct": {CodingElement.TYPE_SCHEMA},
        "interface": {CodingElement.TYPE_SCHEMA, CodingElement.BOUNDARY_INTERFACE},
    }
    elements: Set[CodingElement] = set()
    for kw in keywords:
        kw_lower = kw.lower()
        for trigger, elems in keyword_element_map.items():
            if trigger in kw_lower:
                elements.update(elems)
    return elements


def _normalize_keywords(keywords: Set[str]) -> Set[str]:
    """Normalize keywords to lowercase for consistent matching."""
    return {kw.lower() for kw in keywords}


# ═══════════════════════════════════════════════════════════════════
# CD2 + CD3: Theorem Library (CA2)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class TheoremCheckResult:
    """Result of checking a single theorem against code."""

    theorem_id: str
    passed: bool
    detail: str = ""


TheoremChecker = Callable[[str], TheoremCheckResult]


def _try_parse_ast(code: str) -> Optional[ast.Module]:
    """Parse code into AST; return None if syntax is invalid."""
    try:
        return ast.parse(code)
    except SyntaxError:
        return None


# ── AST helpers ─────────────────────────────────────────────────

_NONDETERMINISTIC_NAMES = frozenset({
    "random", "randint", "choice", "shuffle", "sample",
    "uuid4", "uuid1", "now", "utcnow", "time",
})

_NONDETERMINISTIC_ATTRS = frozenset({
    ("random", "random"), ("random", "randint"), ("random", "choice"),
    ("random", "shuffle"), ("random", "sample"),
    ("datetime", "now"), ("datetime", "utcnow"),
    ("time", "time"), ("uuid", "uuid4"), ("uuid", "uuid1"),
})


def _ast_has_nondeterministic_call(tree: ast.Module) -> Optional[str]:
    """Walk AST to find nondeterministic function calls."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name):
                pair = (func.value.id, func.attr)
                if pair in _NONDETERMINISTIC_ATTRS:
                    return f"{pair[0]}.{pair[1]}()"
            if func.attr in _NONDETERMINISTIC_NAMES:
                val_name = getattr(func.value, "id", "?")
                return f"{val_name}.{func.attr}()"
        elif isinstance(func, ast.Name) and func.id in _NONDETERMINISTIC_NAMES:
            return f"{func.id}()"
    return None


def _ast_while_true_missing_break(tree: ast.Module) -> bool:
    """Check if any ``while True`` loop lacks a ``break`` in its body."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.While):
            continue
        test = node.test
        is_true = isinstance(test, ast.Constant) and test.value is True
        if not is_true:
            continue
        has_break = any(isinstance(n, ast.Break) for n in ast.walk(node))
        if not has_break:
            return True
    return False


def _ast_has_global_stmt(tree: ast.Module) -> bool:
    """Detect ``global`` statements in function bodies."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            return True
    return False


def _ast_has_bare_except_pass(tree: ast.Module) -> bool:
    """Detect ``except: pass`` — swallows all errors."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            if (len(node.body) == 1
                    and isinstance(node.body[0], ast.Pass)):
                return True
    return False


def _ast_try_without_handler(tree: ast.Module) -> bool:
    """Detect ``try`` block with no except/finally handlers."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            if not node.handlers and not node.finalbody:
                return True
        if hasattr(ast, "TryStar") and isinstance(node, ast.TryStar):
            if not node.handlers and not node.finalbody:
                return True
    return False


def _ast_has_eval_call(tree: ast.Module) -> bool:
    """Detect ``eval()`` or ``exec()`` calls."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in ("eval", "exec"):
                return True
    return False


def _ast_open_without_context_manager(tree: ast.Module) -> bool:
    """Detect ``open()`` calls outside ``with`` statements.

    Allows open() inside ``with`` blocks and cases where the same scope
    contains ``.close()`` or a ``try/finally`` with ``.close()``.
    """
    with_targets: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            for item in node.items:
                cv = item.context_expr
                if isinstance(cv, ast.Call) and isinstance(cv.func, ast.Name):
                    if cv.func.id == "open":
                        with_targets.add(id(cv))

    has_close = False
    has_finally_close = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "close":
                has_close = True
        if isinstance(node, (ast.Try,)):
            for fb_node in ast.walk(ast.Module(body=node.finalbody, type_ignores=[])):
                if isinstance(fb_node, ast.Call) and isinstance(fb_node.func, ast.Attribute):
                    if fb_node.func.attr == "close":
                        has_finally_close = True

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_open = (isinstance(func, ast.Name) and func.id == "open") or \
                  (isinstance(func, ast.Attribute) and func.attr == "open")
        if not is_open:
            continue
        if id(node) in with_targets:
            continue
        if has_close or has_finally_close:
            continue
        return True
    return False


def _ast_http_request_without_status_check(tree: ast.Module) -> bool:
    """Detect ``requests.get/post/put/delete()`` without status/error check."""
    http_methods = {"get", "post", "put", "delete", "patch", "head"}
    has_request = False
    has_check = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                if node.func.value.id == "requests" and node.func.attr in http_methods:
                    has_request = True
            if node.func.attr in ("raise_for_status",):
                has_check = True
        if isinstance(node, ast.Attribute):
            if node.attr in ("status_code", "ok"):
                has_check = True
    return has_request and not has_check


def _ast_external_input_without_validation(tree: ast.Module) -> bool:
    """Detect external input usage without validation."""
    external_funcs = {"input"}
    external_attrs = {("request", "args"), ("request", "form"),
                      ("request", "json"), ("request", "data"),
                      ("sys", "argv")}
    validation_funcs = {"validate", "sanitize", "isinstance", "int", "float",
                        "str", "bool", "strip"}
    has_external = False
    has_validation = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in external_funcs:
                has_external = True
            if isinstance(func, ast.Name) and func.id in validation_funcs:
                has_validation = True
            if isinstance(func, ast.Attribute):
                if func.attr in ("get", "strip", "validate", "sanitize"):
                    has_validation = True
                if isinstance(func.value, ast.Name):
                    pair = (func.value.id, func.attr)
                    if pair in external_attrs:
                        has_external = True
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
            if isinstance(node.value.value, ast.Name):
                pair = (node.value.value.id, node.value.attr)
                if pair in external_attrs:
                    has_external = True
    return has_external and not has_validation


# ── Checker implementations (AST with regex fallback) ───────────

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


def _infer_return_type(val: ast.expr) -> type | None:
    """Infer the Python type of a simple AST expression."""
    if isinstance(val, ast.Constant):
        return type(val.value)
    if isinstance(val, (ast.List, ast.ListComp)):
        return list
    if isinstance(val, (ast.Dict, ast.DictComp)):
        return dict
    if isinstance(val, (ast.Set, ast.SetComp)):
        return set
    if isinstance(val, ast.Tuple):
        return tuple
    if isinstance(val, ast.JoinedStr):
        return str
    if isinstance(val, ast.BinOp):
        left_t = _infer_return_type(val.left)
        right_t = _infer_return_type(val.right)
        if left_t == str or right_t == str:
            return str
        if left_t in (int, float) or right_t in (int, float):
            return int if left_t == int and right_t == int else float
    if isinstance(val, ast.Call) and isinstance(val.func, ast.Name):
        builtin_returns = {"str": str, "int": int, "float": float, "list": list,
                           "dict": dict, "set": set, "tuple": tuple, "bool": bool,
                           "len": int, "sorted": list, "reversed": list}
        return builtin_returns.get(val.func.id)
    return None


def _ast_composability_violation(tree: ast.Module) -> str | None:
    """Detect composition violations: functions that return
    incompatible types on different branches.
    """
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        returns: list[type | None] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Return) and child.value is not None:
                inferred = _infer_return_type(child.value)
                if inferred is not None:
                    returns.append(inferred)
        if len(returns) >= 2:
            type_set = {t for t in returns if t is not None and t is not type(None)}
            if len(type_set) > 1:
                incompatible_pairs = [
                    ({str, int}, "str + int"),
                    ({str, float}, "str + float"),
                    ({str, list}, "str + list"),
                    ({dict, list}, "dict + list"),
                    ({int, list}, "int + list"),
                    ({str, dict}, "str + dict"),
                ]
                for pair_set, pair_name in incompatible_pairs:
                    if pair_set.issubset(type_set):
                        return f"function '{node.name}' returns incompatible types: {pair_name}"
    return None


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


def _ast_idempotency_violation(tree: ast.Module) -> str | None:
    """Detect non-idempotent patterns in code that should be idempotent.

    Checks for side-effects that break idempotency:
    1. list.append/extend/insert inside functions (accumulating state)
    2. set.add without existence check in loops
    3. counter += 1 / counter = counter + 1 patterns (accumulating)
    4. file write in append mode without truncation
    5. DB INSERT without ON CONFLICT / upsert guard
    6. global/nonlocal mutation
    """
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        has_global = any(isinstance(n, (ast.Global, ast.Nonlocal)) for n in ast.walk(node))
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                if child.func.attr in ("append", "extend", "insert"):
                    return (f"'{child.func.attr}()' in function '{node.name}' "
                            "mutates state non-idempotently")
            if isinstance(child, ast.AugAssign):
                if isinstance(child.op, ast.Add) and has_global:
                    return (f"augmented assignment '+=' with global/nonlocal "
                            f"in '{node.name}' is non-idempotent")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "open":
                for kw in node.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        if "a" in str(kw.value.value):
                            return "file opened in append mode — non-idempotent"
                if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                    if "a" in str(node.args[1].value):
                        return "file opened in append mode — non-idempotent"
    return None


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
        """CD5: Activate theorems matching keywords or elements.

        Applies keyword normalization and baseline theorem injection (CD5).
        """
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


# ═══════════════════════════════════════════════════════════════════
# CD4: Experience Library (CA3a/CA3b)
# ═══════════════════════════════════════════════════════════════════

def _default_memory_scope() -> "MemoryScope":
    from butler.memory.memory_scope import MemoryScope

    return MemoryScope()


@dataclass
class CodingExperience:
    """A coding experience: a time-bound best practice (CA3, CD4)."""

    id: str
    title: str
    domain: List[str]
    theorem_basis: Set[str]  # B_x
    context: str
    pattern: str
    benchmarks: Dict[str, str] = field(default_factory=dict)
    validity_start: float = 0.0
    validity_end: float = float("inf")
    supersedes: Optional[str] = None
    scope: "MemoryScope" = field(default_factory=lambda: _default_memory_scope())

    def is_valid(self, now: Optional[float] = None) -> bool:
        t = now if now is not None else time.time()
        return self.validity_start <= t <= self.validity_end

    def covers_theorems(self, activated: Set[str]) -> bool:
        return activated.issubset(self.theorem_basis)


class ExperienceLibrary:
    """Manages the experience library (CA3a/CA3b, CD4)."""

    def __init__(self, theorem_lib: Optional[TheoremLibrary] = None) -> None:
        self._experiences: Dict[str, CodingExperience] = {}
        self._theorem_lib = theorem_lib

    def _validate_pattern(self, exp: CodingExperience) -> Tuple[bool, str]:
        """Validate experience pattern against theorem basis (P-CT3a)."""
        if not self._theorem_lib or not exp.theorem_basis:
            return True, "no theorem lib or empty basis"
        activated = {}
        for tid in exp.theorem_basis:
            t = self._theorem_lib.get(tid)
            if t:
                activated[tid] = t
        results = verify_theorems(exp.pattern, activated)
        failed = [r for r in results if not r.passed]
        if failed:
            details = "; ".join(f"{r.theorem_id}: {r.detail}" for r in failed)
            return False, f"pattern violates theorems: {details}"
        return True, "ok"

    def add(self, exp: CodingExperience,
            skip_validation: bool = False) -> Tuple[bool, str]:
        """Add experience with optional theorem validation (CT3 safety)."""
        if not skip_validation:
            ok, detail = self._validate_pattern(exp)
            if not ok:
                return False, detail
        self._experiences[exp.id] = exp
        return True, "ok"

    def remove(self, exp_id: str) -> Optional[CodingExperience]:
        return self._experiences.pop(exp_id, None)

    def get(self, exp_id: str) -> Optional[CodingExperience]:
        return self._experiences.get(exp_id)

    @property
    def count(self) -> int:
        return len(self._experiences)

    @staticmethod
    def _is_b9_experience(exp: "CodingExperience") -> bool:
        return any(str(d).lower() == "b9" for d in exp.domain)

    @staticmethod
    def _experience_search_blob(exp: "CodingExperience") -> str:
        parts = [exp.context, exp.title, exp.pattern[:400]]
        parts.extend(str(d) for d in exp.domain)
        parts.extend(str(v) for v in exp.benchmarks.values())
        return " ".join(parts).lower()

    @classmethod
    def _keyword_match_score(cls, exp: "CodingExperience", normalized: Set[str]) -> int:
        blob = cls._experience_search_blob(exp)
        retrieval = str(exp.benchmarks.get("retrieval_keywords", "")).lower()
        score = 0
        for kw in normalized:
            if retrieval and kw in retrieval:
                score += 3
            elif kw in blob:
                score += 1
        return score

    @staticmethod
    def _is_failure_experience(exp: "CodingExperience") -> bool:
        return (
            str(exp.id).startswith("B9_FAIL_")
            or "failure" in [str(d).lower() for d in exp.domain]
        )

    @staticmethod
    def _failure_experience_allowed(
        exp: "CodingExperience",
        *,
        failure_class: str,
    ) -> bool:
        """B9_FAIL_* rows only when classification explicitly matches."""
        if not ExperienceLibrary._is_failure_experience(exp):
            return True
        want = (failure_class or "").strip().lower()
        if not want:
            return False
        have = str(exp.benchmarks.get("failure_class") or "").strip().lower()
        if have:
            return have == want
        for dom in exp.domain:
            d = str(dom).lower()
            if d not in ("b9", "failure", "auto", "prod_shaped", "pytest"):
                return d == want
        return False

    def search(self, keywords: Set[str], activated_theorems: Set[str],
               now: Optional[float] = None,
               strict_coverage: bool = False,
               *,
               project_id: str = "",
               stack_tags: frozenset[str] | set[str] | None = None,
               failure_class: str = "") -> List[CodingExperience]:
        """Retrieve valid, compatible experiences sorted by coverage.

        Args:
            strict_coverage: If True, require theorem_basis ⊇ activated_theorems
                           (CD5b). If False, allow partial overlap.
                           B9-tagged experiences use partial overlap even when strict.
            failure_class: When set, allow B9_FAIL_* only if benchmarks/domain match.
        """
        normalized = _normalize_keywords(keywords)
        scope_tags = frozenset(stack_tags or ())
        results = []
        for exp in self._experiences.values():
            if not exp.is_valid(now):
                continue
            if not self._failure_experience_allowed(exp, failure_class=failure_class):
                continue
            if project_id or scope_tags:
                if not exp.scope.visible_to(project_id=project_id, stack_tags=scope_tags):
                    continue
            if self._keyword_match_score(exp, normalized) <= 0:
                continue
            if activated_theorems:
                is_b9 = self._is_b9_experience(exp)
                if strict_coverage and not is_b9:
                    if not exp.covers_theorems(activated_theorems):
                        continue
                elif strict_coverage and is_b9:
                    if not bool(exp.theorem_basis & activated_theorems):
                        continue
                elif not bool(exp.theorem_basis & activated_theorems):
                    continue
            results.append(exp)
        results.sort(
            key=lambda e: (
                self._keyword_match_score(e, normalized),
                1 if self._is_b9_experience(e) else 0,
                len(e.theorem_basis),
            ),
            reverse=True,
        )
        return results

    @classmethod
    def load_merged_for_project(
        cls,
        *,
        tenant_path: str,
        project_workspace: str | None = None,
        theorem_lib: Optional["TheoremLibrary"] = None,
    ) -> "ExperienceLibrary":
        """Load L4 tenant corpus + optional L3 project file into one library."""
        merged = cls.load_from_file(tenant_path, theorem_lib=theorem_lib)
        if project_workspace:
            from butler.memory.memory_scope import project_coding_experiences_path

            proj_path = project_coding_experiences_path(project_workspace)
            proj_lib = cls.load_from_file(str(proj_path), theorem_lib=theorem_lib)
            for exp_id, exp in proj_lib._experiences.items():
                merged._experiences[exp_id] = exp
        return merged

    def backfill_scopes(self) -> int:
        """Infer MemoryScope on legacy rows; return count updated."""
        from butler.memory.memory_scope import backfill_experience_scope

        updated = 0
        for exp in self._experiences.values():
            if backfill_experience_scope(exp):
                updated += 1
        return updated

    def replace(self, old_id: str, new_exp: CodingExperience,
                skip_validation: bool = False) -> Tuple[bool, str]:
        """Replace old experience with new one (CT3 safety)."""
        if old_id not in self._experiences:
            return False, f"old experience {old_id} not found"
        if not skip_validation:
            ok, detail = self._validate_pattern(new_exp)
            if not ok:
                return False, detail
        new_exp.supersedes = old_id
        self._experiences.pop(old_id)
        self._experiences[new_exp.id] = new_exp
        return True, "ok"

    # ── Lifecycle Management (P3-2) ──────────────────────────────

    def renew(self, exp_id: str, extend_days: float = 90.0) -> bool:
        """Extend an experience's validity window on successful use."""
        exp = self._experiences.get(exp_id)
        if exp is None:
            return False
        exp.validity_end = max(exp.validity_end, time.time() + extend_days * 86400)
        return True

    def demote(self, exp_id: str, shrink_days: float = 30.0) -> bool:
        """Shrink an experience's validity window on failed evaluation."""
        exp = self._experiences.get(exp_id)
        if exp is None:
            return False
        new_end = exp.validity_end - shrink_days * 86400
        exp.validity_end = max(new_end, time.time())
        return True

    def expire_stale(self, now: Optional[float] = None) -> List[str]:
        """Remove experiences whose validity window has ended. Returns removed IDs."""
        t = now if now is not None else time.time()
        stale = [eid for eid, exp in self._experiences.items()
                 if exp.validity_end < t]
        for eid in stale:
            del self._experiences[eid]
        return stale

    def lifecycle_pass(self, eval_results: Dict[str, bool],
                       now: Optional[float] = None) -> Dict[str, Any]:
        """Run a full lifecycle pass: renew successes, demote failures, expire stale.

        Args:
            eval_results: mapping of experience_id → success (True/False)
        """
        renewed = 0
        demoted = 0
        for eid, success in eval_results.items():
            if success:
                if self.renew(eid):
                    renewed += 1
            else:
                if self.demote(eid):
                    demoted += 1
        expired = self.expire_stale(now)
        return {
            "renewed": renewed,
            "demoted": demoted,
            "expired": len(expired),
            "expired_ids": expired,
            "total_remaining": self.count,
        }

    # ── Persistence (JSON) ──────────────────────────────────────────

    def save_to_file(self, path: str) -> None:
        """Persist library to JSON (CA3b — preserves validity windows)."""
        import json
        from pathlib import Path as _Path

        records = []
        for exp in self._experiences.values():
            records.append({
                "id": exp.id,
                "title": exp.title,
                "domain": exp.domain,
                "theorem_basis": sorted(exp.theorem_basis),
                "context": exp.context,
                "pattern": exp.pattern,
                "benchmarks": exp.benchmarks,
                "validity_start": exp.validity_start,
                "validity_end": exp.validity_end,
                "supersedes": exp.supersedes,
                "scope": exp.scope.to_dict(),
            })
        p = _Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(records, ensure_ascii=False, indent=2),
                      encoding="utf-8")

    @classmethod
    def load_from_file(cls, path: str,
                       theorem_lib: Optional["TheoremLibrary"] = None,
                       ) -> "ExperienceLibrary":
        """Load library from JSON, skipping invalid entries."""
        import json
        from pathlib import Path as _Path

        lib = cls(theorem_lib=theorem_lib)
        p = _Path(path)
        if not p.is_file():
            return lib
        try:
            records = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return lib
        for rec in records:
            from butler.memory.memory_scope import MemoryScope, infer_default_scope

            scope_raw = rec.get("scope")
            if scope_raw:
                scope = MemoryScope.from_dict(scope_raw)
            else:
                scope = infer_default_scope(
                    exp_id=str(rec.get("id", "")),
                    domain=rec.get("domain", []),
                )
            exp = CodingExperience(
                id=rec.get("id", ""),
                title=rec.get("title", ""),
                domain=rec.get("domain", []),
                theorem_basis=set(rec.get("theorem_basis", [])),
                context=rec.get("context", ""),
                pattern=rec.get("pattern", ""),
                benchmarks=rec.get("benchmarks", {}),
                validity_start=rec.get("validity_start", 0.0),
                validity_end=rec.get("validity_end", float("inf")),
                supersedes=rec.get("supersedes"),
                scope=scope,
            )
            lib.add(exp, skip_validation=True)
        return lib

    def load_seed_if_empty(self) -> int:
        """Load seed experiences from bundled data if the library is empty.

        Returns the number of seed experiences loaded. Skips if the library
        already has entries (user/runtime data takes precedence over seeds).
        """
        if self._experiences:
            return 0
        import json
        from pathlib import Path as _Path

        seed_path = _Path(__file__).resolve().parent.parent.parent / "data" / "seed_experiences.json"
        if not seed_path.is_file():
            return 0
        try:
            records = json.loads(seed_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return 0
        loaded = 0
        for rec in records:
            from butler.memory.memory_scope import infer_default_scope

            exp = CodingExperience(
                id=rec.get("id", ""),
                title=rec.get("title", ""),
                domain=rec.get("domain", []),
                theorem_basis=set(rec.get("theorem_basis", [])),
                context=rec.get("context", ""),
                pattern=rec.get("pattern", ""),
                benchmarks=rec.get("benchmarks", {}),
                validity_start=rec.get("validity_start", 0.0),
                validity_end=rec.get("validity_end", float("inf")),
                supersedes=rec.get("supersedes"),
                scope=infer_default_scope(
                    exp_id=str(rec.get("id", "")),
                    domain=rec.get("domain", []),
                ),
            )
            ok, _ = self.add(exp, skip_validation=True)
            if ok:
                loaded += 1
        return loaded


# ═══════════════════════════════════════════════════════════════════
# CD6: Dual Verification Gate (CA4)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class DualVerificationResult:
    """Combined result of theorem + test verification (CD6)."""

    theorem_results: List[TheoremCheckResult] = field(default_factory=list)
    test_passed: bool = False
    test_detail: str = ""
    failed_test_cases: List[str] = field(default_factory=list)

    @property
    def theorem_passed(self) -> bool:
        if not self.theorem_results:
            return False
        return all(r.passed for r in self.theorem_results)

    @property
    def all_passed(self) -> bool:
        return self.theorem_passed and self.test_passed

    @property
    def violated_theorems(self) -> List[str]:
        return [r.theorem_id for r in self.theorem_results if not r.passed]


def verify_theorems(code: str,
                    activated: Dict[str, CodingTheorem]) -> List[TheoremCheckResult]:
    """Verify_thm: check code against all activated theorems (CD6)."""
    return [t.check(code) for t in activated.values()]


def dual_verify(code: str, activated_theorems: Dict[str, CodingTheorem],
                test_passed: bool, test_detail: str = "",
                failed_test_cases: Optional[List[str]] = None,
                ) -> DualVerificationResult:
    """Full dual verification gate (CA4, CD6)."""
    thm_results = verify_theorems(code, activated_theorems)
    return DualVerificationResult(
        theorem_results=thm_results,
        test_passed=test_passed,
        test_detail=test_detail,
        failed_test_cases=failed_test_cases or [],
    )


# ═══════════════════════════════════════════════════════════════════
# CD0/CD7/CD8: Spec, Process, Synthesize
# ═══════════════════════════════════════════════════════════════════

@dataclass
class CodingKnowledgeContext:
    """Full context for a coding task after knowledge layer processing."""

    task_keywords: Set[str]
    activated_elements: Set[CodingElement]
    activated_theorems: Dict[str, CodingTheorem]
    selected_experience: Optional[CodingExperience]
    mode: str  # "experience_guided" or "theorem_only"


def process_task(keywords: List[str],
                 theorem_lib: TheoremLibrary,
                 experience_lib: ExperienceLibrary,
                 now: Optional[float] = None,
                 strict_experience: bool = True,
                 *,
                 project_id: str = "",
                 stack_tags: frozenset[str] | set[str] | None = None) -> CodingKnowledgeContext:
    """End-to-end coding knowledge processing (CD7).

    PLAN phase: decompose → activate theorems → search experience.
    """
    kw_set = set(keywords)
    elements = decompose_task(keywords)
    activated = theorem_lib.activate(kw_set, elements)
    activated_ids = set(activated.keys())

    candidates = experience_lib.search(
        kw_set, activated_ids, now,
        strict_coverage=strict_experience,
        project_id=project_id,
        stack_tags=stack_tags,
    )
    selected = candidates[0] if candidates else None
    mode = "experience_guided" if selected else "theorem_only"

    return CodingKnowledgeContext(
        task_keywords=kw_set,
        activated_elements=elements,
        activated_theorems=activated,
        selected_experience=selected,
        mode=mode,
    )


# ═══════════════════════════════════════════════════════════════════
# CD8: Code Synthesizer — constraint-driven code suggestion (CA3+CA4)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class SynthConstraint:
    """A single constraint derived from an activated theorem or experience."""

    source: str
    category: str  # "must", "must_not", "prefer"
    description: str


@dataclass
class SynthResult:
    """Result of CD8 synthesis — constraints + optional template."""

    constraints: List[SynthConstraint]
    template_hint: str = ""
    experience_pattern: str = ""
    activated_theorem_ids: List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        must = [c for c in self.constraints if c.category == "must"]
        must_not = [c for c in self.constraints if c.category == "must_not"]
        parts = []
        if must:
            parts.append("MUST: " + "; ".join(c.description for c in must))
        if must_not:
            parts.append("MUST NOT: " + "; ".join(c.description for c in must_not))
        return " | ".join(parts) if parts else "no constraints"


_THEOREM_CONSTRAINTS: Dict[str, List[SynthConstraint]] = {
    "T01": [
        SynthConstraint("T01", "must_not", "avoid nondeterministic calls (random/time/uuid) in pure functions"),
        SynthConstraint("T01", "must", "same input always produces same output"),
    ],
    "T02": [
        SynthConstraint("T02", "must", "functions must return consistent types across all branches"),
        SynthConstraint("T02", "must_not", "avoid returning incompatible types (e.g. str on one branch, int on another)"),
        SynthConstraint("T02", "prefer", "use type annotations on function signatures for composition clarity"),
    ],
    "T03": [
        SynthConstraint("T03", "must_not", "avoid eval()/exec()"),
        SynthConstraint("T03", "must", "use proper type conversions"),
    ],
    "T04": [
        SynthConstraint("T04", "must", "every loop/recursion must have a termination condition"),
        SynthConstraint("T04", "must_not", "avoid while True without break/return"),
    ],
    "T05": [
        SynthConstraint("T05", "must_not", "avoid global mutable state"),
        SynthConstraint("T05", "must", "minimize mutable state scope"),
    ],
    "T06": [
        SynthConstraint("T06", "must", "every try must have proper exception handling"),
        SynthConstraint("T06", "must_not", "avoid bare except:pass"),
    ],
    "T07": [
        SynthConstraint("T07", "must", "operations must be idempotent — calling twice yields the same result as calling once"),
        SynthConstraint("T07", "must_not", "avoid list.append/extend in functions that may be retried"),
        SynthConstraint("T07", "must_not", "avoid file open in append mode for idempotent operations"),
        SynthConstraint("T07", "prefer", "use dict assignment or set operations instead of list append for idempotent writes"),
    ],
    "T08": [
        SynthConstraint("T08", "must", "use context managers (with) for resources"),
        SynthConstraint("T08", "must_not", "avoid open() without with/close/finally"),
    ],
    "T09": [
        SynthConstraint("T09", "must", "check HTTP response status after requests"),
    ],
    "T10": [
        SynthConstraint("T10", "must", "validate all external input before use"),
        SynthConstraint("T10", "must_not", "never trust user/network input directly"),
    ],
}


def synthesize(ctx: CodingKnowledgeContext) -> SynthResult:
    """CD8 Synthesizer: derive constraints and template from knowledge context.

    Takes the output of ``process_task`` and produces actionable constraints
    that guide code generation toward theorem-compliant implementations.
    """
    constraints: List[SynthConstraint] = []
    for tid in sorted(ctx.activated_theorems.keys()):
        cs = _THEOREM_CONSTRAINTS.get(tid, [])
        constraints.extend(cs)

    template_hint = ""
    experience_pattern = ""
    if ctx.selected_experience:
        experience_pattern = ctx.selected_experience.pattern
        constraints.append(SynthConstraint(
            f"EXP:{ctx.selected_experience.id}",
            "prefer",
            f"follow pattern from experience '{ctx.selected_experience.title}'",
        ))

    if CodingElement.ERROR_HANDLING in ctx.activated_elements:
        template_hint += "try:\n    ...\nexcept SpecificError as e:\n    handle(e)\n"
    if CodingElement.BOUNDARY_INTERFACE in ctx.activated_elements:
        template_hint += "with resource_manager() as r:\n    ...\n"

    return SynthResult(
        constraints=constraints,
        template_hint=template_hint,
        experience_pattern=experience_pattern,
        activated_theorem_ids=sorted(ctx.activated_theorems.keys()),
    )


# ═══════════════════════════════════════════════════════════════════
# CD6 GenTC: Test Case Generation — equivalence class partitioning
# ═══════════════════════════════════════════════════════════════════

@dataclass
class TestCase:
    """A generated test case from equivalence class partitioning (H10)."""

    id: str
    category: str  # "normal", "boundary", "error", "negative"
    description: str
    input_sketch: str
    expected_behavior: str
    theorem_source: str = ""


@dataclass
class GenTCResult:
    """Result of test case generation."""

    test_cases: List[TestCase]
    coverage_classes: List[str]

    @property
    def count(self) -> int:
        return len(self.test_cases)

    @property
    def category_breakdown(self) -> Dict[str, int]:
        breakdown: Dict[str, int] = {}
        for tc in self.test_cases:
            breakdown[tc.category] = breakdown.get(tc.category, 0) + 1
        return breakdown


_THEOREM_TEST_PATTERNS: Dict[str, List[TestCase]] = {
    "T01": [
        TestCase("T01_norm", "normal", "same input → same output", "f(x)", "f(x) == f(x)", "T01"),
        TestCase("T01_bound", "boundary", "empty/null input determinism", "f(None), f([])", "consistent result", "T01"),
    ],
    "T02": [
        TestCase("T02_norm", "normal", "composed functions type-compatible", "g(f(x))", "no TypeError", "T02"),
        TestCase("T02_neg", "negative", "incompatible return types detected", "f() returns int or str", "checker flags violation", "T02"),
        TestCase("T02_bound", "boundary", "None return in optional chain", "f() → None | T, g(T)", "handles None gracefully", "T02"),
    ],
    "T03": [
        TestCase("T03_norm", "normal", "valid typed input accepted", "valid_typed_value", "no TypeError", "T03"),
        TestCase("T03_neg", "negative", "invalid type rejected", "wrong_type_value", "raises TypeError/ValueError", "T03"),
    ],
    "T04": [
        TestCase("T04_norm", "normal", "finite input terminates", "small_collection", "returns in finite time", "T04"),
        TestCase("T04_bound", "boundary", "empty input terminates", "empty_input", "returns immediately", "T04"),
        TestCase("T04_bound2", "boundary", "large input terminates", "max_size_input", "returns within timeout", "T04"),
    ],
    "T05": [
        TestCase("T05_norm", "normal", "no external state mutation", "call_function()", "global state unchanged", "T05"),
    ],
    "T06": [
        TestCase("T06_norm", "normal", "normal execution succeeds", "valid_input", "success", "T06"),
        TestCase("T06_err", "error", "error leaves no side effects", "error_trigger", "state unchanged after error", "T06"),
        TestCase("T06_bound", "boundary", "exception propagation correct", "edge_case", "proper exception type", "T06"),
    ],
    "T07": [
        TestCase("T07_norm", "normal", "calling twice yields same result as once", "op(); op()", "state == after single op()", "T07"),
        TestCase("T07_neg", "negative", "append in retry context detected", "retry(lambda: items.append(x))", "checker flags non-idempotent", "T07"),
        TestCase("T07_bound", "boundary", "set/dict operations are idempotent", "d[k]=v; d[k]=v", "state unchanged after repeat", "T07"),
    ],
    "T08": [
        TestCase("T08_norm", "normal", "resource acquired and released", "normal_op", "resource closed", "T08"),
        TestCase("T08_err", "error", "resource released on error", "error_during_use", "resource still closed", "T08"),
    ],
    "T09": [
        TestCase("T09_norm", "normal", "API success path", "valid_request", "proper response handling", "T09"),
        TestCase("T09_err", "error", "API error response handled", "error_response", "graceful degradation", "T09"),
        TestCase("T09_bound", "boundary", "API timeout handled", "slow_endpoint", "timeout exception caught", "T09"),
    ],
    "T10": [
        TestCase("T10_norm", "normal", "valid input accepted", "clean_input", "processed correctly", "T10"),
        TestCase("T10_neg", "negative", "malicious input rejected", "injection_attempt", "sanitized/rejected", "T10"),
        TestCase("T10_bound", "boundary", "empty input handled", "empty_string", "no crash", "T10"),
    ],
}


def generate_test_cases(ctx: CodingKnowledgeContext) -> GenTCResult:
    """CD6 GenTC: Generate test cases via equivalence class partitioning (H10).

    For each activated theorem, produces normal/boundary/error/negative test
    case sketches. The result is a blueprint for test implementation.
    """
    test_cases: List[TestCase] = []
    coverage_classes: List[str] = []

    for tid in sorted(ctx.activated_theorems.keys()):
        patterns = _THEOREM_TEST_PATTERNS.get(tid, [])
        for p in patterns:
            tc = TestCase(
                id=f"{p.id}_{len(test_cases)}",
                category=p.category,
                description=p.description,
                input_sketch=p.input_sketch,
                expected_behavior=p.expected_behavior,
                theorem_source=tid,
            )
            test_cases.append(tc)
        if patterns:
            coverage_classes.append(f"{tid}: {len(patterns)} equivalence classes")

    for elem in sorted(ctx.activated_elements, key=lambda e: e.value):
        tc = TestCase(
            id=f"ELEM_{elem.value}_{len(test_cases)}",
            category="normal",
            description=f"element {elem.value} basic behavior",
            input_sketch="standard_input",
            expected_behavior=f"{elem.value} properties hold",
        )
        test_cases.append(tc)
        coverage_classes.append(f"Element:{elem.value}")

    return GenTCResult(test_cases=test_cases, coverage_classes=coverage_classes)


def format_coding_guidance_block(ctx: CodingKnowledgeContext, *, max_cases: int = 6) -> str:
    """Format Synth + GenTC output for delegate/dev prompt injection (O5)."""
    synth = synthesize(ctx)
    gentc = generate_test_cases(ctx)
    lines = ["<coding-guidance>"]
    if synth.constraints:
        lines.append("## Theorem constraints")
        for c in synth.constraints[:12]:
            lines.append(f"- [{c.source}] ({c.category}) {c.description}")
    if synth.template_hint.strip():
        lines.append("## Suggested template")
        lines.append(synth.template_hint.strip())
    if synth.experience_pattern:
        lines.append(f"## Experience pattern\n{synth.experience_pattern[:400]}")
    if gentc.test_cases:
        lines.append("## Equivalence-class test sketches")
        for tc in gentc.test_cases[:max_cases]:
            lines.append(
                f"- ({tc.category}) {tc.description}: {tc.input_sketch} → {tc.expected_behavior}"
            )
    lines.append("</coding-guidance>")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# Experience Candidate Extraction (post-task success)
# ═══════════════════════════════════════════════════════════════════

def extract_experience_candidate(
    task_description: str,
    code_snippets: List[str],
    activated_theorems: Dict[str, CodingTheorem],
    *,
    domain: Optional[List[str]] = None,
) -> Optional[CodingExperience]:
    """Extract a candidate experience from a successfully completed task.

    Called after a dev task passes dual verification.  The candidate is
    validated against theorem basis before returning (CT3 safety).
    Returns None if validation fails or no meaningful pattern emerges.
    """
    if not code_snippets or not activated_theorems:
        return None

    best_snippet = max(code_snippets, key=len)
    if len(best_snippet) < 20:
        return None

    thm_results = verify_theorems(best_snippet, activated_theorems)
    if any(not r.passed for r in thm_results):
        return None

    import hashlib
    ts = str(time.time()).encode()
    exp_id = f"EX_{hashlib.sha256(ts + best_snippet[:100].encode()).hexdigest()[:12]}"

    words = task_description.lower().split()[:8]
    title = " ".join(words) if words else "auto-extracted"

    return CodingExperience(
        id=exp_id,
        title=title,
        domain=domain or ["auto"],
        theorem_basis=set(activated_theorems.keys()),
        context=task_description[:200],
        pattern=best_snippet[:2000],
        validity_start=time.time(),
        validity_end=time.time() + 180 * 86400,  # 180 days default TTL
    )
