"""``butler doctor`` diagnostic command."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def cmd_doctor(_ns: argparse.Namespace) -> int:
    from butler.ops.security_audit import format_audit_report, run_security_audit

    workspace: Path | None = None
    try:
        from butler.config import BUTLER_RUNTIME_DIRS, get_butler_home

        butler_home = get_butler_home()
        projects_dir = butler_home / "projects"
        if projects_dir.is_dir():
            for child in sorted(projects_dir.iterdir()):
                if (child / "AGENTS.md").is_file():
                    workspace = child
                    break
    except Exception:
        from butler.config import BUTLER_RUNTIME_DIRS  # noqa: F811

        butler_home = Path(os.environ.get("BUTLER_HOME", "~/.butler")).expanduser()

    print("=== Butler Doctor ===\n")

    print("[数据目录]")
    for d in BUTLER_RUNTIME_DIRS:
        p = butler_home / d
        status = "✓" if p.is_dir() else "✗ (missing)"
        print(f"  {butler_home / d}: {status}")
    print()

    print("[核心依赖]")
    core_deps = {
        "dotenv": "python-dotenv",
        "yaml": "PyYAML",
        "httpx": "httpx",
        "openai": "openai",
    }
    for mod, pkg in core_deps.items():
        try:
            __import__(mod)
            print(f"  {pkg}: ✓")
        except ImportError:
            print(f"  {pkg}: ✗ (pip install {pkg})")

    print("\n[可选依赖]")
    optional = {
        "chromadb": ("chromadb (vectors extra)", 'pip install -e ".[vectors]"'),
        "fastembed": ("fastembed (embeddings extra)", 'pip install -e ".[embeddings]"'),
        "aiohttp": ("aiohttp (wechat extra)", 'pip install -e ".[wechat]"'),
        "markitdown": ("markitdown (documents extra)", 'pip install -e ".[documents]"'),
        "croniter": ("croniter (core dependency)", 'pip install -e ".[dev]"'),
    }
    missing_optional: list[str] = []
    for mod, (desc, install_hint) in optional.items():
        try:
            __import__(mod)
            print(f"  {desc}: ✓")
        except ImportError:
            print(f"  {desc}: — (not installed)")
            missing_optional.append(f"{desc} -> {install_hint}")
    if missing_optional:
        print("  可按需安装：")
        for item in missing_optional:
            print(f"    - {item}")

    print("\n[配置]")
    env_path = Path.cwd() / ".env"
    if env_path.is_file():
        print(f"  .env: ✓ ({env_path})")
    else:
        print("  .env: ✗ (copy .env.example → .env)")

    api_key = os.environ.get("MINIMAX_API_KEY", "")
    print(f"  MINIMAX_API_KEY: {'✓ (set)' if api_key else '✗ (unset)'}")

    print("\n[安全审计]")
    findings = run_security_audit(workspace=workspace)
    print(format_audit_report(findings))
    critical = sum(1 for f in findings if f.level == "critical")
    return 1 if critical else 0
