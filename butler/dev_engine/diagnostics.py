"""Diagnostics collector — parse terminal output into structured diagnostics.

Formal model from v4-dev-engine-theory.md §5.3 DD3:
  Terminal output (pytest/ruff/tsc/gcc) → Diagnostic(file, line, severity, msg, source, rule)
"""

from __future__ import annotations

import re

from butler.dev_engine.dev_state import DiagSeverity, Diagnostic


def parse_diagnostics(output: str, source: str = "") -> list[Diagnostic]:
    """Parse terminal output into structured diagnostics.

    Dispatches to source-specific parsers. Falls back to
    generic colon-delimited format.
    """
    src = source.lower().strip()
    if src in ("ruff", "flake8"):
        return _parse_ruff(output)
    if src in ("pytest", "python"):
        return _parse_pytest(output)
    if src in ("mypy",):
        return _parse_mypy(output)
    if src in ("tsc", "typescript"):
        return _parse_tsc(output)
    if src in ("gcc", "g++", "clang"):
        return _parse_gcc(output)
    return _parse_generic(output)


_RUFF_RE = re.compile(
    r"^(.+?):(\d+):(\d+):\s+([A-Z]\d+)\s+(.+)$", re.MULTILINE
)


def _parse_ruff(output: str) -> list[Diagnostic]:
    results: list[Diagnostic] = []
    for m in _RUFF_RE.finditer(output):
        results.append(Diagnostic(
            file=m.group(1),
            line=int(m.group(2)),
            column=int(m.group(3)),
            severity=DiagSeverity.ERROR,
            message=m.group(5).strip(),
            source="ruff",
            rule=m.group(4),
        ))
    return results


_PYTEST_FAIL_RE = re.compile(
    r"^FAILED\s+(.+?)::(.+?)(?:\s+-\s+(.+))?$", re.MULTILINE
)
_PYTEST_ERROR_RE = re.compile(
    r"^E\s+(.+)$", re.MULTILINE
)


def _parse_pytest(output: str) -> list[Diagnostic]:
    results: list[Diagnostic] = []
    for m in _PYTEST_FAIL_RE.finditer(output):
        results.append(Diagnostic(
            file=m.group(1),
            line=0,
            severity=DiagSeverity.ERROR,
            message=f"{m.group(2)}: {m.group(3) or 'failed'}",
            source="pytest",
        ))
    if not results:
        for m in _PYTEST_ERROR_RE.finditer(output):
            results.append(Diagnostic(
                file="",
                line=0,
                severity=DiagSeverity.ERROR,
                message=m.group(1).strip(),
                source="pytest",
            ))
    return results


_MYPY_RE = re.compile(
    r"^(.+?):(\d+):\s+(error|warning|note):\s+(.+?)(?:\s+\[(.+?)\])?$",
    re.MULTILINE,
)


def _parse_mypy(output: str) -> list[Diagnostic]:
    results: list[Diagnostic] = []
    sev_map = {"error": DiagSeverity.ERROR, "warning": DiagSeverity.WARNING, "note": DiagSeverity.INFO}
    for m in _MYPY_RE.finditer(output):
        results.append(Diagnostic(
            file=m.group(1),
            line=int(m.group(2)),
            severity=sev_map.get(m.group(3), DiagSeverity.ERROR),
            message=m.group(4).strip(),
            source="mypy",
            rule=m.group(5) or "",
        ))
    return results


_TSC_RE = re.compile(
    r"^(.+?)\((\d+),(\d+)\):\s+(error|warning)\s+(TS\d+):\s+(.+)$",
    re.MULTILINE,
)


def _parse_tsc(output: str) -> list[Diagnostic]:
    results: list[Diagnostic] = []
    for m in _TSC_RE.finditer(output):
        sev = DiagSeverity.ERROR if m.group(4) == "error" else DiagSeverity.WARNING
        results.append(Diagnostic(
            file=m.group(1),
            line=int(m.group(2)),
            column=int(m.group(3)),
            severity=sev,
            message=m.group(6).strip(),
            source="tsc",
            rule=m.group(5),
        ))
    return results


_GCC_RE = re.compile(
    r"^(.+?):(\d+):(\d+):\s+(error|warning|note):\s+(.+?)(?:\s+\[(.+?)\])?$",
    re.MULTILINE,
)


def _parse_gcc(output: str) -> list[Diagnostic]:
    results: list[Diagnostic] = []
    sev_map = {"error": DiagSeverity.ERROR, "warning": DiagSeverity.WARNING, "note": DiagSeverity.INFO}
    for m in _GCC_RE.finditer(output):
        results.append(Diagnostic(
            file=m.group(1),
            line=int(m.group(2)),
            column=int(m.group(3)),
            severity=sev_map.get(m.group(4), DiagSeverity.ERROR),
            message=m.group(5).strip(),
            source="gcc",
            rule=m.group(6) or "",
        ))
    return results


_GENERIC_RE = re.compile(
    r"^(.+?):(\d+)(?::(\d+))?:\s*(?:(error|warning|Error|Warning|ERROR|WARNING))?\s*:?\s*(.+)$",
    re.MULTILINE,
)


def _parse_generic(output: str) -> list[Diagnostic]:
    results: list[Diagnostic] = []
    for m in _GENERIC_RE.finditer(output):
        sev_str = (m.group(4) or "").lower()
        if sev_str in ("error",):
            sev = DiagSeverity.ERROR
        elif sev_str in ("warning",):
            sev = DiagSeverity.WARNING
        else:
            sev = DiagSeverity.ERROR
        results.append(Diagnostic(
            file=m.group(1),
            line=int(m.group(2)),
            column=int(m.group(3)) if m.group(3) else 0,
            severity=sev,
            message=m.group(5).strip(),
        ))
    return results
