"""Deterministic static code review (H13 — no LLM)."""

from __future__ import annotations

import ast
import logging
import os
import re
from pathlib import Path

from butler.contracts.review_ports import DevReviewView, ReviewFinding
from butler.core.review_context_adapter import merge_review_views
from butler.env_parse import int_env

logger = logging.getLogger(__name__)

_SECRET_PATTERNS = (
    re.compile(r"""(?i)(api[_-]?key|password|secret|token)\s*=\s*['"][^'"]{8,}['"]"""),
    re.compile(r"""(?i)Bearer\s+[A-Za-z0-9._\-]{20,}"""),
)

_GATEWAY_IMPORT_RE = re.compile(r"""^\s*from\s+butler\.gateway\b""")


def review_max_function_lines() -> int:
    return int(int_env("BUTLER_DEV_REVIEW_MAX_FUNCTION_LINES", 80))


def review_max_file_lines() -> int:
    return int(int_env("BUTLER_DEV_REVIEW_MAX_FILE_LINES", 600))


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _check_boundary_imports(path: Path, text: str) -> list[ReviewFinding]:
    rel = str(path).replace("\\", "/")
    if "/butler/core/" not in rel and not rel.endswith("/butler/core"):
        return []
    findings: list[ReviewFinding] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        if _GATEWAY_IMPORT_RE.match(line):
            findings.append(
                ReviewFinding(
                    severity="error",
                    rule_id="RK-BOUNDARY",
                    file=str(path.name),
                    line=idx,
                    message="core module imports butler.gateway directly",
                    evidence=line.strip()[:120],
                )
            )
    return findings


def _check_broad_except(path: Path, tree: ast.AST) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if node.type is None:
            continue
        if not isinstance(node.type, ast.Name) or node.type.id != "Exception":
            continue
        body = node.body or []
        has_log = any(
            isinstance(b, ast.Expr)
            and isinstance((val := b.value), ast.Call)
            and isinstance((func := val.func), ast.Attribute)
            and func.attr in ("debug", "info", "warning", "error", "exception")
            for b in body
        )
        has_reraise = any(isinstance(b, ast.Raise) for b in body)
        if has_log or has_reraise:
            continue
        findings.append(
            ReviewFinding(
                severity="warning",
                rule_id="RK-ERROR",
                file=str(path.name),
                line=int(getattr(node, "lineno", 0) or 0),
                message="broad except Exception without log or re-raise",
                evidence="except Exception",
            )
        )
    return findings


def _check_sizes(path: Path, tree: ast.AST, line_count: int) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    max_fn = review_max_function_lines()
    max_file = review_max_file_lines()
    if line_count > max_file:
        findings.append(
            ReviewFinding(
                severity="warning",
                rule_id="RK-SIZE",
                file=str(path.name),
                line=1,
                message=f"file exceeds {max_file} lines ({line_count})",
                evidence=f"lines={line_count}",
            )
        )
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        start = int(getattr(node, "lineno", 0) or 0)
        end = int(getattr(node, "end_lineno", start) or start)
        span = max(0, end - start + 1)
        if span > max_fn:
            findings.append(
                ReviewFinding(
                    severity="warning",
                    rule_id="RK-SIZE",
                    file=str(path.name),
                    line=start,
                    message=f"function `{node.name}` exceeds {max_fn} lines ({span})",
                    evidence=f"span={span}",
                )
            )
    return findings


def _check_secrets(path: Path, text: str) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        for pat in _SECRET_PATTERNS:
            if pat.search(line):
                findings.append(
                    ReviewFinding(
                        severity="error",
                        rule_id="RK-SECURITY",
                        file=str(path.name),
                        line=idx,
                        message="possible hardcoded secret",
                        evidence=line.strip()[:80],
                    )
                )
                break
    return findings


def _check_test_touch(path: Path, workspace: Path) -> list[ReviewFinding]:
    if path.suffix != ".py":
        return []
    if "test" in path.name.lower() or "/tests/" in str(path).replace("\\", "/"):
        return []
    stem = path.stem.replace("_", " ")
    tests_dir = workspace / "tests"
    if not tests_dir.is_dir():
        return []
    try:
        for candidate in tests_dir.rglob("*.py"):
            text = _read_text(candidate)
            if path.stem in text or stem.split()[0] in text:
                return []
    except OSError:
        return []
    return [
        ReviewFinding(
            severity="info",
            rule_id="RK-TEST",
            file=str(path.name),
            line=0,
            message="no tests/ reference found for changed module (heuristic)",
            evidence=f"stem={path.stem}",
        )
    ]


def review_file(path: Path, *, workspace: Path) -> DevReviewView:
    text = _read_text(path)
    if not text.strip():
        return DevReviewView(passed=True, metadata={"acl_shape": "empty_file"})
    findings: list[ReviewFinding] = []
    findings.extend(_check_boundary_imports(path, text))
    findings.extend(_check_secrets(path, text))
    findings.extend(_check_test_touch(path, workspace))
    try:
        tree = ast.parse(text, filename=str(path))
        findings.extend(_check_broad_except(path, tree))
        findings.extend(_check_sizes(path, tree, len(text.splitlines())))
    except SyntaxError as exc:
        findings.append(
            ReviewFinding(
                severity="error",
                rule_id="RK-SIZE",
                file=str(path.name),
                line=int(getattr(exc, "lineno", 0) or 0),
                message=f"syntax error: {exc.msg}",
                evidence=str(exc.msg or "")[:120],
            )
        )
    passed = not any(f.severity == "error" for f in findings)
    return DevReviewView(
        passed=passed,
        findings=findings,
        metadata={"source": "review_static", "file": str(path.name)},
    )


def resolve_changed_files(
    workspace: Path,
    *,
    changed_files: list[str] | None = None,
    edit_paths: list[str] | None = None,
) -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()
    for raw in list(changed_files or []) + list(edit_paths or []):
        rel = str(raw or "").strip()
        if not rel or rel in seen:
            continue
        seen.add(rel)
        fp = (workspace / rel).resolve()
        try:
            fp.relative_to(workspace.resolve())
        except ValueError:
            continue
        if fp.is_file():
            paths.append(fp)
    if paths:
        return paths
    for pattern in ("**/*.py",):
        for fp in workspace.glob(pattern):
            if fp.is_file() and "__pycache__" not in str(fp):
                paths.append(fp)
                if len(paths) >= 8:
                    return paths
    return paths


def run_static_review(
    workspace: Path,
    *,
    changed_files: list[str] | None = None,
    edit_paths: list[str] | None = None,
) -> DevReviewView:
    files = resolve_changed_files(
        workspace,
        changed_files=changed_files,
        edit_paths=edit_paths,
    )
    if not files:
        return DevReviewView(
            passed=True,
            metadata={"source": "review_static", "acl_empty": True},
        )
    views = [review_file(fp, workspace=workspace) for fp in files]
    return merge_review_views(*views)
