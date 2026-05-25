# 阶段 B — 工程化 / 安全 / 工作流 / 工具纪律

> 2026-05-25 · 零新增 pip 依赖（对标 Hermes / LangChain / Dify / Langflow §6）

## 已落地

| 项 | 模块 | 环境变量 |
|----|------|----------|
| Usage 归一 | `transport/usage_normalize.py` + `agent_loop` | — |
| Registry SSRF | `registry/url_safety.py` `safe_registry_get` | `BUTLER_REGISTRY_ALLOWED_HOSTS` |
| Catalog SHA-256 | `registry/catalog_integrity.py` | `BUTLER_CATALOG_INTEGRITY` / `FAIL_CLOSED` |
| 工具瞬态重试 | `core/tool_retry.py` + `tool_batch` | `BUTLER_TOOL_RETRY` / `MAX` / `BACKOFF_SECONDS` |
| 按工具调用上限 | `core/tool_call_limits.py` | `BUTLER_TOOL_CALL_LIMIT_PER_TOOL` / `EXEMPT` |
| 出站 PII 脱敏 | `gateway/pii_scrub.py` | `BUTLER_OUTBOUND_PII_SCRUB` / `SCRUB_EMAIL` |
| Human gate TTL | `human_gate.py` | `BUTLER_GATEWAY_HUMAN_GATE_TTL` |
| Workflow 暂停快照 | `workflows/pause_state.py` | — |
| 步骤变量传递 | `workflows/variables.py` + runner 进度回调 | `output_keys` in step schema |
| Transcript 检索工具 | `search_transcript` | `BUTLER_TRANSCRIPT_SEARCH_*` |
| Terminal 危险模式 | `tools/terminal_danger.py` | `BUTLER_TERMINAL_DANGER_CHECK` |
| 子代理独立迭代上限 | `delegate_policy.resolve_delegate_max_iterations` | `BUTLER_DELEGATE_MAX_ITERATIONS` |

## 验收

```bash
pytest tests/test_phase_b_external.py -q
```

微信 / 运维：

1. 出站消息中的手机号是否被替换为 `[手机号已脱敏]`  
2. `rm -rf /` 类 terminal 是否返回 `TERMINAL_DANGER_PATTERN`  
3. 工作流步骤 `output_keys` 是否能在后续步骤 `{{steps.id.key}}` 中展开  
4. 人工 gate 超过 TTL 后是否自动失效（需重发 `/workflow`）  
5. Registry 启动时 catalog manifest 校验（改 catalog 文件后应触发告警或 fail-closed）

## 与阶段 A 关系

阶段 A 负责网关压缩、auto-continue、workflow 出站事件；阶段 B 在此基础上加强工具纪律、Registry 安全与 workflow 变量，详见 [`phase-a-external-reference.md`](phase-a-external-reference.md)。阶段 C（工具预选、Loop 插件、workflow validate、execute_code 门控等）见 [`phase-c-external-reference.md`](phase-c-external-reference.md)。
