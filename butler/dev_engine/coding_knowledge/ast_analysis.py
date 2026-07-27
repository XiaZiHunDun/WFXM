"""AST analysis utilities for coding knowledge layer."""

from __future__ import annotations

import ast
import re
from typing import Optional, Set


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
    """Detect non-idempotent patterns in code that should be idempotent."""
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


__all__ = [
    "_try_parse_ast",
    "_ast_has_nondeterministic_call",
    "_ast_while_true_missing_break",
    "_ast_has_global_stmt",
    "_ast_has_bare_except_pass",
    "_ast_try_without_handler",
    "_ast_has_eval_call",
    "_ast_open_without_context_manager",
    "_ast_http_request_without_status_check",
    "_ast_external_input_without_validation",
    "_infer_return_type",
    "_ast_composability_violation",
    "_ast_idempotency_violation",
]