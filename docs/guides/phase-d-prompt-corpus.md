# 阶段 D/E：Prompt Corpus 线验收

> 对标 `reference/system-prompts-and-models-of-ai-tools` 的设计模式（非源码移植）。对照全文：[prompts-corpus-butler-comparison-2026-05.md](../plans/comparisons/prompts-corpus-butler-comparison-2026-05.md)。

## 自动化验收

```bash
pytest tests/test_prompt_corpus_patterns.py -q
pytest tests/test_plan_mode.py -q
```

## D1 工具描述 DSL

- 核心工具 `read_file`、`search_files`、`delegate_task`、`terminal`、`patch`、`write_file`、`list_directory` 的 registry description 含 **何时不要用**。
- 模板：`butler/tools/tool_doc_templates.py`。

## D2 系统提示纪律

- `butler/prompts/butler_system.md` 含 `<agent_discipline>`：语言、批量只读工具、微信确认、规划模式约束。

## D3 规划模式

| 入口 | 行为 |
|------|------|
| `/计划`、`/规划` | 开启只读规划；重建会话 loop（`role=plan`） |
| `/执行`、`/退出规划` | 关闭规划；恢复完整工具 |

- 专用附录：`butler/prompts/butler_plan_mode.md`
- 仍禁止：`delegate_task`、`terminal`、非 plan 路径写入（见 `plan_mode.py`）

## D4 Transcript 事件

| type | 用途 |
|------|------|
| `plan_step` | 进入/规划阶段标记 |
| `knowledge_inject` | 记忆预取注入 |
| `tool_observation` | 工具结果摘要 |

超大 transcript 裁剪时按 `transcript_retention.py` 优先级保留高价值行。

## D5 大文件读取

- 行数 > `BUTLER_READ_FILE_SUMMARY_THRESHOLD`（默认 400）且 `offset=1`、`limit>=100` 时返回 **大文件摘要**，提示 `offset`/`limit` 二次读取。

## E1 微信长任务里程碑（可选）

```bash
BUTLER_GATEWAY_TASK_MILESTONE=1
BUTLER_GATEWAY_TASK_MILESTONE_SECONDS=90   # 默认 90，且需已发 progress ack
```

格式：`【进度】阶段 | 正在做什么 | 下一步（约 N 秒）`。

## E2–E4（原 defer，已落地）

| ID | 默认 | 说明 |
|----|------|------|
| E2 | `BUTLER_MODE_CLASSIFIER=1` | 启发式 plan/do **建议**（ephemeral banner），不自动改模式；`AUTO_PLAN=0` |
| E2 aux | `BUTLER_MODE_CLASSIFIER_AUX=0` | 边界句可选 auxiliary JSON 分类 |
| E3 | `BUTLER_DELEGATE_ONE_TOOL_PER_ITERATION=0` | 设为 `1` 时委派子 loop 关闭并行工具 |
| E4 | `BUTLER_COMPACTION_PREFLIGHT_CHECKLIST=1` | 压缩摘要 prompt 附带完成前自检要点 |

```bash
pytest tests/test_mode_classifier_defer.py -q
```

## 与 external-ref 测试关系

阶段 A/B/C 测试（26 项）与本文件独立；发版前建议一并运行：

```bash
pytest tests/test_phase_a_external.py tests/test_phase_b_external.py \
  tests/test_phase_c_external.py tests/test_prompt_corpus_patterns.py -q
```
