# 03 · 高频追问 Q&A（10-15 条）

> **用途**：面试官追问时的快速参考。每条含"问题 → 一句话回答 → 展开"。

---

## A. 架构选型类

### Q1：为什么不用 LangChain / LangGraph？

**一句话**：单租户自托管 + 微信原生 + 极致可控的场景下，框架自带能力是负债而非资产。

**展开**：
- 业务代码 -33%（实测），无 breaking change 升级风险
- 每个工具调用是 Python 函数，可断点调试
- 状态白盒：`transcript.jsonl` 全程可审计

**SSOT**：`01-situation-task.md §2` + `02-action.md §2`

### Q2：为什么不直接用 Claude Code？

**一句话**：Claude Code 是 CLI-first，没有微信入口、多项目切换、分层记忆。

**展开**：
- 我的 Dev 子代理能力上限**对标** Claude Code CLI（CC 线束）
- 但 Butler 比 CC 多 5+ 能力：微信接入、多项目、记忆三层、runtime jobs、MCP 客户端

### Q3：为什么不直接用现成的 ChatGPT？

**一句话**：ChatGPT 是聊天工具，不是 Agent 平台。

**展开**：
- 无工具、无记忆、无项目隔离、无微信集成
- 我们解决的是"远程多项目管理"，不是聊天

---

## B. 记忆类

### Q4：为什么不用 Postgres / MySQL？

**一句话**：单租户自托管场景下，文件 SSOT 比数据库更易审计、可恢复。

**展开**：
- `git diff` 能看到所有记忆变更
- SQLite 索引可 `reindex` 重建
- 多项目隔离通过文件路径而非数据库 schema

### Q5：记忆压缩会不会丢关键信息？

**一句话**：会，所以我们**压缩前先抽 fact 写回 SSOT**，而不是"信任摘要"。

**展开**：
- 主动压缩：token ≥ 阈值 + 消息 ≥ 12 条
- 被动压缩：API 413 触发 `reactive_compact`
- 关键决策通过 fact_extraction 写回项目 MEMORY.md
- 锚点重注入：从 MEMORY 注入"最近 3 条决策"

### Q6：跨会话记忆准确率怎么测？

**一句话**：用 Recall@3（检索 top3 命中正确答案），配合 user feedback 校准。

**展开**：
- ⚠ 实际数字待你补充
- 评估价值不在"分数"，在"暴露盲区"

---

## C. 工具调用类

### Q7：Agent 幻觉怎么解决？

**一句话**：协议约束的是"格式"，不约束"意图"。所以我们用多道防线，不只靠 schema。

**展开**（口播精简版 5 道，好记）：
1. `permissions.yaml` 三态
2. `filter_tools_for_subagent` 子代理窄化
3. `read-before-edit` patch 前 read
4. `DELEGATE_BLOCKED_TOOLS` 禁止再 delegate
5. typed schema 严格校验

**⚠ 追问细节时**：真实是 **2 层 15 道门**——入站管线 9 步（io_guardrail → human_gate → injection_guard → injection_llm → bot_loop_guard → two_phase_confirm → prequeue_interrupt → mcp_profile → pre_dispatch_rewrite）+ 工具执行链 6 层（项目白名单 → permissions.yaml → terminal_danger → 外部目录批准 → execpolicy → workflow 门控）。见 `02-action.md §4`。

### Q8：工具数 100+ 怎么管理？

**一句话**：分层注册表 + 角色过滤 + 项目白名单。

**展开**：
- `registry.py` 按"业务域"分（delegate / memory / project / runtime / terminal / multimodal / network）
- 角色路由：lead / butler / plan / dev / content / review 不同工具集
- `permissions.yaml` 项目级 allow/deny

### Q9：Dev 子代理越权怎么办？

**一句话**：多道防线里有几道专门防御它，加上最后一道验收卡。

**展开**：
- 真实 bug：早期 dev 误改项目 `MEMORY.md`，根因是 `safe_root` 没生效
- 修法 4 管齐下：safe_root + 子代理窄化（`filter_tools_for_subagent`）+ read-before-edit + 验收卡
- 对应真实 15 道门里的：工具链第 1 层（项目白名单）+ 第 4 层（外部目录批准）+ 入站第 6 步（two_phase_confirm）
- 修法上线后再未出现同类越权（`path_safety` 32 个测试文件守门）

---

## D. 工程治理类

### Q10：单测覆盖多少？端到端怎么测？

**一句话**：单测 ~80%，端到端用 sim（owner 视角真实使用）。

**展开**：
- 分层 pytest gate：smoke + attach + CC harness + mypy strict
- 9 个域：gateway / tools / core / runtime / transport / ops / hooks / memory / io
- 676+ tests passed（`323862e` 验证）
- sim：一次性，每次重写，模拟 Owner 真实使用

### Q11：怎么发版？

**一句话**：分层 gate 守门（不是裸跑全量 pytest）。

**展开**：
- `./scripts/butler-pytest-fast-gate.sh`：smoke + attach + CC harness + mypy strict
- `./scripts/butler-five-reports-gate.sh`：五报告 P5-P10
- `bash scripts/p3j-env-hygiene-gate.sh`：env 卫生
- mypy strict 826 主模块

### Q12：怎么评估 LLM 输出质量？

**一句话**：人审 + 业务指标，不追求 LLM-as-Judge 全自动。

**展开**：
- 不用 LLM 评 LLM：循环依赖 + 维度难定义 + 模型升级失效
- 用 Owner 验收卡 + runtime metrics + Recall@3 + jobs 完成率
- 评估的价值在"暴露盲区"，不在"分数"

---

## E. 产品决策类

### Q13：为什么不做多租户 SaaS？

**一句话**：明确不在产品边界。理由是单租户自托管 + 远程微信的场景足够大，不需要 SaaS 化。

**展开**（来自产品边界决策）：
- ❌ 不做全量 MCP Host / 市场
- ❌ 不做 IDE 子进程替代 Loop
- ❌ 不做多租户 SaaS
- ❌ 不用 LangGraph 替换自建 Loop
- ❌ 不做浏览器自动化默认路径

### Q14：如果重来一次，你会怎么做？

**一句话**：砍掉 60% 的 `memory/` 模块抽象，先做 P0（消息链路 + 记忆三层 + delegate），后做 P2（多 scope 召回）。

**展开**：
- 过度分层：`chunking` / `semantic_index` / `observation` / `triplet` 等可合并
- 设计不足：可观测性 dashboard、跨项目索引
- 重构优先级：P0 先做 / P1 再做 / P2 后做 / 砍 academic-style

### Q15：怎么看 Agent 的未来？

**一句话**：当前 LLM 能力上限 ≈ 高级模式匹配 + 短程规划 + 工具调用。真正的"长程规划 + 创造性问题求解"还不够稳健。

**展开**（认知颠覆）：
- 没有真正的"长程规划"：在我项目里前几步准确，多步后开始漂移（具体几步步数不好量化）
- 没有真正的"协作涌现"：子代理之间更像接力，不是涌现
- 真正突破需要"工作记忆 + 长期记忆 + 元认知"工程化

**⚠ 注意**：不要用绝对数字（如"还差 N 个量级"），那是没有依据的玄学；说"还不够稳健"+"我的项目里没观察到"更经得起追问。

---

## ⚠ 待你校对

- [ ] Q5 实际 Recall@3 数字
- [x] Q9 "30 次拦截"已改为"上线后未复发 + 32 个测试覆盖"（不可证数据替换为可证结构）
- [ ] Q12 是否有"评估本身缺陷"的更尖锐例子
- [ ] Q14 "砍 60%" 数字是否准确

---

## 附录：高频追问的"反问句"

如果被问到不确定的问题，可以反问澄清：

- "这个问题我能从两个角度回答，您是想听架构层面还是实现层面？"
- "我理解您问的是 X，不知道我理解对不对？"
- "这个我没有实测数据，但我可以从设计意图讲——可以吗？"
- "我可以现场画一下这个架构图，30 秒——可以吗？"