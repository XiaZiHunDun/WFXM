#!/usr/bin/env python3
"""P5 wave2b: targeted mypy strict fixes for remaining core/*_ops.py."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "butler/core"


def patch(path: Path, old: str, new: str) -> None:
    src = path.read_text(encoding="utf-8")
    if old not in src:
        raise SystemExit(f"missing patch in {path}: {old[:60]!r}")
    path.write_text(src.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    # agent_loop_ops
    p = CORE / "agent_loop_ops.py"
    patch(
        p,
        "            return synthetic_result(decision)\n    except Exception:",
        "            return str(synthetic_result(decision))\n    except Exception:",
    )
    patch(
        p,
        "        return synthetic_result(decision)\n    return None",
        "        return str(synthetic_result(decision))\n    return None",
    )
    patch(
        p,
        "        return filter_fallback_chain(chain)",
        "        out = filter_fallback_chain(chain)\n        return out if isinstance(out, list) else chain",
    )
    patch(p, "    def _run():\n\n        return run_stop_hooks(", "    def _run() -> Any:\n\n        return run_stop_hooks(")

    # agents_md_sections_ops
    p = CORE / "agents_md_sections_ops.py"
    src = p.read_text(encoding="utf-8")
    if "cast" not in src:
        src = src.replace(
            "from pathlib import Path\n",
            "from pathlib import Path\nfrom typing import cast\n",
        )
    src = src.replace(
        "    return resolve_active_project_workspace_safe()",
        "    return cast(Path | None, resolve_active_project_workspace_safe())",
    )
    p.write_text(src, encoding="utf-8")

    # batch_sequence_guard_ops
    patch(
        CORE / "batch_sequence_guard_ops.py",
        "            return tc.args_dict()",
        "            raw = tc.args_dict()\n            return dict(raw) if isinstance(raw, dict) else {}",
    )

    # context_pipeline_ops
    p = CORE / "context_pipeline_ops.py"
    patch(
        p,
        "        return get_audit_session_key(fallback=fallback)",
        "        return str(get_audit_session_key(fallback=fallback) or fallback)",
    )
    for fn in (
        "apply_unified_tool_masking",
        "compress_inline_tool_messages",
        "apply_model_transforms",
    ):
        patch(
            p,
            f"        return {fn}(list(messages))",
            f"        out = {fn}(list(messages))\n        return out if isinstance(out, list) else list(messages)",
        )
    patch(
        p,
        "        return out\n    except Exception as exc:",
        "        return out if isinstance(out, list) else list(messages)\n    except Exception as exc:",
    )

    # llm_retry_invoke_ops
    patch(
        CORE / "llm_retry_invoke_ops.py",
        "    on_tool_call_ready: Callable[[int, str, str, dict], None] | None,",
        "    on_tool_call_ready: Callable[[int, str, str, dict[str, Any]], None] | None,",
    )

    # message_context_adapter_ops
    patch(
        CORE / "message_context_adapter_ops.py",
        '        role: ApiRole = role_raw  # type: ignore[assignment]\n',
        "        role: ApiRole = role_raw\n",
    )

    # mode_classifier_ops
    patch(
        CORE / "mode_classifier_ops.py",
        "from typing import Literal",
        "from typing import Any, Literal",
    )

    # review_context_adapter_ops
    patch(
        CORE / "review_context_adapter_ops.py",
        "        severity=sev,  # type: ignore[arg-type]\n",
        "        severity=sev,\n",
    )

    # parallel_tools_ops
    p = CORE / "parallel_tools_ops.py"
    src = p.read_text(encoding="utf-8")
    src = src.replace("def parse_tool_args_safe(tc: Any) -> dict:", "def parse_tool_args_safe(tc: Any) -> dict[str, Any]:")
    src = src.replace("    def _run() -> dict:", "    def _run() -> dict[str, Any]:")
    src = src.replace(
        "        return dispatch_fn(name, args, tool_call_id=tool_id)",
        "        return str(dispatch_fn(name, args, tool_call_id=tool_id))",
    )
    src = src.replace(
        "        return finalize(\n            name,\n            args,\n            {\n                \"error\": f\"Tool execution failed: {exc}\",\n                \"code\": \"TOOL_DISPATCH_ERROR\",\n            },\n        )",
        "        return str(\n            finalize(\n                name,\n                args,\n                {\n                    \"error\": f\"Tool execution failed: {exc}\",\n                    \"code\": \"TOOL_DISPATCH_ERROR\",\n                },\n            )\n        )",
    )
    p.write_text(src, encoding="utf-8")

    # tool_batch_runner_ops
    p = CORE / "tool_batch_runner_ops.py"
    src = p.read_text(encoding="utf-8")
    src = src.replace("def parse_tool_call_args_safe(tc: Any) -> dict:", "def parse_tool_call_args_safe(tc: Any) -> dict[str, Any]:")
    src = src.replace("    def _run() -> dict:", "    def _run() -> dict[str, Any]:")
    src = src.replace("        return tc.args_dict()", "        raw = tc.args_dict()\n        return dict(raw) if isinstance(raw, dict) else {}")
    p.write_text(src, encoding="utf-8")

    # model_context_ops
    patch(
        CORE / "model_context_ops.py",
        "    return safe_best_effort(_run, label=\"model_context.max_output_tokens\", default=None)",
        "    result = safe_best_effort(_run, label=\"model_context.max_output_tokens\", default=None)\n"
        "    return int(result) if isinstance(result, int) else None",
    )

    # prompt_renderer_ops
    patch(
        CORE / "prompt_renderer_ops.py",
        "        return static_system_reminder_enabled()",
        "        return bool(static_system_reminder_enabled())",
    )

    # reasoning_trace_ops
    patch(
        CORE / "reasoning_trace_ops.py",
        "        return enrich_fix_hint(level, state)",
        "        return str(enrich_fix_hint(level, state) or \"\")",
    )

    # reflection_closure_ops
    p = CORE / "reflection_closure_ops.py"
    src = p.read_text(encoding="utf-8")
    if "cast" not in src:
        src = src.replace("from pathlib import Path\n", "from pathlib import Path\nfrom typing import cast\n")
    src = src.replace("        return _reflex_path()", "        return cast(Path, _reflex_path())")
    src = src.replace(
        "    return env_truthy(\"BUTLER_REFLECTION_CLOSURE_WRITE\", default=False)",
        "    return bool(env_truthy(\"BUTLER_REFLECTION_CLOSURE_WRITE\", default=False))",
    )
    p.write_text(src, encoding="utf-8")

    # session_hydration_ops
    p = CORE / "session_hydration_ops.py"
    src = p.read_text(encoding="utf-8")
    if "cast" not in src:
        src = src.replace("from typing import Any\n", "from typing import Any, cast\n")
    src = src.replace(
        "        return effective_workspace(Path(workspace))",
        "        return cast(Path, effective_workspace(Path(workspace)))",
    )
    src = src.replace(
        "    return safe_best_effort(_run, label=\"session_hydration.transcript_ts\", default=None)",
        "    result = safe_best_effort(_run, label=\"session_hydration.transcript_ts\", default=None)\n"
        "    return float(result) if isinstance(result, (int, float)) else None",
    )
    p.write_text(src, encoding="utf-8")

    # session_transcript_ops
    for label, fn in (
        ("session_transcript.load_tail_index", "load_tail_rows_safe"),
        ("session_transcript.load_tail_full_read", "load_tail_full_read_safe"),
    ):
        pass
    p = CORE / "session_transcript_ops.py"
    src = p.read_text(encoding="utf-8")
    src = src.replace(
        "    return safe_best_effort(\n        _run,\n        label=\"session_transcript.load_tail_index\",\n        default=None,\n    )",
        "    result = safe_best_effort(\n        _run,\n        label=\"session_transcript.load_tail_index\",\n        default=None,\n    )\n"
        "    return result if isinstance(result, list) else None",
    )
    src = src.replace(
        "    return safe_best_effort(\n        _run,\n        label=\"session_transcript.load_tail_full_read\",\n        default=None,\n    )",
        "    result = safe_best_effort(\n        _run,\n        label=\"session_transcript.load_tail_full_read\",\n        default=None,\n    )\n"
        "    return result if isinstance(result, list) else None",
    )
    p.write_text(src, encoding="utf-8")

    # tool_batch_finalize_ops
    p = CORE / "tool_batch_finalize_ops.py"
    src = p.read_text(encoding="utf-8")
    src = src.replace(
        "        return finalize_unenveloped_failure_result(name, args, result)",
        "        return str(finalize_unenveloped_failure_result(name, args, result))",
    )
    src = src.replace(
        "        return finalize_fallback_tool_result(\n            name,\n            args,\n            {\n                \"error\": f\"Tool execution failed: {exc}\",\n                \"code\": \"TOOL_DISPATCH_ERROR\",\n            },\n        )",
        "        return str(\n            finalize_fallback_tool_result(\n                name,\n                args,\n                {\n                    \"error\": f\"Tool execution failed: {exc}\",\n                    \"code\": \"TOOL_DISPATCH_ERROR\",\n                },\n            )\n        )",
    )
    p.write_text(src, encoding="utf-8")

    # tool_dispatch_doom_ops
    p = CORE / "tool_dispatch_doom_ops.py"
    src = p.read_text(encoding="utf-8")
    src = src.replace(
        "            return finalize_fallback_tool_result(name, args, synthetic_result(ask_dec))",
        "            return str(finalize_fallback_tool_result(name, args, synthetic_result(ask_dec)))",
    )
    src = src.replace(
        "        return finalize_fallback_tool_result(name, args, synthetic_result(before))",
        "        return str(finalize_fallback_tool_result(name, args, synthetic_result(before)))",
    )
    p.write_text(src, encoding="utf-8")

    # tool_dispatch_ops
    patch(
        CORE / "tool_dispatch_ops.py",
        "        return annotate_mutation_not_landed(tool_name, result)",
        "        out = annotate_mutation_not_landed(tool_name, result)\n"
        "        if isinstance(out, tuple) and len(out) == 2:\n"
        "            return str(out[0]), bool(out[1])\n"
        "        return result, False",
    )

    # tool_orchestrator_ops
    patch(
        CORE / "tool_orchestrator_ops.py",
        "        return check_approval(command, cwd=cwd, session_key=session_key)",
        "        block = check_approval(command, cwd=cwd, session_key=session_key)\n"
        "        return str(block) if block else None",
    )

    # tool_retry_ops
    patch(
        CORE / "tool_retry_ops.py",
        "        return classify_tool_error(result) == ToolErrorKind.retry",
        "        return bool(classify_tool_error(result) == ToolErrorKind.retry)",
    )

    # transcript_search_ops
    patch(
        CORE / "transcript_search_ops.py",
        "    return safe_best_effort(\n        _run,\n        label=\"transcript_search.fts\",\n        default=None,\n    )",
        "    result = safe_best_effort(\n        _run,\n        label=\"transcript_search.fts\",\n        default=None,\n    )\n"
        "    return result if isinstance(result, list) else None",
    )

    # transcript_export_ops
    p = CORE / "transcript_export_ops.py"
    src = p.read_text(encoding="utf-8")
    src = src.replace(
        "    return safe_best_effort(\n        _run,\n        label=\"transcript_export.recent_tasks\",\n        default=None,\n    )",
        "    result = safe_best_effort(\n        _run,\n        label=\"transcript_export.recent_tasks\",\n        default=None,\n    )\n"
        "    return result if isinstance(result, list) else None",
    )
    src = src.replace(
        "    return safe_best_effort(\n        _run,\n        label=\"transcript_export.workspace\",\n        default=None,\n    )",
        "    result = safe_best_effort(\n        _run, label=\"transcript_export.workspace\", default=None)\n"
        "    return result if isinstance(result, Path) else None",
    )
    p.write_text(src, encoding="utf-8")

    print("Applied wave2b patches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
