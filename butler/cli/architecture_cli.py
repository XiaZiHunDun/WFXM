"""CLI: ``butler architecture ...`` — 架构分析工具."""

from __future__ import annotations

import argparse
import json
from typing import Any, cast


def register_architecture_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the architecture subcommand parser."""
    arch = sub.add_parser(
        "architecture",
        help="架构分析：循环依赖检测与层边界验证",
        description="分析项目架构，检测循环依赖和层边界违规",
    )
    arch_sub = arch.add_subparsers(dest="arch_cmd", required=True)

    # Dependencies subcommand
    deps_p = arch_sub.add_parser(
        "dependencies",
        help="查看依赖关系",
        description="生成完整的依赖分析报告",
    )
    deps_p.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    deps_p.add_argument("--cycles-only", action="store_true", help="只显示循环依赖")
    deps_p.add_argument("--violations-only", action="store_true", help="只显示层边界违规")
    deps_p.set_defaults(func=_cmd_architecture_dependencies)

    # Layers subcommand
    layers_p = arch_sub.add_parser(
        "layers",
        help="验证层边界",
        description="验证 ENG-15 层边界约束",
    )
    layers_p.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    layers_p.set_defaults(func=_cmd_architecture_layers)

    # Graph subcommand
    graph_p = arch_sub.add_parser(
        "graph",
        help="生成依赖图",
        description="生成 Graphviz 格式的依赖关系图",
    )
    graph_p.add_argument("--output", type=str, default="dependencies.dot", help="输出文件路径")
    graph_p.set_defaults(func=_cmd_architecture_graph)


def _cmd_architecture_dependencies(ns: argparse.Namespace) -> int:
    """Display dependency analysis report."""
    from butler.core.circular_dependency_detector import (
        generate_dependency_report,
        print_dependency_report,
    )

    report = generate_dependency_report()

    if ns.json:
        output = {
            "total_modules": report.total_modules,
            "total_dependencies": report.total_dependencies,
            "circular_dependencies": [c.cycle for c in report.circular_dependencies],
            "layer_violations": [
                {
                    "source_module": v.source_module,
                    "source_layer": v.source_layer,
                    "target_module": v.target_module,
                    "target_layer": v.target_layer,
                }
                for v in report.layer_violations
            ],
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0

    if ns.cycles_only:
        print("循环依赖检测:")
        print("-" * 40)
        if report.circular_dependencies:
            for i, cycle in enumerate(report.circular_dependencies, 1):
                print(f"{i}. {' -> '.join(cycle.cycle)}")
        else:
            print("None detected ✓")
        return 0

    if ns.violations_only:
        print("层边界违规检测:")
        print("-" * 40)
        if report.layer_violations:
            for i, violation in enumerate(report.layer_violations, 1):
                print(
                    f"{i}. {violation.source_module} (layer {violation.source_layer}) "
                    f"depends on {violation.target_module} (layer {violation.target_layer})"
                )
        else:
            print("None detected ✓")
        return 0

    print_dependency_report(report)
    return 0


def _cmd_architecture_layers(ns: argparse.Namespace) -> int:
    """Display layer boundary validation results."""
    from butler.core.circular_dependency_detector import (
        LAYER_MAP,
        validate_layer_boundaries,
    )

    violations = validate_layer_boundaries()

    if ns.json:
        output = {
            "layers": LAYER_MAP,
            "violations": [
                {
                    "source_module": v.source_module,
                    "source_layer": v.source_layer,
                    "target_module": v.target_module,
                    "target_layer": v.target_layer,
                }
                for v in violations
            ],
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0

    print("=" * 60)
    print("ENG-15 层边界验证")
    print("=" * 60)
    print()
    print("层定义:")
    print("-" * 40)
    for layer_name, layer_number in sorted(LAYER_MAP.items(), key=lambda x: x[1]):
        print(f"  Layer {layer_number}: {layer_name}")
    print()
    print("层边界违规:")
    print("-" * 40)
    if violations:
        for i, violation in enumerate(violations, 1):
            print(
                f"{i}. {violation.source_module} (layer {violation.source_layer}) "
                f"depends on {violation.target_module} (layer {violation.target_layer})"
            )
    else:
        print("None detected ✓")
    print()
    print("规则: 低层（数字大）不能依赖高层（数字小）")

    return 0


def _cmd_architecture_graph(ns: argparse.Namespace) -> int:
    """Generate Graphviz dependency graph."""
    from butler.core.circular_dependency_detector import generate_dependency_report

    report = generate_dependency_report()

    dot_content = """digraph ButlerDependencies {
    rankdir=LR;
    node [shape=box, style=filled, color="#e8f4fd", fontname="Arial"];
    edge [color="#999999", arrowhead="vee"];
    
    // Layer clusters
    subgraph cluster_utilities {
        label = "Layer 1: utilities";
        color = "#4CAF50";
    """

    layers = {
        1: "utilities",
        2: "configuration",
        3: "contracts",
        4: "core",
        5: "memory",
        6: "tools",
        7: "skills",
        8: "orchestrator",
        9: "gateway",
        10: "cli",
    }

    for layer_num, layer_name in layers.items():
        modules = [m for m in report.dependency_graph.keys() if m.startswith(f"butler.{layer_name}")]
        if modules:
            dot_content += f"\n    subgraph cluster_{layer_name} {{\n        label = \"Layer {layer_num}: {layer_name}\";\n"
            for mod in modules[:5]:  # Limit to 5 per layer for readability
                safe_name = mod.replace(".", "_")
                dot_content += f"        {safe_name} [label=\"{mod}\"];\n"
            dot_content += "    }\n"

    # Add dependencies
    dot_content += "\n    // Dependencies\n"
    for source, targets in report.dependency_graph.items():
        safe_source = source.replace(".", "_")
        for target in targets:
            safe_target = target.replace(".", "_")
            dot_content += f"    {safe_source} -> {safe_target};\n"

    dot_content += "}\n"

    with open(ns.output, "w", encoding="utf-8") as f:
        f.write(dot_content)

    print(f"依赖图已生成到: {ns.output}")
    print("")
    print("使用 Graphviz 生成可视化:")
    print(f"  dot -Tsvg {ns.output} -o dependencies.svg")
    print(f"  dot -Tpng {ns.output} -o dependencies.png")

    return 0