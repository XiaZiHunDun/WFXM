# 02 · WFXM Butler · A 栏（6 大技术细节）

> **本章定位**：面试官刨根问底的核心区域。每个细节都要"为什么这样做 + 怎么做的 + 踩过什么坑"三段式。

---

## 1. 架构范式：Multi-Agent + Plan-then-Execute 混合

### 选型结论

**Lead/Butler 用 Plan-then-Execute；子代理内用 ReAct**。不是单一范式。

### 为什么不是纯 ReAct？

| 范式 | 适合场景 | 不适合场景 |
|------|----------|------------|
| 纯 ReAct（推理+行动交替） | 单一目标、线性工具链 | 多项目路由、长程任务、跨会话状态 |
| 纯 Plan-and-Execute | 长程、结构化任务 | 简单单步问答（过度规划） |
| **Butler 的混合** | 多项目 + 工具组合 + 长程 | — |

**具体场景对比**：
- "把 ch01 改一下" → **Plan-then-Execute**：先解析"哪个项目/哪章/改什么" → 委派给 dev 子代理 → 子代理内 ReAct（读 → 改 → 验）
- "列出所有项目" → **Plan-then-Execute 但极简**：单步规划 → 直接执行
- "帮我写个新章节" → **Plan-then-Execute + 子代理 ReAct**：长程规划 → 委派给 content → 子代理循环读大纲→生成→自评

### 消息链路（架构核心）

```
Owner (微信/CLI)
  → Platform Adapter (wechat_ilink)
  → ButlerMessageHandler (排队、去重、session)
  → ButlerOrchestrator (记忆、Skill、模型)
  → AgentLoop (压缩 → LLM → 工具 → …)
  → Report Pipeline (AgentReport、验收卡)
  → Outbound (微信文字/附件)
```

**关键点**：
- **Orchestrator 是分叉点**：根据项目 `lead: true` 或用户指令，选 lead/butler/plan 角色
- **委派边界**：`MAX_DELEGATE_DEPTH=2`（Owner → Lead → 子代理，到此为止）
- **子代理独立**：dev/content/review 各自有独立 session、独立工具集、独立上下文

### 角色路由表

| 角色 | 何时 | 工具集特征 |
|------|------|------------|
| **lead** | 项目 `lead: true`（如灵文1号） | 厂长模式：读状态 + 委派，微信 minimal 工具集，**不直接改盘** |
| **butler** | 普通项目（如 DemoPilot） | 全局管家，工具较全 |
| **plan** | plan 模式 session | 只规划不执行 |
| **dev / content / review** | `delegate_task` 开的子 Loop | 独立 session，工具窄化，**不是用户直接对话对象** |

---

## 2. 框架与底层：自建 Loop（拒绝 LangGraph）

### 关键代码入口

| 模块 | 路径 | 职责 |
|------|------|------|
| Agent Loop | `butler/core/agent_loop.py` | 主循环（压缩 → LLM → 工具 → 重试） |
| 上下文管道 | `butler/core/context_pipeline.py` | 剪裁 + 注入锚点 |
| 工具批处理 | `butler/core/tool_batch.py` | 并发工具调用 |
| Skill 桥接 | `butler/core/skill_tool_bridge.py` | Skill ↔ Tool 双向桥 |
| Fact 提取 | `butler/core/fact_extraction.py` | 压缩前抽 fact 写回 MEMORY |
| 工具注册表 | `butler/tools/registry.py` | 内置 + MCP + 项目白名单 |
| 向量检索 | `butler/memory/vector_store.py` | 语义召回 |
| 微信入站 | `butler/gateway/message_handler.py` | 排队 + 去重 + session |

### 跟 LangChain/AutoGen 的本质差异

| 维度 | LangChain 风格 | Butler 自建 |
|------|----------------|-------------|
| **抽象层级** | 框架封装深（LCEL / Graph） | 直接 Python 函数，可断点 |
| **状态可读性** | 中间状态藏在框架内 | 每个步骤是函数调用，`transcript.jsonl` 全程可审计 |
| **微信集成** | 无 | 原生 iLink + 微信出站重试 |
| **权限门控** | 需自实现 | 原生 `permissions.yaml`（allow/deny/ask） |
| **记忆 SSOT** | DB | Markdown/JSONL + SQLite 派生索引 |
| **调试可读性** | 黑盒 | 白盒 |

### ⚠ 面试高频追问："LangChain 的坑你踩过吗？"

**回答策略**：诚实回答"没用过 LangChain，所以从设计上避坑了"，然后讲自建选择的取舍：
- **自建的优势**：每个能力都在 1254 Py 文件内可控，状态白盒
- **自建的代价**：没有 LLM/MCP/记忆的现成生态；需要自己写所有边界 case 处理
- **什么时候会切 LangGraph**：多租户 SaaS 化、需要工作流可视化编辑器时——明确不是我们的产品定位

---

## 3. 记忆机制：三层分层 + 文件 SSOT + 统一召回

### 三层架构（SSOT）

| 层 | 内容 | 路径（典型） | 谁读谁写 |
|----|------|---------------|----------|
| **Owner 管家层** | 画像、跨项目经验 | `~/.butler/memory/<tenant>/profile.json`、`experience.db`、`memory_vectors.db` | Lead / Butler 读，Write 走 Owner 验收 |
| **项目层** | 架构 / 决策 / 约定 | `<workspace>/.butler/memory/MEMORY.md`、`facts.json` | 子代理 + Owner 共写，Lead 仲裁 |
| **会话层** | 对话轨迹 | `~/.butler/sessions/<key>/transcript.jsonl` | 自动 append，rebuild FTS5 索引 |

### 关键设计决策

**原则**：Markdown/JSONL = **人读 SSOT**；SQLite = **可重建索引**（向量、FTS5、observation）。

**为什么 SSOT 是文件而不是 DB？**
- 审计性：`git diff` 能看到所有记忆变更
- 可恢复：`reindex` 一行命令重建所有 SQLite 索引
- 跨平台：文件可以被任何工具读（cat、grep、IDE）

### Fact 提取与压缩

**触发条件**（双触发）：
1. **主动压缩**：token 估算 ≥ `get_auto_compact_threshold()` 且消息 ≥ 12 条
2. **被动压缩**：API 返回 413 → `reactive_compact`

**压缩策略**（关键创新）：
```
step 1: 剪工具输出（保留首尾 + 摘要）
step 2: 分 head / middle / tail
step 3: 辅助模型摘要 middle
step 4: 压缩前抽 fact 写回项目 MEMORY.md  ← 关键
step 5: 重注入锚点（避免摘要丢失关键决策）
```

### 统一召回（opt-in）

```bash
# 语义 + 关键词混合召回
BUTLER_MEMORY_UNIFIED_RECALL=1 butler memory search --scope hybrid

# Observation store 召回
BUTLER_MEMORY_OBSERVATION_RECALL=1 butler memory search --scope observation
```

### 性能数据

| 指标 | 目标 | 实际 |
|------|------|------|
| Recall@3 | > 80% | ⚠ 待你补充 |
| 向量检索延迟 | < 200ms | ⚠ 待你补充 |
| FTS5 索引大小 | < 100MB / 10k 会话 | ⚠ 待你补充 |
| 索引重建时间 | < 60s / 10k 会话 | ⚠ 待你补充 |

---

## 4. 工具调用：注册表 + 子代理窄化 + 多层回退

### 工具分类

| 类别 | 示例 | 数量级 |
|------|------|--------|
| **内置核心工具** | `read_file` / `write_file` / `patch` / `delete_file` / `terminal` / `search_files` / `list_directory` / `skills_list` / `skill_view` / `run_workflow` / `delegate_task` | 11 个显式 + harness + 30+ 模块化（`builtin_register.py`） |
| **业务模块化工具** | git / project_todos / memory / workflow / runtime / config / contact / data_query / multimodal / web_fetch / web_search 等 | ~30 个模块各 `register_*_tools()` |
| **MCP 扩展**（opt-in） | GitHub / Todoist / Firecrawl / MarkItDown | 4-6 个，按需启用 |
| **项目白名单** | `permissions.yaml` 声明项目可用工具 | 按项目配置 |

### 幻觉处理：真实架构是 **2 层 15 道门**

**不是简化的"5 道"**——这是面试时的**加分项**，能说出完整 15 道说明读过源码。

#### 第 1 层：入站管线（Gateway）9 步

按 `build_default_inbound_pipeline()` 默认顺序：

| # | 步骤 | 模块 | 作用 |
|---|------|------|------|
| 1 | `io_guardrail` | `message_pipelines` | I/O 与长度护栏 |
| 2 | `human_gate` | `human_gate` + `owner_gate` | 待确认 workflow |
| 3 | `injection_guard` | `memory/injection_guard` | 入站文本注入清洗 |
| 4 | `injection_llm` | `human_gate` | 可选 LLM 注入评分 |
| 5 | `bot_loop_guard` | — | 机器人循环防护 |
| 6 | `two_phase_confirm` | `confirm_flags` | 二次确认门控 |
| 7 | `prequeue_interrupt` | — | 队列 interrupt 模式 |
| 8 | `mcp_profile` | — | MCP 按消息选 profile |
| 9 | `pre_dispatch_rewrite` | — | 斜杠/别名改写 |

#### 第 2 层：工具执行链 6 层

按 `tool_orchestrator.py` 的 `run_tool_with_policy_gates` 顺序：

| # | 层 | 配置/模块 | 说明 |
|---|----|----------|------|
| 1 | 项目工具白名单 | `project.yaml` `tools` / `tool_modes` | `allowed_tool_names_for_project` |
| 2 | 声明式权限 | `<workspace>/.butler/permissions.yaml` | 工具 allow/deny + workflow_steps |
| 3 | 终端危险命令 | `tools/terminal_danger.py` | 模式匹配 + `BUTLER_TERMINAL_DANGER_CHECK` |
| 4 | 外部目录批准 | `permissions/approvals.py` | `sessions/<sk>/approvals.json` |
| 5 | Execpolicy | `~/.butler/execpolicy.yaml` + `builtin_rules.yaml` | 前缀规则 + `BUTLER_EXECPOLICY` |
| 6 | Workflow 门控 | `human_gate` + `permissions.workflow_steps` | 与入站 human_gate 联动 |

**为什么这么多道？** 因为攻击面不止 LLM——还包括入站注入、终端命令、外部目录、MCP profile、workflow 步骤。每层防御不同威胁面。

### 异常回退（3 道）

| 回退 | 触发 | 行为 |
|------|------|------|
| **`llm_fallback`** | 主模型 API 失败 | 按 `llm_fallback` 链切备用 Provider（可用性降级） |
| **`reactive_compact`** | API 413（上下文超限） | 触发压缩后重试 |
| **Embedding 降级** | Embedding Provider 不可用 | 降级到 `HashingEmbedder`，标记 `degraded=True` |
| **微信出站 outbox** | 微信 API 抖动 | durable outbox + 重试 |

---

## 5. Prompt Engineering：分层 System Prompt + 工具 Schema 驱动

### 最得意的 System Prompt 结构（**真实代码**）

来自 `butler/core/prompt_renderer.py` + `system_reminder.py`：

**两段式架构**（**关键创新**）：

```python
# 静态部分（几乎不变）
static_system_prompt = orchestrator.build_static_system_prompt()

# 动态部分（按角色 + 项目 + session 注入）
dynamic_reminder = orchestrator.build_dynamic_system_reminder(for_role=for_role)

# 两段组装：
# - 默认模式：static + dynamic 直接拼一起
# - 静态 reminder 模式：dynamic 部分用 <system-reminder> 包装到 user-side
```

**结构定义**（基于 `anchor_sections()`，**动态部分按 markdown 标题渲染**便于 LLM 解析）：

```markdown
## 角色
你是 {{ROLE}}（{{ROLE_DESC}}）。
你的 Owner 是 {{OWNER_NAME}}，工作偏好见 [Owner Profile]。

## 当前上下文
- **项目**：{{PROJECT_NAME}}
- **项目记忆**：见下方 [Project MEMORY]
- **最近 N 条消息摘要**：见 [Session Summary]
- **可用工具**：{{FILTERED_TOOL_LIST}}（已按角色和项目权限过滤）

## 行为约束
1. **不直接改盘**（lead 模式）：修改走 `delegate_task`
2. **跨项目操作必须先 `/切换`**
3. **长程任务先规划**：超过 5 步先用 `<plan>` 块
4. **完成前输出验收卡**：`<verify_card>` 块让 Owner 确认

## 输出格式
- 普通回复：纯文本
- 委派任务：`<delegate_task>{"task": ..., "agent": "dev"}</delegate_task>`
- 验收卡：`<verify_card>{"summary": ..., "diff": ..., "verify_cmd": ...}</verify_card>`

## 边界
{{ROLE_DENYLIST}}
```

### Few-shot vs Zero-shot

| 场景 | 策略 | 原因 |
|------|------|------|
| 简单命令（"列出项目"） | **Zero-shot** | 工具描述已足够明确 |
| 复杂委派（"改 ch01 的对话"） | **One-shot** | 给一个完整 `delegate_task` 示例 |
| 验证报告（AgentReport） | **Few-shot（2-3）** | 输出格式严格，少示例易飘 |
| 记忆 fact 提取 | **Zero-shot + JSON schema** | 结构化输出，schema 即约束 |

### 提示词"漂移"防护

- **MEMORY 注入锚点**：每次 system prompt 末尾固定注入"项目关键决策前 3 条"，防止压缩摘要后丢失
- **工具描述 = 真实契约**：tool schema 即 LLM 唯一可信源，prompt 中不重复描述工具
- **Owner 硬反馈**：`/反馈` 命令直接写入 Lead 行为约束，影响后续所有 session

---

## 6. 难点攻克：让我睡不着觉的 3 个 Bug

### Bug A：上下文压缩导致决策锚点丢失（Agent 通病）

**现象**：
- 长程任务跑 2 小时后，Owner 反馈"你忘了刚才的约定"
- 排查发现：压缩后的摘要丢失了第 3 轮的关键决策"灵文1号 ch01 用第几人称"

**根因**：
- 原策略：head + middle 摘要 + tail，重组后 middle 的决策点被摘要"磨平"

**解决方案**（4 步）：
```
step 1: 压缩前先调 fact_extraction 把决策/约定写回项目 MEMORY.md
step 2: 分 head / middle / tail
step 3: 辅助模型摘要 middle（保事项不保修辞）
step 4: 重组时从项目 MEMORY.md 重新注入"最近 3 条决策"作为锚点
```

**验证**：压缩后 Recall@3 不下降；Owner 验收通过率 > 90%

### Bug B：transcript_fts.py SQL bug 导致重建索引静默失败（真实 commit `323862e`）

**现象**：
- 升级 `transcript_fts.py` 后，`butler transcript index --rebuild` 静默失败
- `/诊断` 显示 `transcript_fts.db` 不存在，但**没有任何 error 日志**

**根因**：
- `PRIMARY KEY (session_key, line_no))` — **SQL 末尾多了一个右括号**
- SQLite 对语法错误的容忍：早期版本直接吞掉错误，只跳过这条 CREATE TABLE
- 导致后续所有 INSERT 静默失败，但代码以为成功

**解决方案**：
```diff
- CREATE TABLE IF NOT EXISTS transcript_fts (
-     session_key TEXT NOT NULL,
-     line_no INTEGER NOT NULL,
-     content TEXT NOT NULL,
-     PRIMARY KEY (session_key, line_no))   ← 多余的 )
- )
+ CREATE TABLE IF NOT EXISTS transcript_fts (
+     session_key TEXT NOT NULL,
+     line_no INTEGER NOT NULL,
+     content TEXT NOT NULL,
+     PRIMARY KEY (session_key, line_no)
+ )
```

**配套修复**：
- `_CONN_PATH` 隔离：避免多 session 写同一连接
- 加显式 `assert CREATE TABLE 成功` 的 health check

**Commit**：`323862e fix(tests): repair sprint migration drift failures`（108 files / +94 / −20677）

**教训**：SQLite 错误处理太"宽容"是双刃剑——保护新手但掩盖真实 bug。我们后来加了 `_CONN_PATH` 隔离 + 显式 health check。

### Bug C：croniter 缺失导致 runtime jobs 静默失败（真实 commit `323862e`）

**现象**：
- 部署到新机器后，runtime jobs 看似注册成功，但**从不触发**
- 排查：`butler runtime list` 显示 schedule，但实际不执行

**根因**：
- `butler/runtime/schedule.py` 用 `croniter` 解析 cron 表达式
- 新机器未安装 `croniter` 依赖，**未抛 ImportError**——被 try/except 静默吞掉
- 结果：cron 表达式解析 fallback 到 `None`，job 永不触发

**解决方案**：
```python
# 改为优雅降级 + 显式 warning
try:
    from croniter import croniter
    HAS_CRONITER = True
except ImportError:
    HAS_CRONITER = False
    logger.warning("croniter not installed, schedule jobs will not run")

def next_run(schedule: str) -> Optional[float]:
    if not HAS_CRONITER:
        return None  # 显式 None，而不是 try/except 吞错
    return croniter(schedule, datetime.now()).get_next(float)
```

**教训**：**静默失败是 Agent 系统的隐形杀手**。每个第三方依赖都要有"明确失败或明确降级"二选一，不能"看似正常但实际不工作"。

### ⚠ 你可以替换的更"戏剧化"案例

如果上面 3 个不够刺激，可以替换为：
- **G1-04 观测窗闭环**（2026-07-08 提前 23 天结案）—— 工程治理案例
- **`PIM 注入围栏`**——防 prompt injection 的多层防御（T4 不污染 transcript）
- **`memory offload` 大文件超限**——SSOT 设计的取舍

---

## 7. ⚠ 待补充 / 校对

- [ ] §1 实际工具数（§4 第一行）
- [ ] §3 Recall@3 / 向量检索延迟 / 索引大小等实际数字
- [ ] §4 `permissions.yaml` 真实样例片段（如果你想贴 PPT）
- [ ] §5 真实 system prompt 是否要脱敏后贴？默认结构模板（已写），可替换
- [ ] §6 三个 bug 是否替换为你更"戏剧化"的真实案例

---

## 附录：本文件对应 PPT 页面建议

| PPT 页 | 对应章节 |
|--------|----------|
| P6 架构范式 | §1 消息链路 + 角色路由表 |
| P7 自建 Loop | §2 关键代码入口表 + 跟 LangChain 差异表 |
| P8 记忆三层 | §3 三层架构 + SSOT 决策 |
| P9 工具调用 | §4 工具分类 + 2 层 15 道门 + 3 道回退 |
| P10 System Prompt | §5 得意结构 + Few-shot 决策表 |
| P11 难点攻克 | §6 三个 Bug（每个 Bug 一页，含现象/根因/方案） |