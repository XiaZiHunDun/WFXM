# 外部对标阶段 A / B / C — 验收索引（合并版）

> **更新**：2026-05-25 · 零新增 pip 依赖  
> **总索引**：[`external-reference-roadmap-2026-05.md`](external-reference-roadmap-2026-05.md)  
> **defer / 补做**：[`external-reference-deferred-2026-05.md`](external-reference-deferred-2026-05.md)  
> **历史拆分**：原 `phase-a/b/c-external-reference.md` 已并入本文（§A–§C）

---

## 总验收

```bash
pytest tests/test_phase_a_external.py tests/test_phase_b_external.py tests/test_phase_c_external.py -q
```

---

## §A — 微信体验与网关

| 项 | 模块 | 环境变量 |
|----|------|----------|
| 压缩前 AI/Tool 成对切分 | `butler/core/compaction_cutoff.py` | — |
| 压缩触发优先 usage | `hygiene_preflight.py` | `/诊断` 见 `hygiene_compact_trigger_source` |
| 流式 memory-context scrub | `transport/memory_context_scrubber.py` | `BUTLER_STREAM_MEMORY_SCRUB` |
| Gateway 流式预览（ack） | `outbound_bridge.append_stream_preview` | `BUTLER_GATEWAY_STREAM_PREVIEW=1` |
| auto-continue | `core/auto_continue.py` | `BUTLER_AUTO_CONTINUE` / `MAX_AGE` |
| slash 旁路 `/stop` 等 | `message_handler` 入队前 | — |
| workflow 节点事件 | `session_transcript` `workflow_step` + bridge | — |
| 出站事件类型 | `gateway/outbound_events.py` | health `outbound_events` |

**微信抽测**：长任务 ack 预览；中断后「继续」；`/stop` 打断；workflow 失败有 `workflow_step` fail。

---

## §B — 安全 / Registry / 工具纪律 / 工作流变量

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

**微信抽测**：出站手机号脱敏；`rm -rf /` 类 terminal 拦截；`output_keys` 变量展开；gate TTL；catalog manifest 校验。

---

## §C — 规模与工程化

| 项 | 模块 | 环境变量 |
|----|------|----------|
| C1 工具预选 | `core/tool_selector.py` + `agent_loop` | `BUTLER_TOOL_SELECTOR` / `THRESHOLD` |
| C2 Loop 插件契约 | `core/loop_plugins.py` + `LoopConfig.plugins` | — |
| C3 只读工具结果缓存 | `core/tool_result_cache.py` + `tool_batch` | `BUTLER_TOOL_RESULT_CACHE` / `TTL` |
| C4 Workflow 校验 CLI | `workflows/validate.py` + `butler workflow validate` | `schema_version` in YAML |
| C5 工具分层诊断 | `tools/provider_layers.py` | — |
| C6 单工具 HITL | `permissions.evaluate_tool_policy` | `tool_policies` in permissions.yaml |
| C7 execute_code（默认关） | `tools/execute_code.py` | `BUTLER_EXECUTE_CODE=0` |
| Hermes 摘要 v2 | `compaction_prompt` Hermes 模板 | `BUTLER_COMPACTION_USE_HERMES_TEMPLATE` |
| Hermes 渐进流式 | `gateway/progressive_stream.py` | `BUTLER_GATEWAY_PROGRESSIVE_STREAM` |
| Terminal 批准按会话 | `terminal_approval.check_approval(session_key=)` | — |

**补做子集**：C8 `search_project_knowledge`；C9 `secrets.yaml`；B9 `list_workflows` — 见 [`external-reference-deferred-2026-05.md`](external-reference-deferred-2026-05.md)。

**仍 defer**：Fernet 加密 secrets；execute_code 生产默认；iLink 真流式编辑。

```bash
butler workflow validate --path .butler/workflows/your.yaml
```

**permissions.yaml 示例（C6）**：

```yaml
tool_policies:
  write_file: ask
  terminal: deny
```

---

## 阶段依赖关系

```text
A（网关/压缩/auto-continue）→ B（安全/Registry/工具纪律）→ C（预选/插件/validate）
```
