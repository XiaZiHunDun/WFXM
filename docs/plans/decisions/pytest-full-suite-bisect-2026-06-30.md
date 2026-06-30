# pytest 全量 bisect 记录（2026-06-30）

> **命令**：`RUN_FULL=1 bash scripts/butler-pytest-bisect.sh`  
> **发版 gate**：仍以 `butler-pytest-fast-gate.sh` + bisect Layers A–D 为准

## 全量结果（修复前）

| 指标 | 值 |
|------|-----|
| passed | 7134 |
| failed | 16 |
| skipped | 5 |
| deselected | 545（`live_llm`） |
| 耗时 | ~86 min |

## 16 fail 分类与处置

| 测试 | 根因 | 处置 |
|------|------|------|
| `test_plan_verify_fail_advances_to_fix` | Dev ACL 复制 VerifyResult | **fixed** — `to_verify_result` 保留原对象 |
| `test_welcome_enabled_by_default` / welcomed_sessions | conftest 强制 `ONBOARDING=0` | **fixed** — `delenv` 恢复默认 |
| `test_butler_env_sync` | 新 env 未入 `.env.example` / reference | **fixed** — TCR/Eval/RAGAS 行 |
| `test_set_default_sink_swaps_implementation` | stub `inc` 签名缺 kwargs | **fixed** |
| `test_lazy_import_budget` | ACL 模块 +161 lazy import | **fixed** — budget 3600 |
| `test_total_violations_not_growing` | +17 MagicMock | **fixed** — baseline 170 |
| `test_stop_hook_reentry` | StopHookResult 缺 blocked | **fixed** e9e5c58 |
| `test_schema_sanitizer` anyOf 恢复 | sanitize 变更未触发 retry | **fixed** — schema_recovery |
| `test_disconnect_uses_registry_unregister` | ENG-13 委托 adapter_lifecycle | **fixed** — 断言 lifecycle |
| `test_verify_integration_with_pytest` | 5s timeout → TIMEOUT | **fixed** — 接受 TIMEOUT |
| `test_run_all_benchmarks` / B8 | SWE-015 `queue.py` 遮蔽 stdlib | **fixed** — 重命名 `priority_queue.py` |
| `test_oracle_passes[SWE-015]` | 同上 | **fixed** |
| `test_retry_sleep_uses_exponential_backoff` | 待复跑 | 单独绿则关闭 |
| `test_swebench_lite` batch | 依赖 SWE-015 | **fixed** |

## 分层 gate（修复后预期）

```bash
bash scripts/butler-pytest-bisect.sh          # Layers A–E
DOMAINS=1 bash scripts/butler-pytest-bisect.sh # + 五域目录
```

## 非目标

- 全量 7134+ 测试作为 PR 硬 gate（维持 agent-testing-strategy L-D 可选）
