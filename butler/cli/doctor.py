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

    print("\n[部署剖面]")
    try:
        from butler.ops.deploy_profile import (
            deploy_profile,
            effective_operating_profile,
            env_profile,
            format_owner_profile_lines,
            gateway_singleton_lock_held,
            profile_deviation_warnings,
        )

        op = effective_operating_profile()
        print(f"  推荐剖面: {op}")
        print(f"  BUTLER_DEPLOY_PROFILE: {deploy_profile() or '(未设)'}")
        print(f"  BUTLER_ENV_PROFILE: {env_profile() or '(未设)'}")
        print(f"  Gateway 锁: {'运行中' if gateway_singleton_lock_held() else '未持有'}")
        for line in format_owner_profile_lines(max_lines=6):
            print(f"  {line}")
        for w in profile_deviation_warnings():
            print(f"  ⚠ {w}")
        print("  指南: docs/guides/deploy-profiles-2026-06.md")
    except Exception as exc:
        print(f"  (不可用: {exc})")

    try:
        from butler.config_secrets import secrets_status_line

        print(f"  {secrets_status_line()}")
    except Exception as exc:
        print(f"  凭证文件: (不可用: {exc})")

    print("\n[观测演化 L7]")
    lf = os.environ.get("BUTLER_LANGFUSE_ENABLED", "0").strip()
    print(f"  BUTLER_LANGFUSE_ENABLED: {'✓' if lf in ('1', 'true', 'yes') else '— (opt-in)'}")
    print(f"  LANGFUSE_HOST: {os.environ.get('LANGFUSE_HOST', '(unset)')}")
    emb = os.environ.get("BUTLER_EMBEDDING_PROVIDER", "local")
    sem = os.environ.get("BUTLER_SEMANTIC_MEMORY", "0")
    print(f"  BUTLER_EMBEDDING_PROVIDER: {emb}")
    print(f"  BUTLER_SEMANTIC_MEMORY: {sem}")
    try:
        from butler.ops.embedding_diagnostics import format_embedding_doctor_lines

        for line in format_embedding_doctor_lines():
            print(line)
    except Exception as exc:
        print(f"  Embedding 档位: (不可用: {exc})")
    try:
        from butler.memory.semantic_config import semantic_memory_enabled
        from butler.ops.transcript_diagnostics import transcript_fts_drift

        drift = transcript_fts_drift()
        if semantic_memory_enabled():
            try:
                from butler.config import get_butler_home
                from butler.memory.semantic_index import SemanticMemoryIndex
                from butler.tenant import tenant_memory_dir

                db = tenant_memory_dir(butler_home, "default") / "memory_vectors.db"
                if db.is_file():
                    idx = SemanticMemoryIndex(db)
                    try:
                        print(f"  memory_vectors.db: {idx.count_rows()} 行")
                    finally:
                        idx.close()
            except Exception as exc:
                print(f"  memory_vectors.db: (不可用: {exc})")
        if drift.get("fts_enabled"):
            print(
                f"  transcript FTS: jsonl {drift.get('transcript_jsonl_lines', 0)} / "
                f"indexed {drift.get('transcript_fts_rows', 0)}"
            )
            if drift.get("transcript_fts_stale"):
                print("  ⚠ Transcript FTS 陈旧 — butler transcript index --rebuild")
    except Exception as exc:
        print(f"  索引统计: (不可用: {exc})")
    try:
        from butler.memory.vector_store import chroma_data_present_hint

        hint = chroma_data_present_hint(butler_home)
        if hint:
            print(f"  ⚠ {hint}")
    except Exception:
        pass
    try:
        from butler.ops.embedding_health import check_embedding_recall

        report = check_embedding_recall(min_recall=0.5)
        status = "✓" if report.ok(min_recall=0.5) else "⚠"
        print(f"  Embedding Recall@3: {status} {report.recall_at_3:.0%} — {report.message}")
        if report.degraded:
            print("  ⚠ Embedding 已降级为 HashingEmbedder（召回质量下降）")
    except Exception as exc:
        print(f"  Embedding Recall@3: ✗ ({exc})")

    try:
        from butler.ops.degradation_registry import (
            format_brief_line,
            format_diagnostic_lines,
            sync_compaction_acl_from_metrics,
            sync_embedding_degradation_from_health_check,
        )

        sync_embedding_degradation_from_health_check(min_recall=0.5)
        sync_compaction_acl_from_metrics()
        brief = format_brief_line()
        if brief:
            print(f"\n[运行降级] ⚠ {brief}")
        deg = format_diagnostic_lines()
        if deg and not brief:
            print("\n[运行降级]")
        for i, line in enumerate(deg):
            if brief and i == 0 and line == "运行降级:":
                continue
            print(f"  {line}" if line.startswith("  ") else line)
    except Exception as exc:
        print(f"\n[运行降级] (不可用: {exc})")

    print("\n[开发质量 O7/O9]")
    try:
        from butler.ops.eval_diagnostics import format_eval_quality_lines

        for line in format_eval_quality_lines():
            print(line)
    except Exception as exc:
        print(f"  (不可用: {exc})")

    try:
        from butler.core.transform_overrides import format_transform_diagnostic_lines

        for line in format_transform_diagnostic_lines():
            print(f"  {line}")
    except Exception as exc:
        print(f"  transform: (不可用: {exc})")

    print("\n[诚实边界 G1/G2]")
    try:
        from butler.ops.boundary_observability import format_boundary_observability_lines

        for line in format_boundary_observability_lines(verbose=True):
            print(line)
    except Exception as exc:
        print(f"  (不可用: {exc})")

    print("\n[有效模型]")
    print("  （CLI 无微信会话；不含 project.yaml 的当前项目覆盖，见 /诊断 或 /模型）")
    try:
        from butler.config import get_butler_settings
        from butler.model_resolve import format_model_diagnostic_lines

        for line in format_model_diagnostic_lines(
            project=None,
            settings=get_butler_settings(),
        ):
            print(line)
    except Exception as exc:
        print(f"  (不可用: {exc})")

    print("\n[执行面 Skill 路径]")
    try:
        from butler.ops.execution_surface_diagnostics import check_legacy_global_skills

        legacy = check_legacy_global_skills(butler_home)
        if legacy:
            for line in legacy:
                print(f"  ⚠ {line}")
        else:
            print("  遗留 ~/.butler/skills/: ✓（无或已迁移）")
    except Exception as exc:
        print(f"  (不可用: {exc})")

    print("\n[Terminal 沙箱]")
    try:
        from butler.ops.terminal_sandbox_diagnostics import (
            collect_terminal_sandbox_status,
            format_terminal_sandbox_diagnostic_lines,
        )

        st = collect_terminal_sandbox_status(workspace=workspace)
        for line in format_terminal_sandbox_diagnostic_lines(workspace=workspace):
            print(f"  {line}" if not line.startswith("Terminal") else line)
        if st.terminal_enabled and st.linux_host and not st.bwrap_available:
            print("  安装: sudo apt install bubblewrap   # Debian/Ubuntu")
    except Exception as exc:
        print(f"  (不可用: {exc})")

    print("\n[安全审计]")
    findings = run_security_audit(workspace=workspace)
    print(format_audit_report(findings))
    critical = sum(1 for f in findings if f.level == "critical")

    print("\n[项目 stack 依赖清单]")
    try:
        from butler.tools.path_safety import _default_project_workspace

        stack_ws = _default_project_workspace()
        if stack_ws is not None and (stack_ws / "stack.yaml").is_file():
            from butler.ops.stack_diagnostics import format_stack_diagnostic_lines

            for line in format_stack_diagnostic_lines(stack_ws):
                print(f"  {line}" if line.startswith("  ") else line)
        else:
            print("  （无 BUTLER_DEFAULT_PROJECT 或 stack.yaml）")
    except Exception as exc:
        print(f"  (不可用: {exc})")

    print("\n[G1-04 OT2 进化观测]")
    try:
        from butler.ops.boundary_observability import g1_04_observation_window_status

        w = g1_04_observation_window_status()
        print(
            f"  窗进度: {w.get('days_elapsed', '?')}/{w.get('window_days', '?')} 天 "
            f"（剩 {w.get('days_remaining', '?')}）"
        )
        print(f"  硬反馈: 窗内 {w.get('feedback_in_window', 0)} 条 "
              f"(B9 {w.get('feedback_evidence_b9_eval', 0)} / "
              f"生产 {w.get('feedback_evidence_production', 0)})")
        if w.get("feedback_triggers_in_window"):
            print(f"  triggers: {w.get('feedback_triggers_in_window')}")
        print(f"  ot2_closure_ready: {'✓' if w.get('ot2_closure_ready') else '—'}")
        if w.get("feedback_b9_eval_only") and w.get("feedback_in_window"):
            print("  提示: 当前仅 B9 测评证据，勿当 OT2 已证")
        if w.get("window_complete"):
            if w.get("ot2_closure_ready"):
                print("  结案: bash scripts/butler-g1-04-closure-apply.sh")
            elif w.get("pipeline_closure_ready"):
                print("  管线结案(可选): bash scripts/butler-g1-04-closure-apply.sh --pipeline-only")
            else:
                print("  结案: bash scripts/butler-g1-04-closure-check.sh")
    except Exception as exc:
        print(f"  (不可用: {exc})")

    return 1 if critical else 0
