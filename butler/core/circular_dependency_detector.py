"""Circular dependency detector for the butler codebase.

Inspired by ArchUnit and dependency-cruiser, this module provides tools to:
1. Detect circular dependencies between modules
2. Validate layer boundaries (ENG-15)
3. Generate dependency reports

Usage:
    from butler.core.circular_dependency_detector import (
        detect_circular_dependencies,
        validate_layer_boundaries,
        generate_dependency_report,
    )

    # Detect circular dependencies
    cycles = detect_circular_dependencies("butler.core")

    # Validate layer boundaries
    violations = validate_layer_boundaries()

    # Generate report
    report = generate_dependency_report()
"""

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set

from butler.utilities.repo_paths import REPO_ROOT


@dataclass
class Dependency:
    """Represents a dependency between modules."""

    source: str
    target: str
    line: int
    column: int
    import_type: str  # 'import', 'from', 'from_as'


@dataclass
class CircularDependency:
    """Represents a circular dependency cycle."""

    cycle: List[str]
    dependencies: List[Dependency]


@dataclass
class LayerViolation:
    """Represents a layer boundary violation."""

    source_module: str
    source_layer: str
    target_module: str
    target_layer: str
    dependency: Dependency


@dataclass
class DependencyReport:
    """Comprehensive dependency analysis report."""

    total_modules: int
    total_dependencies: int
    circular_dependencies: List[CircularDependency]
    layer_violations: List[LayerViolation]
    dependency_graph: Dict[str, Set[str]]


# Layer hierarchy (ENG-15) - lower layers can depend on higher layers
LAYER_MAP: Dict[str, int] = {
    "butler.utilities": 1,
    "butler.configuration": 2,
    "butler.contracts": 3,
    "butler.core": 4,
    "butler.memory": 5,
    "butler.tools": 6,
    "butler.skills": 7,
    "butler.orchestrator": 8,
    "butler.gateway": 9,
    "butler.cli": 10,
}


def _extract_imports(file_path: Path) -> List[Dependency]:
    """Extract imports from a Python file."""
    dependencies: List[Dependency] = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        tree = ast.parse(content)
    except (SyntaxError, UnicodeDecodeError):
        return dependencies

    module_name = _path_to_module_name(file_path)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = alias.name
                if target.startswith("butler."):
                    dependencies.append(
                        Dependency(
                            source=module_name,
                            target=target.split(".")[0],
                            line=node.lineno,
                            column=node.col_offset,
                            import_type="import",
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("butler."):
                node.module.split(".")[0]
                for alias in node.names:
                    full_target = f"{node.module}.{alias.name}"
                    dependencies.append(
                        Dependency(
                            source=module_name,
                            target=full_target,
                            line=node.lineno,
                            column=node.col_offset,
                            import_type="from_as" if alias.asname else "from",
                        )
                    )

    return dependencies


def _path_to_module_name(file_path: Path) -> str:
    """Convert a file path to a module name."""
    rel_path = file_path.relative_to(REPO_ROOT)
    parts = list(rel_path.parent.parts)
    if rel_path.stem != "__init__":
        parts.append(rel_path.stem)
    return ".".join(parts)


def _build_dependency_graph(modules: List[str]) -> Dict[str, Set[str]]:
    """Build a dependency graph from module imports."""
    graph: Dict[str, Set[str]] = defaultdict(set)
    visited: Set[str] = set()

    def find_modules(path: Path, prefix: str = "") -> None:
        if path in visited:
            return
        visited.add(path)

        for item in path.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                find_modules(item, prefix + item.name + ".")
            elif item.is_file() and item.name.endswith(".py"):
                module_name = prefix + item.stem
                if module_name.endswith(".__init__"):
                    module_name = module_name[:-9]
                modules.append(module_name)

    find_modules(REPO_ROOT)

    for module_name in modules:
        parts = module_name.split(".")
        current = REPO_ROOT
        for part in parts:
            current = current / part
        file_path = current.with_suffix(".py")
        if not file_path.exists():
            file_path = current / "__init__.py"
            if not file_path.exists():
                continue

        for dep in _extract_imports(file_path):
            # Normalize to top-level butler package
            target_parts = dep.target.split(".")
            if len(target_parts) >= 2 and target_parts[0] == "butler":
                top_level = ".".join(target_parts[:2])
                if top_level != module_name.split(".")[:2]:
                    graph[".".join(module_name.split(".")[:2])].add(top_level)

    return dict(graph)


def _detect_cycles(graph: Dict[str, Set[str]]) -> List[CircularDependency]:
    """Detect cycles in the dependency graph using DFS."""
    cycles: List[CircularDependency] = []
    visited: Set[str] = set()
    rec_stack: Set[str] = set()
    path: List[str] = []

    def dfs(node: str) -> None:
        if node not in visited:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    if cycle not in [c.cycle for c in cycles]:
                        cycles.append(CircularDependency(cycle=cycle, dependencies=[]))

            path.pop()
            rec_stack.remove(node)

    for node in graph:
        dfs(node)

    return cycles


def detect_circular_dependencies(package: str = "butler") -> List[CircularDependency]:
    """Detect circular dependencies in a package.

    Args:
        package: The package name to analyze (default: 'butler')

    Returns:
        List of CircularDependency objects representing detected cycles
    """
    modules: List[str] = []
    graph = _build_dependency_graph(modules)
    return _detect_cycles(graph)


def validate_layer_boundaries() -> List[LayerViolation]:
    """Validate layer boundaries according to ENG-15.

    Lower layers (higher numbers) should not depend on higher layers (lower numbers).

    Returns:
        List of LayerViolation objects representing boundary violations
    """
    violations: List[LayerViolation] = []
    modules: List[str] = []
    graph = _build_dependency_graph(modules)

    for source, targets in graph.items():
        source_layer = None
        for prefix, layer in LAYER_MAP.items():
            if source.startswith(prefix):
                source_layer = layer
                break

        if source_layer is None:
            continue

        for target in targets:
            target_layer = None
            for prefix, layer in LAYER_MAP.items():
                if target.startswith(prefix):
                    target_layer = layer
                    break

            if target_layer is None:
                continue

            # Lower layers (higher numbers) cannot depend on higher layers (lower numbers)
            if source_layer > target_layer:
                violations.append(
                    LayerViolation(
                        source_module=source,
                        source_layer=source_layer,
                        target_module=target,
                        target_layer=target_layer,
                        dependency=Dependency(
                            source=source,
                            target=target,
                            line=0,
                            column=0,
                            import_type="layer_violation",
                        ),
                    )
                )

    return violations


def generate_dependency_report() -> DependencyReport:
    """Generate a comprehensive dependency analysis report.

    Returns:
        DependencyReport with total counts, circular dependencies, and layer violations
    """
    modules: List[str] = []
    graph = _build_dependency_graph(modules)

    total_dependencies = sum(len(targets) for targets in graph.values())
    circular_deps = _detect_cycles(graph)
    layer_violations = validate_layer_boundaries()

    return DependencyReport(
        total_modules=len(modules),
        total_dependencies=total_dependencies,
        circular_dependencies=circular_deps,
        layer_violations=layer_violations,
        dependency_graph=graph,
    )


def print_dependency_report(report: DependencyReport) -> None:
    """Print a human-readable dependency report."""
    print("=" * 70)
    print("Butler Dependency Analysis Report")
    print("=" * 70)
    print(f"Total modules: {report.total_modules}")
    print(f"Total dependencies: {report.total_dependencies}")
    print()

    print("Circular Dependencies:")
    print("-" * 40)
    if report.circular_dependencies:
        for i, cycle in enumerate(report.circular_dependencies, 1):
            print(f"{i}. {' -> '.join(cycle.cycle)}")
    else:
        print("None detected ✓")
    print()

    print("Layer Boundary Violations:")
    print("-" * 40)
    if report.layer_violations:
        for i, violation in enumerate(report.layer_violations, 1):
            print(
                f"{i}. {violation.source_module} (layer {violation.source_layer}) "
                f"depends on {violation.target_module} (layer {violation.target_layer})"
            )
    else:
        print("None detected ✓")
    print()

    print("Dependency Graph Summary:")
    print("-" * 40)
    for module, targets in sorted(report.dependency_graph.items()):
        if targets:
            print(f"{module}:")
            for target in sorted(targets):
                print(f"  -> {target}")


__all__ = [
    "Dependency",
    "CircularDependency",
    "LayerViolation",
    "DependencyReport",
    "detect_circular_dependencies",
    "validate_layer_boundaries",
    "generate_dependency_report",
    "print_dependency_report",
]
