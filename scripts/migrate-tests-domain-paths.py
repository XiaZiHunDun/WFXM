#!/usr/bin/env python3
"""One-shot path updater after tests/ domain moves. Safe to re-run (idempotent)."""
from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[1]

# old path substring -> new (only under tests/)
REPLACEMENTS: list[tuple[str, str]] = [
    ("tests/test_gateway_", "tests/gateway/test_gateway_"),
    ("tests/test_wechat_", "tests/gateway/test_wechat_"),
    ("tests/test_dev_commands.py", "tests/gateway/test_dev_commands.py"),
    ("tests/test_project_commands.py", "tests/gateway/test_project_commands.py"),
    ("tests/test_registry_commands.py", "tests/gateway/test_registry_commands.py"),
    ("tests/test_export_commands.py", "tests/gateway/test_export_commands.py"),
    ("tests/test_gateway_help_commands.py", "tests/gateway/test_gateway_help_commands.py"),
    ("tests/test_owner_profile_gateway.py", "tests/gateway/test_owner_profile_gateway.py"),
    ("tests/test_message_queue.py", "tests/gateway/test_message_queue.py"),
    ("tests/test_install_pending.py", "tests/gateway/test_install_pending.py"),
    ("tests/test_completion_notify_p2.py", "tests/gateway/test_completion_notify_p2.py"),
    ("tests/test_completion_notify.py", "tests/gateway/test_completion_notify.py"),
    ("tests/test_eval_", "tests/ops/test_eval_"),
    ("tests/test_g1_04_prod_evidence.py", "tests/ops/test_g1_04_prod_evidence.py"),
    ("tests/test_health_report.py", "tests/ops/test_health_report.py"),
    ("tests/test_runtime_metrics.py", "tests/ops/test_runtime_metrics.py"),
    ("tests/test_ops_snapshot.py", "tests/ops/test_ops_snapshot.py"),
    ("tests/test_boundary_observability.py", "tests/ops/test_boundary_observability.py"),
    ("tests/test_langfuse_tracer.py", "tests/ops/test_langfuse_tracer.py"),
    ("tests/test_phase1_observability.py", "tests/ops/test_phase1_observability.py"),
    ("tests/test_phase2_observability.py", "tests/ops/test_phase2_observability.py"),
    ("tests/test_failure_tracker.py", "tests/ops/test_failure_tracker.py"),
    ("tests/test_wechat_dataset.py", "tests/ops/test_wechat_dataset.py"),
    ("tests/test_wechat_corpus_eval.py", "tests/ops/test_wechat_corpus_eval.py"),
    ("tests/test_dev_engine_", "tests/dev_engine/test_dev_engine_"),
    ("tests/test_verify_", "tests/dev_engine/test_verify_"),
    ("tests/test_read_state.py", "tests/dev_engine/test_read_state.py"),
    ("tests/test_dev_eval.py", "tests/dev_engine/test_dev_eval.py"),
    ("tests/test_memory_eval.py", "tests/memory/test_memory_eval.py"),
]

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "htmlcov", ".mypy_cache", ".pytest_cache"}

TEXT_SUFFIXES = {
    ".py", ".md", ".sh", ".yml", ".yaml", ".toml", ".txt", ".rst",
}


def should_scan(path: pathlib.Path) -> bool:
    if any(part in SKIP_DIRS for part in path.parts):
        return False
    if path.suffix not in TEXT_SUFFIXES:
        return False
    if path.name == "migrate-tests-domain-paths.py":
        return False
    return True


def apply_replacements(text: str) -> str:
    # Prevent double-prefix: tests/gateway/gateway/...
    for old, new in REPLACEMENTS:
        if old.startswith("tests/test_") and new.count("/") >= 2:
            double = new.replace("tests/", "tests/gateway/", 1) if "gateway" in new else None
            if double and double in text:
                continue
        text = text.replace(old, new)
    # Fix accidental double gateway prefix from chained replacements
    text = re.sub(r"tests/gateway/gateway/", "tests/gateway/", text)
    text = re.sub(r"tests/ops/ops/", "tests/ops/", text)
    text = re.sub(r"tests/dev_engine/dev_engine/", "tests/dev_engine/", text)
    return text


def main() -> None:
    changed: list[str] = []
    for path in REPO.rglob("*"):
        if not path.is_file() or not should_scan(path):
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        updated = apply_replacements(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed.append(str(path.relative_to(REPO)))
    print(f"updated {len(changed)} files")
    for name in sorted(changed)[:40]:
        print(f"  {name}")
    if len(changed) > 40:
        print(f"  ... and {len(changed) - 40} more")


if __name__ == "__main__":
    main()
