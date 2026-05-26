# Prompt Corpus ↔ Butler 对标报告（2026-05）

> 语料来源：`reference/system-prompts-and-models-of-ai-tools`（各产品泄露/收集的 system prompt 与 tools JSON，**非可运行源码**）。  
> 工程化对标见 [external-reference-roadmap-2026-05.md](../../guides/external-reference-roadmap-2026-05.md)（Hermes/LangChain/Dify/Langflow）；本文档为 **Prompt Corpus 线** 互补。

## 1. 语料库按维度分类

| 维度 | 代表 | 提炼到 Butler |
|------|------|----------------|
| Agent Loop 本体 | Manus Agent loop / Modules | transcript 事件类型 `plan_step`、`knowledge_inject`、`tool_observation`；tombstone 加权保留 |
| 规划 vs 执行 | Traycer plan_mode、Devin、Antigravity planning | `butler_plan_mode.md`、`/规划`、role=`plan` 工具白名单 |
| 工具路由 DSL | Cursor Agent 2.0、Claude Code Tools.json | `tool_doc_templates.py`：何时用 / 何时不要用 / 示例 |
| 并行工具 | Claude Code Task、Cursor speculative read | 已有 `enable_parallel_tools`；父 loop 保持并行 |
| 长任务进度 UX | Antigravity task_boundary | `gateway/task_milestone.py` + `BUTLER_GATEWAY_TASK_MILESTONE` |
| 大文件读 | Traycer read_partial | `read_file_partial.py` 摘要 + offset/limit 契约 |
| 模式分类器 | Kiro Mode_Classifier | **defer**（E2） |
| 单工具/迭代 | Manus one-tool-per-iter | **defer**（E3，子 Agent 可配置） |

## 2. Butler 已有 vs 本次补齐

| 语料概念 | 落地前 | 阶段 D/E |
|----------|--------|----------|
| 压缩摘要 | `compaction_prompt.py` | 不变 |
| 子 Agent / 并行 | `delegate_task`、`enable_parallel_tools` | 不变 |
| 工作流 + gate | `workflows/runner.py`、`human_gate.py` | 不变 |
| 出站里程碑 | `outbound_bridge.py` | + task_milestone 结构化进度 |
| 规划模式 | `plan_mode.py`（工具 block） | + 专用 prompt、`/规划`、plan role 白名单 |
| 工具描述反模式 | 短 description | + DSL 模板 |
| transcript 本体 | `workflow_step` 等 | + plan/knowledge/tool_observation |
| 大文件 read | offset/limit | + 超阈值自动摘要 |

## 3. 阶段 D/E 落点索引

| ID | 文件 |
|----|------|
| D1 | `butler/tools/tool_doc_templates.py`、`butler/tools/registry.py` |
| D2 | `butler/prompts/butler_system.md`（`<agent_discipline>`） |
| D3 | `butler/prompts/butler_plan_mode.md`、`butler/plan_mode.py`、`butler/tools/project_tools.py`、`butler/gateway/message_handler.py` |
| D4 | `butler/core/session_transcript.py`、`butler/core/transcript_retention.py` |
| D5 | `butler/core/read_file_partial.py`、`butler/tools/registry.py`（`_tool_read_file`） |
| E1 | `butler/gateway/task_milestone.py`、`butler/gateway/outbound_bridge.py` |

验收：`tests/test_prompt_corpus_patterns.py`；运维说明 [phase-d-prompt-corpus.md](../../guides/phase-d-prompt-corpus.md)。

## 4. 明确不做

- 不复制各厂商 system prompt 全文进生产模板
- 不引入 Manus 级 sandbox/browser/公网部署
- 不用语料库 JSON 直接替换 Butler tool schema 字段
- 不建多产品 prompt 对比 UI

## 5. E2–E4（已落地，保守默认）

| ID | 落点 | 默认 |
|----|------|------|
| E2 | `butler/core/mode_classifier.py` | 启发式建议 `/规划`；不自动开启 plan（除非 `BUTLER_MODE_CLASSIFIER_AUTO_PLAN=1`） |
| E3 | `delegate_policy.delegate_one_tool_per_iteration` | **关**；委派子 loop `enable_parallel_tools=False` |
| E4 | `compaction_prompt.PREFLIGHT_CHECKLIST_APPENDIX` | **开**；压缩时提醒测试/未改完/权限阻塞 |

## 6. 交叉引用

- [external-reference-roadmap-2026-05.md](../../guides/external-reference-roadmap-2026-05.md)
- [external-reference-deferred-2026-05.md](../../guides/external-reference-deferred-2026-05.md)
- [cc-butler-gap-analysis-2026-05.md](../active/cc-butler-gap-analysis-2026-05.md)
