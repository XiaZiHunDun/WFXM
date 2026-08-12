"""Theorem Library — Coding theorem checkers and library (CA2, CD2, CD3).

CD2 + CD3: Theorem taxonomy, checkers, and library management.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Set

from butler.dev_engine.coding_elements import (
    CodingElement,
    BASELINE_THEOREMS,
    _normalize_keywords,
)


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
    """Detect ``open()`` calls outside ``with`` statements."""
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
    """Detect composition violations: functions that return incompatible types."""
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
            type_set: set[type] = {
                t for t in returns if t is not None and t is not type(None)
            }
            if len(type_set) > 1:
                incompatible_pairs: list[tuple[set[type], str]] = [
                    ({str, int}, "str + int"),
                    ({str, float}, "str + float"),
                    ({str, list}, "str + list"),
                    ({dict, list}, "dict + list"),
                    ({int, list}, "int + list"),
                    ({str, dict}, "str + dict"),
                ]
                for pair_set, pair_name in incompatible_pairs:
                    if all(t in type_set for t in pair_set):
                        return f"function '{node.name}' returns incompatible types: {pair_name}"
    return None


def _ast_idempotency_violation(tree: ast.Module) -> str | None:
    """Detect non-idempotent patterns in code."""
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


def _check_t01_determinism(code: str) -> TheoremCheckResult:
    """T01: Pure functions must be deterministic."""
    tree = _try_parse_ast(code)
    if tree is not None:
        hit = _ast_has_nondeterministic_call(tree)
        if hit:
            return TheoremCheckResult("T01", False, f"nondeterministic call: {hit}")
        return TheoremCheckResult("T01", True, "ok")
    nondeterministic = [
        r"\brandom\b", r"\brandint\b", r"\bchoice\b",
        r"datetime\.now\b", r"time\.time\b", r"\buuid\b",
    ]
    for pat in nondeterministic:
        if re.search(pat, code):
            return TheoremCheckResult("T01", False, f"nondeterministic pattern: {pat}")
    return TheoremCheckResult("T01", True, "ok")


def _check_t02_composability(code: str) -> TheoremCheckResult:
    """T02: Composition type compatibility."""
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
    """T03: Type safety — no eval/exec bypasses."""
    tree = _try_parse_ast(code)
    if tree is not None:
        if _ast_has_eval_call(tree):
            return TheoremCheckResult("T03", False, "eval()/exec() bypasses type safety")
        return TheoremCheckResult("T03", True, "ok")
    if re.search(r"\beval\s*\(", code):
        return TheoremCheckResult("T03", False, "eval() bypasses type safety")
    return TheoremCheckResult("T03", True, "ok")


def _check_t04_termination(code: str) -> TheoremCheckResult:
    """T04: Loops/recursion must terminate."""
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
    """T05: Mutable state scope minimized."""
    tree = _try_parse_ast(code)
    if tree is not None:
        if _ast_has_global_stmt(tree):
            return TheoremCheckResult("T05", False, "global keyword — state isolation violation")
        return TheoremCheckResult("T05", True, "ok")
    if "global " in code:
        for line in code.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if stripped.startswith("global "):
                return TheoremCheckResult("T05", False, "global keyword — state isolation violation")
    return TheoremCheckResult("T05", True, "ok")


def _check_t06_exception_safety(code: str) -> TheoremCheckResult:
    """T06: Strong exception safety."""
    tree = _try_parse_ast(code)
    if tree is not None:
        if _ast_try_without_handler(tree):
            return TheoremCheckResult("T06", False, "try without catch/except")
        if _ast_has_bare_except_pass(tree):
            return TheoremCheckResult("T06", False, "bare except:pass swallows all errors")
        return TheoremCheckResult("T06", True, "ok")
    has_try = "try:" in code or "try {" in code
    has_handler = ("except " in code or "except:" in code
                   or "catch " in code or "catch(" in code)
    if has_try and not has_handler:
        return TheoremCheckResult("T06", False, "try without catch/except")
    if re.search(r"except\s*:\s*pass", code):
        return TheoremCheckResult("T06", False, "bare except:pass swallows all errors")
    return TheoremCheckResult("T06", True, "ok")


def _check_t07_idempotency(code: str) -> TheoremCheckResult:
    """T07: Idempotent operations."""
    tree = _try_parse_ast(code)
    if tree is not None:
        violation = _ast_idempotency_violation(tree)
        if violation:
            return TheoremCheckResult("T07", False, violation)
        return TheoremCheckResult("T07", True, "ok")
    if re.search(r"\.append\s*\(", code):
        return TheoremCheckResult("T07", False, "append() mutates state non-idempotently")
    if re.search(r"open\s*\([^)]*['\"]a['\"]", code):
        return TheoremCheckResult("T07", False, "file opened in append mode — non-idempotent")
    return TheoremCheckResult("T07", True, "ok")


def _check_t08_resource_lifecycle(code: str) -> TheoremCheckResult:
    """T08: Every acquire must pair with release."""
    tree = _try_parse_ast(code)
    if tree is not None:
        if _ast_open_without_context_manager(tree):
            return TheoremCheckResult("T08", False, "resource opened without with/close/finally")
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
                return TheoremCheckResult("T08", False, "resource opened without with/close/finally")
    return TheoremCheckResult("T08", True, "ok")


def _check_t09_contract_adherence(code: str) -> TheoremCheckResult:
    """T09: API contract adherence."""
    tree = _try_parse_ast(code)
    if tree is not None:
        if _ast_http_request_without_status_check(tree):
            return TheoremCheckResult("T09", False, "HTTP request without status check")
        return TheoremCheckResult("T09", True, "ok")
    has_request = bool(re.search(r"requests\.(get|post|put|delete)\s*\(", code))
    if has_request:
        has_status_check = bool(re.search(r"(status_code|raise_for_status|\.ok\b)", code))
        if not has_status_check:
            return TheoremCheckResult("T09", False, "HTTP request without status check")
    return TheoremCheckResult("T09", True, "ok")


def _check_t10_trust_boundary(code: str) -> TheoremCheckResult:
    """T10: External data must be validated."""
    tree = _try_parse_ast(code)
    if tree is not None:
        if _ast_external_input_without_validation(tree):
            return TheoremCheckResult("T10", False, "external input used without validation")
        return TheoremCheckResult("T10", True, "ok")
    has_external = bool(re.search(r"\binput\s*\(|request\.(args|form|json|data)\b|sys\.argv\b", code))
    if has_external:
        has_validation = bool(re.search(r"(validate|sanitize|isinstance|int\(|float\(|strip\(|\.get\()", code))
        if not has_validation:
            return TheoremCheckResult("T10", False, "external input used without validation")
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
            triggers={"exception", "try", "catch", "error", "throw", "transaction"},
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
            triggers={"open", "close", "acquire", "release", "file", "connection"},
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
            triggers={"input", "external", "user", "network", "validate", "sanitize"},
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
    "verify_theorems",
]


def verify_theorems(code: str, activated_theorems: Dict[str, CodingTheorem]) -> list[TheoremCheckResult]:
    """Verify code against activated theorems."""
    results: list[TheoremCheckResult] = []
    for theorem_id, theorem in activated_theorems.items():
        result = theorem.check(code)
        results.append(result)
    return results
