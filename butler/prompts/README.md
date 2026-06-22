# Butler 提示词 SSOT 索引

> 不单独做 Prompt 管理平台；改 prompt → `butler prompt eval` → `butler-wechat-owner-sim.sh --quick`。  
> 验收说明：[`docs/guides/phase-d-prompt-corpus.md`](../../docs/guides/phase-d-prompt-corpus.md)

## 系统模板（Markdown + 占位符）

| 文件 | 角色 | 占位符 / 注入 |
|------|------|----------------|
| [`butler_system.md`](butler_system.md) | 管家（默认 loop） | `{butler_name}` `{owner_name}` `{current_project}` `{project_list}` `{memory_context}` |
| [`lingwen_lead_system.md`](lingwen_lead_system.md) | 项目 Lead（厂长） | `{current_project}` `{memory_context}` `{workflows_block}` `{lifecycle_block}` |
| [`butler_plan_mode.md`](butler_plan_mode.md) | 只读规划模式附录 | 由 `/规划` 注入 |
| [`dev_engine_system.md`](dev_engine_system.md) | Dev Engine 子系统 | 编码知识 / Synth |

加载与缓存：[`butler/orchestrator.py`](../orchestrator.py) · 渲染：[`butler/core/prompt_renderer.py`](../core/prompt_renderer.py)

## 内联 Profile（Python）

| 模块 | 用途 |
|------|------|
| [`butler/agent_profiles.py`](../agent_profiles.py) | 委派子代理 dev/content/review/lead 默认 system |

## 领域片段（Skill）

| 路径 | 说明 |
|------|------|
| `projects/<slug>/skills/*.md` | 项目级 Skill，如灵文 `lingwen-project-lead` |

## 工具描述

| 模块 | 说明 |
|------|------|
| [`butler/tools/tool_doc_templates.py`](../tools/tool_doc_templates.py) | registry 描述 +「何时不要用」 |

## 评估与回归

```bash
butler prompt eval                          # pattern rubric（CI 友好）
butler prompt eval --corpus-live-smoke      # 需 API key
bash scripts/butler-wechat-owner-sim.sh --quick
./scripts/corpus-test.sh pr-gate            # 改 gateway 语料时
```

Fixtures：[`tests/fixtures/prompt_eval/cases.yaml`](../../tests/fixtures/prompt_eval/cases.yaml)

## Owner 模拟 ↔ Prompt 对照

| owner-sim track | 主要 prompt 文件 |
|-----------------|------------------|
| `search` 竞品检索 | `butler_system.md` §网络检索 |
| `search` GitHub | `butler_system.md` §网络检索 + MCP |
| `delegate` | `butler_system.md` §任务委派 + `lingwen_lead_system.md` §路径 |
| `memory` /新对话 | `butler_system.md` §会话重置；Lead §5 |

Manifest： [`.butler/simulation/wechat-owner-scenarios.yaml`](../../.butler/simulation/wechat-owner-scenarios.yaml)
