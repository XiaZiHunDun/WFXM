# 阶段 C — 规模与工程化（按需）

> 2026-05-25 · 零新增 pip 依赖（LangChain / Langflow / Dify / Hermes 路线图 C 项）

## 已落地

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

## 补做（原「未做」子集）

| 项 | 说明 |
|----|------|
| C8 轻量检索 | `search_project_knowledge`（复用 semantic + MEMORY） |
| C9 凭证分离 | `~/.butler/secrets.yaml` + `butler secrets set`（600，非加密） |
| B9 补充 | `list_workflows` 工具 |

完整分析与仍 defer 项见 [`external-reference-deferred-2026-05.md`](external-reference-deferred-2026-05.md)。

## 仍单独立项

| 项 | 说明 |
|----|------|
| Fernet 加密 secrets | 需 `cryptography` + 安全评审 |
| execute_code 生产默认 | 须 `BUTLER_EXECUTE_CODE=1` + 安全评审 |
| iLink 真流式编辑 | API 能力验证 |

## 验收

```bash
pytest tests/test_phase_c_external.py tests/test_phase_b_external.py tests/test_phase_a_external.py -q
butler workflow validate --path .butler/workflows/your.yaml
```

### permissions.yaml 示例（C6）

```yaml
tool_policies:
  write_file: ask
  terminal: deny
```

## 关系

- 阶段 A：网关 / 压缩 / auto-continue → [`phase-a-external-reference.md`](phase-a-external-reference.md)
- 阶段 B：安全 / Registry / 工具纪律 → [`phase-b-external-reference.md`](phase-b-external-reference.md)
