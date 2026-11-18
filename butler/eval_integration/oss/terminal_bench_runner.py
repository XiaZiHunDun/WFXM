"""Terminal-Bench external anchor (opt-in, subset).

测量口径：同一个底层模型 + terminus-2 最小终端脚手架，不是 WFXM 完整
agent。它回答“模型在终端任务上的下限”，用于与内部 capability 集对照。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any

from butler.utilities.env_parse import int_env

DEFAULT_SUBSET = (
    "hello-world",
    "fix-permissions",
    "openssl-selfsigned-cert",
    "csv-to-parquet",
)
DEFAULT_DATASET = "terminal-bench-core==0.1.1"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def tb_binary() -> str | None:
    return _env("BUTLER_EVAL_TB_BIN") or shutil.which("tb")


def terminal_bench_available() -> bool:
    if _env("BUTLER_EVAL_TB_DISABLE") == "1":
        return False
    if not tb_binary():
        return False
    try:
        probe = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


def terminal_bench_subset() -> list[str]:
    raw = _env("BUTLER_EVAL_TB_SUBSET")
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    return list(DEFAULT_SUBSET)


def _failure_mode(value: Any) -> str:
    if value is None:
        return "unset"
    text = str(value)
    return text.rsplit(".", 1)[-1].lower()


def _trial_payloads(payload: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    trials = payload.get("results")
    return list(trials) if isinstance(trials, list) else []


def summarize_results(
    payload: dict[str, Any] | list[dict[str, Any]],
    *,
    dataset: str,
    agent: str,
    model: str | None,
    run_dir: str,
) -> dict[str, Any]:
    """把 Terminal-Bench 的 results.json 汇总成 suite metrics。"""
    trials = _trial_payloads(payload)
    by_task: dict[str, list[bool]] = {}
    failure_modes: Counter[str] = Counter()
    input_tokens = 0
    output_tokens = 0

    for trial in trials:
        task_id = str(trial.get("task_id") or trial.get("taskId") or "")
        if not task_id:
            continue
        by_task.setdefault(task_id, []).append(bool(trial.get("is_resolved")))
        failure_modes[_failure_mode(trial.get("failure_mode"))] += 1
        input_tokens += int(trial.get("total_input_tokens") or 0)
        output_tokens += int(trial.get("total_output_tokens") or 0)

    details = [
        {
            "taskId": task_id,
            "resolved": any(attempts),
            "attempts": len(attempts),
        }
        for task_id, attempts in sorted(by_task.items())
    ]
    resolved = sum(1 for row in details if row["resolved"])
    total = len(details)

    return {
        "mode": "terminal_bench",
        "dataset": dataset,
        "agent": agent,
        "model": model,
        "tasks": total,
        "passed": resolved,
        "pass_rate": round(resolved / total, 4) if total else 0.0,
        "attempts": len(trials),
        "failure_modes": dict(failure_modes),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "details": details,
        "run_dir": run_dir,
    }


def _build_command(
    *,
    binary: str,
    dataset: str,
    tasks: list[str],
    agent: str,
    model: str | None,
    api_base: str | None,
    output_dir: Path,
    run_id: str,
) -> list[str]:
    command = [
        binary,
        "run",
        "-d",
        dataset,
        "--agent",
        agent,
        "--output-path",
        str(output_dir),
        "--run-id",
        run_id,
        "--n-concurrent",
        "1",
        "--no-upload-results",
    ]
    for task in tasks:
        command.extend(["-t", task])
    if model:
        command.extend(["-m", model])
    if api_base:
        command.extend(["-k", f"api_base={api_base}"])
    if _env("BUTLER_EVAL_TB_TEMPERATURE"):
        command.extend(["-k", f"temperature={_env('BUTLER_EVAL_TB_TEMPERATURE')}"])
    if _env("BUTLER_EVAL_TB_REBUILD", "1") == "0":
        command.append("--no-rebuild")
    if _env("BUTLER_EVAL_TB_CLEANUP", "1") == "0":
        command.append("--no-cleanup")
    if _env("BUTLER_EVAL_TB_TEST_TIMEOUT"):
        command.extend(["--global-test-timeout-sec", _env("BUTLER_EVAL_TB_TEST_TIMEOUT")])
    return command


def _load_results(run_root: Path) -> tuple[dict[str, Any] | list[dict[str, Any]] | None, str]:
    try:
        root_file = run_root / "results.json"
        if root_file.is_file():
            return json.loads(root_file.read_text(encoding="utf-8")), str(root_file)
        trials = list(run_root.glob("*/*/results.json"))
        if not trials:
            return None, ""
        payloads = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(trials)]
        return payloads, str(run_root)
    except (OSError, json.JSONDecodeError):
        return None, ""


def run_terminal_bench_eval(*, warn_only: bool = False) -> tuple[bool, dict[str, Any]]:
    binary = tb_binary()
    if not binary:
        return True, {"skipped": True, "reason": "tb 未安装（设置 BUTLER_EVAL_TB_BIN）"}
    if not terminal_bench_available():
        return True, {"skipped": True, "reason": "Docker 不可用或 BUTLER_EVAL_TB_DISABLE=1"}

    dataset = _env("BUTLER_EVAL_TB_DATASET") or DEFAULT_DATASET
    tasks = terminal_bench_subset()
    agent = _env("BUTLER_EVAL_TB_AGENT") or "terminus-2"
    model: str | None = None
    api_base = _env("BUTLER_EVAL_TB_API_BASE")
    if agent != "oracle":
        configured = _env("BUTLER_EVAL_TB_MODEL")
        minimax_model = _env("MINIMAX_MODEL")
        model = configured or (f"openai/{minimax_model}" if minimax_model else "")
        if not model:
            return False, {"error": "缺少模型：设置 BUTLER_EVAL_TB_MODEL 或 MINIMAX_MODEL"}
        api_base = api_base or _env("MINIMAX_BASE_URL")

    run_id = _env("BUTLER_EVAL_TB_RUN_ID") or f"tb-{time.strftime('%Y%m%d-%H%M%S')}"
    output_dir = Path(
        _env("BUTLER_EVAL_TB_OUT_DIR")
        or Path.home() / ".cache" / "butler-eval" / "terminal-bench"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    run_root = output_dir / run_id

    command = _build_command(
        binary=binary,
        dataset=dataset,
        tasks=tasks,
        agent=agent,
        model=model or None,
        api_base=api_base or None,
        output_dir=output_dir,
        run_id=run_id,
    )
    env = os.environ.copy()
    env.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    if model and not env.get("OPENAI_API_KEY"):
        key = _env("BUTLER_EVAL_TB_API_KEY") or _env("MINIMAX_CN_API_KEY") or _env("MINIMAX_API_KEY")
        if key:
            env["OPENAI_API_KEY"] = key

    timeout = int_env("BUTLER_EVAL_TB_TIMEOUT", 5400, min=60, max=24 * 3600)
    started = time.time()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = round(time.time() - started, 1)
        log = "\n".join(
            part.decode(errors="ignore") if isinstance(part, bytes) else part
            for part in (exc.stdout, exc.stderr)
            if part
        )
        run_root.mkdir(parents=True, exist_ok=True)
        (run_root / "tb-eval.log").write_text(log, encoding="utf-8")
        return warn_only, {
            "error": f"Terminal-Bench 超时（{timeout}s）",
            "elapsed_seconds": elapsed,
            "tasks": tasks,
            "run_dir": str(run_root),
            "log_tail": "\n".join(log.strip().splitlines()[-8:]),
        }
    except OSError as exc:
        return False, {"error": f"无法执行 tb：{exc}", "tasks": tasks, "run_dir": str(run_root)}

    elapsed = round(time.time() - started, 1)
    log = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "tb-eval.log").write_text(log, encoding="utf-8")

    payload, source = _load_results(run_root)
    if payload is None:
        tail = "\n".join(log.strip().splitlines()[-8:])
        return warn_only, {
            "error": "Terminal-Bench 未产出 results.json",
            "exit_code": completed.returncode,
            "elapsed_seconds": elapsed,
            "tasks": tasks,
            "run_dir": str(run_root),
            "log_tail": tail,
        }

    metrics = summarize_results(
        payload,
        dataset=dataset,
        agent=agent,
        model=model or None,
        run_dir=str(run_root),
    )
    metrics["source"] = source
    metrics["elapsed_seconds"] = elapsed
    threshold = float(_env("BUTLER_EVAL_TB_MIN_PASS_RATE", "0") or 0)
    ok = metrics["tasks"] > 0 and metrics["pass_rate"] >= threshold
    if warn_only:
        ok = True
    return ok, metrics
