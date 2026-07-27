"""Dependency visualization for the butler codebase.

Analyzes module dependencies and generates a Graphviz DOT file
for visualization with tools like Graphviz (dot, neato, etc.).

Usage:
    python butler/dev_engine/dep_visualizer.py
    # Output: butler_deps.dot

    # Generate SVG:
    dot -Tsvg butler_deps.dot -o butler_deps.svg
"""

from __future__ import annotations

import ast
import os
import sys
from collections import defaultdict
from pathlib import Path


# Directories to analyze
BUTLER_DIR = Path(__file__).parent.parent.parent / "butler"

# Layer definitions for grouping
LAYER_MAP = {
    "gateway": "L1-Gateway",
    "cli": "L1-Gateway",
    "orchestrator": "L2-Orchestration",
    "workflows": "L2-Orchestration",
    "delegate": "L2-Orchestration",
    "core": "L3-Core",
    "tools": "L4-Tools",
    "mcp": "L4-Tools",
    "skills": "L4-Tools",
    "dev_engine": "L4-Tools",
    "memory": "L5-Memory",
    "transport": "L6-Transport",
    "permissions": "L7-Permissions",
    "human_gate": "L7-Permissions",
    "resilience": "L8-Resilience",
    "ops": "L9-Ops",
    "eval_integration": "L9-Ops",
    "contracts": "Cross-Cutting",
    "configuration": "Cross-Cutting",
    "defaults": "Cross-Cutting",
    "utilities": "Cross-Cutting",
    "registry": "Cross-Cutting",
    "runtime": "Cross-Cutting",
    "project": "Cross-Cutting",
}

# Layer colors for visualization
LAYER_COLORS = {
    "L1-Gateway": "#a8d8ea",
    "L2-Orchestration": "#aa96da",
    "L3-Core": "#fcbad3",
    "L4-Tools": "#ffffd2",
    "L5-Memory": "#a8e6cf",
    "L6-Transport": "#ffd3b6",
    "L7-Permissions": "#ffaaa5",
    "L8-Resilience": "#dcedc1",
    "L9-Ops": "#ffdac1",
    "Cross-Cutting": "#e0bbff",
}


def get_layer(module_path: str) -> str:
    """Determine the architectural layer for a module path."""
    parts = module_path.split(".")
    if not parts:
        return "Unknown"

    top_level = parts[0]
    sub_module = parts[1] if len(parts) > 1 else ""

    # Check sub-module first
    if sub_module in LAYER_MAP:
        return LAYER_MAP[sub_module]

    # Check top-level
    if top_level in LAYER_MAP:
        return LAYER_MAP[top_level]

    return "Other"


def find_python_files(base_dir: Path) -> list[Path]:
    """Find all Python files in the butler directory."""
    files = []
    for root, dirs, filenames in os.walk(base_dir):
        # Skip hidden directories and __pycache__
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]

        for filename in filenames:
            if filename.endswith(".py"):
                files.append(Path(root) / filename)

    return files


def analyze_imports(file_path: Path) -> list[str]:
    """Analyze imports in a Python file using AST."""
    imports = []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("butler."):
                        imports.append(alias.name)

            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("butler."):
                    imports.append(node.module)

    except SyntaxError:
        pass
    except Exception as e:
        print(f"Error analyzing {file_path}: {e}", file=sys.stderr)

    return imports


def generate_module_name(file_path: Path, base_dir: Path) -> str:
    """Generate a dotted module name from a file path."""
    rel_path = file_path.relative_to(base_dir)
    parts = list(rel_path.parts)

    # Remove __init__.py if present
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        # Remove .py extension
        parts[-1] = parts[-1][:-3]

    return ".".join(parts)


def build_dependency_graph(base_dir: Path) -> dict[str, set[str]]:
    """Build a dependency graph for the butler codebase."""
    graph: dict[str, set[str]] = defaultdict(set)
    python_files = find_python_files(base_dir)

    print(f"Found {len(python_files)} Python files to analyze...")

    for i, file_path in enumerate(python_files):
        if i % 100 == 0:
            print(f"  Processing {i}/{len(python_files)}...")

        module_name = generate_module_name(file_path, base_dir)
        if not module_name:
            continue

        imports = analyze_imports(file_path)
        for imp in imports:
            # Skip self-references
            if imp != module_name and not module_name.startswith(imp):
                graph[module_name].add(imp)

    return graph


def detect_circular_dependencies(graph: dict[str, set[str]]) -> list[list[str]]:
    """Detect circular dependencies using DFS."""
    cycles = []
    visited = set()
    rec_stack = set()

    def dfs(node: str, path: list[str]) -> None:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in graph.get(node, set()):
            if neighbor not in visited:
                dfs(neighbor, path)
            elif neighbor in rec_stack:
                # Found a cycle
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                cycles.append(cycle)

        path.pop()
        rec_stack.remove(node)

    for node in graph:
        if node not in visited:
            dfs(node, [])

    return cycles


def generate_dot_file(
    graph: dict[str, set[str]],
    cycles: list[list[str]],
    output_file: str = "butler_deps.dot",
) -> None:
    """Generate a Graphviz DOT file for the dependency graph."""
    cycle_set = set()
    for cycle in cycles:
        for i in range(len(cycle) - 1):
            cycle_set.add((cycle[i], cycle[i + 1]))

    with open(output_file, "w", encoding="utf-8") as f:
        f.write('digraph ButlerDeps {\n')
        f.write('  rankdir=LR;\n')
        f.write('  node [shape=box, style=filled];\n')
        f.write('  graph [fontsize=12, label="Butler Module Dependencies"];\n\n')

        # Group by layer
        layers = defaultdict(list)
        for module in graph:
            layer = get_layer(module)
            layers[layer].append(module)

        for layer, modules in sorted(layers.items()):
            color = LAYER_COLORS.get(layer, "#cccccc")
            f.write(f'  subgraph cluster_{layer.replace("-", "_")} {{\n')
            f.write(f'    label="{layer}";\n')
            f.write(f'    style=filled;\n')
            f.write(f'    fillcolor="{color}";\n')
            f.write(f'    nodesep=0.3;\n')
            f.write(f'    ranksep=0.5;\n')

            for module in sorted(modules):
                # Shorten label for readability
                short_label = module.split(".")[-1]
                f.write(f'    "{module}" [label="{short_label}"];\n')

            f.write('  }\n\n')

        # Draw edges
        for source, targets in sorted(graph.items()):
            for target in sorted(targets):
                is_cycle = (source, target) in cycle_set
                color = "red" if is_cycle else "gray60"
                style = "bold" if is_cycle else "solid"

                f.write(f'  "{source}" -> "{target}" [color="{color}", style="{style}"];\n')

        f.write('}\n')

    print(f"DOT file written to: {output_file}")
    print(f"\nTo generate SVG, run:")
    print(f"  dot -Tsvg {output_file} -o {output_file.replace('.dot', '.svg')}")


def generate_summary_report(
    graph: dict[str, set[str]],
    cycles: list[list[str]],
    output_file: str = "butler_deps_report.txt",
) -> None:
    """Generate a text summary report of the dependency analysis."""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("Butler Dependency Analysis Report\n")
        f.write("=" * 60 + "\n\n")

        # Module counts by layer
        layers = defaultdict(int)
        for module in graph:
            layer = get_layer(module)
            layers[layer] += 1

        f.write("Modules by Architectural Layer:\n")
        f.write("-" * 40 + "\n")
        for layer, count in sorted(layers.items()):
            f.write(f"  {layer}: {count} modules\n")

        f.write("\n")

        # Dependency statistics
        total_deps = sum(len(deps) for deps in graph.values())
        avg_deps = total_deps / len(graph) if graph else 0

        f.write("Dependency Statistics:\n")
        f.write("-" * 40 + "\n")
        f.write(f"  Total modules: {len(graph)}\n")
        f.write(f"  Total dependencies: {total_deps}\n")
        f.write(f"  Average deps per module: {avg_deps:.1f}\n")

        # Most connected modules
        f.write("\nMost Connected Modules (Top 20):\n")
        f.write("-" * 40 + "\n")
        sorted_modules = sorted(graph.items(), key=lambda x: len(x[1]), reverse=True)
        for module, deps in sorted_modules[:20]:
            f.write(f"  {module}: {len(deps)} dependencies\n")

        # Circular dependencies
        f.write("\nCircular Dependencies:\n")
        f.write("-" * 40 + "\n")
        if cycles:
            f.write(f"  Found {len(cycles)} circular dependency chain(s):\n\n")
            for i, cycle in enumerate(cycles[:10]):  # Show first 10
                f.write(f"  Cycle {i + 1}: {' -> '.join(cycle)}\n")
        else:
            f.write("  No circular dependencies detected.\n")

    print(f"Report written to: {output_file}")


def main() -> None:
    """Main entry point for dependency visualization."""
    print("Butler Dependency Visualizer")
    print("=" * 60)
    print(f"Analyzing: {BUTLER_DIR}")
    print()

    # Validate directory exists
    if not BUTLER_DIR.exists():
        print(f"Error: Butler directory not found: {BUTLER_DIR}")
        sys.exit(1)

    # Build dependency graph
    print("Building dependency graph...")
    graph = build_dependency_graph(BUTLER_DIR)
    print(f"Analyzed {len(graph)} modules\n")

    # Detect circular dependencies
    print("Detecting circular dependencies...")
    cycles = detect_circular_dependencies(graph)
    print(f"Found {len(cycles)} circular dependency chain(s)\n")

    # Generate outputs
    print("Generating visualization files...")
    generate_dot_file(graph, cycles)
    generate_summary_report(graph, cycles)

    # Print summary
    print("\n" + "=" * 60)
    print("Analysis Complete!")
    print("=" * 60)
    print(f"  Modules analyzed: {len(graph)}")
    print(f"  Dependencies found: {sum(len(d) for d in graph.values())}")
    print(f"  Circular dependencies: {len(cycles)}")


if __name__ == "__main__":
    main()
