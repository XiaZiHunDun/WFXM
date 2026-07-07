"""``butler doctor`` diagnostic command."""

from __future__ import annotations

import argparse

from butler.cli.doctor_sections import (
    discover_doctor_workspace,
    print_boundary_section,
    print_config_section,
    print_core_dependencies,
    print_deploy_profile_section,
    print_degradation_section,
    print_dev_quality_section,
    print_effective_models_section,
    print_execution_surface_section,
    print_g1_04_section,
    print_observability_l7,
    print_l7_policy_section,
    print_optional_dependencies,
    print_runtime_dirs,
    print_secrets_status,
    print_stack_section,
    print_terminal_sandbox_section,
    resolve_butler_home,
)


def cmd_doctor(_ns: argparse.Namespace) -> int:
    from butler.ops.security_audit import format_audit_report, run_security_audit

    butler_home = resolve_butler_home()
    workspace = discover_doctor_workspace(butler_home)

    print("=== Butler Doctor ===\n")

    print_runtime_dirs(butler_home)
    print_core_dependencies()
    print_optional_dependencies()
    print_config_section()
    print_deploy_profile_section()
    print_secrets_status()
    print_observability_l7(butler_home)
    print_l7_policy_section(butler_home)
    print_degradation_section()
    print_dev_quality_section()
    print_boundary_section()
    print_effective_models_section()
    print_execution_surface_section(butler_home)
    print_terminal_sandbox_section(workspace)

    print("\n[安全审计]")
    findings = run_security_audit(workspace=workspace)
    print(format_audit_report(findings))
    critical = sum(1 for f in findings if f.level == "critical")

    print_stack_section()
    print_g1_04_section()

    return 1 if critical else 0
