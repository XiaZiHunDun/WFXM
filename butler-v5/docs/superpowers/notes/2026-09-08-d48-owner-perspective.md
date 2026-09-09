# D48 — Owner 视角笔记（观察性，不依赖 LLM eval）

> 视角：站在 owner 立场，从 7 轮 recordings baseline + 35 场景分析 + D44/D46 commit 链路 + v8 PRD REVERT 实证中，抽出"owner 真实撞过 / 已知没撞 / 没识别但结构性 / 撞出的产品力"4 类观察。
>
> 性质：纯观察性，不含修复建议。下批入口按 [deferred-trigger-conditions](../../../../.claude/projects/-home-ailearn-projects-WFXM/memory/project-deferred-trigger-conditions-2026-09-01.md) 协议等真实 owner 撞点。

---

## 0. 视角与证据源

| 证据 | 路径 | 用途 |
|---|---|---|
| recordings v7-current (35 真实 LLM 录音) | `tests/acceptance/scenarios/recordings/` | owner 真撞的输入与系统反应 (model=MiniMax-M3[1m]) |
| recordings-archive (7 baseline 演化) | `tests/acceptance/scenarios/recordings-archive/` | v1-pre-context-fix → v7-current 7 轮 fix 实证 |
| 35 场景人工分析 | `tests/acceptance/scenarios/_analysis.md` | judgment 层 gap 分类（P0/P1/P2/P3） |
| 35 场景 fixture 定义 | `tests/acceptance/scenarios/_fixtures.ts` | owner 视角输入 + v5 wrap-around 反应 |
| D46 P2 batch spec/plan | `docs/superpowers/specs/2026-09-08-v5-p2-batch-design.md` + `plans/2026-09-08-v5-p2-batch.md` | owner 真撞痛点 ④+⑤ 的承诺 |
| D44 product-layer-followups commit chain | `854c16ee..6b40d69d` | owner 真撞痛点 ①+②+③ 的实现 |
| v8 PRD 3/3 REVERT 实证 | `plans/v5-real-llm-v8-iteration-2026-09.md` | temperature model 单 round 验证不可靠 |

**Owner 视角定义**：owner = v5 唯一真实用户（非 owner 不是目标用户）。从 owner 一周真实对话录音 + 35 场景产品层行为分析中推断"owner 关心什么 / 真撞了什么 / 没识别什么"。

---

## 1. Owner 真撞过的 5 项痛点（已 ship）

按 owner 撞到 → 修了的顺序：

### ① P0 inline-approval 第一眼崩坏（owner 撞 1 次就崩）

- **撞点**：bot 刚问"确认？"，owner 手快回 `y` / `👌`（最自然的确认姿势），bot 反过来答 `[fixture exhausted: plan#0]`——**完全没听懂**。
- **来源**：C1 (`y`) / C3 (`👌`) 探针场景。
- **owner 视角**：第一眼崩坏。后续所有对话都伴随"这 bot 是不是不太灵"的疑虑。
- **修**：[D44 `69dc924c`](https://github.com/.../commit/69dc924c) `parseInlineApprovalIntent` 扩 `y/n/yes/no/👌/✅/👍/❌/👎`。[D44 `854c16ee`](https://github.com/.../commit/854c16ee) 加 6 个 lock test。

### ② P1-A read-only approval 高频摩擦（owner 一天撞 20 次）

- **撞点**：`git log` / `git diff` / `pnpm test` / `pnpm typecheck` 都是只读无副作用命令，但 v5 policy-gate 一律要求 approval。35 场景 13 次 approval，4 次是只读命令。owner 真用一天撞 20 次。
- **owner 视角**：高频摩擦会养成"确认 = 无脑点"的肌肉记忆，**反而降低对真危险操作的警觉**（羊群效应）。
- **修**：[D44 `88158080`](https://github.com/.../commit/88158080) argv 运行时分类器 + `ALWAYS_READONLY` 集合。[D44 `53cc595b`](https://github.com/.../commit/53cc595b) revert + fix 验收回归。

### ③ P1-B 使用率埋点缺失（bot 自承认）

- **撞点**：owner 撞过几次后会问"这 bot 哪些能力我常用 / 哪些 dead"，bot 答"我没有使用率埋点"（B8 场景）。
- **owner 视角**：自反能力差。一个不懂自己使用率的 bot，owner 无法判断它的价值。
- **修**：[D44 `6b40d69d`](https://github.com/.../commit/6b40d69d) `/v1/owner/usage` aggregate llm + capability counts。

### ④ P2 撤销空承诺（中文 NL 撞了才知没接住）

- **撞点**：owner 用中文 "撤销刚才" / "撤销上一步"，bot 答"好的已撤销"（LLM 路径空承诺）。`/undo` 无 path 盲目 pop workspaceRoot 永远返 "无 ... 的撤销记录"。
- **owner 视角**：最坏承诺——bot 嘴上说撤了，文件没动。owner 下次完全不信 bot。
- **修**：[D46 `8140a343`](https://github.com/.../commit/8140a343) `tryWechatUndoCommand` regex longest-first + 区分 explicit slash vs 中文 NL + `popMostRecentWrite` 跨 path 智能撤销。[D46 `eaaea84b`](https://github.com/.../commit/eaaea84b) F2 lock test。

### ⑤ P2 长消息 spam 漏检（owner 试探撞 1 次）

- **撞点**：200x "请帮我" + "看一下 README" = bot 真去 read 文档，**没识别 spam / 灌水 / 试探**。
- **owner 视角**：bot 替我做事的成本远高于直接拒绝一次"请发具体需求"。
- **修**：[D46 `a8e636a3`](https://github.com/.../commit/a8e636a3) `detectSpam` 加 3 flag（per-line 重复 / whitespace-token 重复 / length+structure 1500-2000 合法中文）。[D46 `3df98ccc`](https://github.com/.../commit/3df98ccc) C9 fixture drift + `resetUndoStack` 隔离。

**5 项 owner 痛点闭环 = D44 (①②③) + D46 (④⑤) = 6 commit + 8 mock harness case lock + 35/35 realistic 套件验证。**

---

## 2. Owner 已知没撞但 bot 自承认的 1 项（§18 延后）

### P3 开放回复教科书化（B10 / D5）

- **观察**：B10 "1 周 focus" 给出 5 条结构化建议，但**没结合 owner 当前上下文**（不知道 owner 实际撞过什么、关心什么）。D5 "它安全吗" 走 capability check 但**没引用具体 capability 风险**（只说 "安全/risk/capability"）。
- **owner 视角**：开放回复"通用化"是信任源缓慢衰减的原因——每次都答得像模板，owner 不再认真读。
- **当前承认**：§18 row 3 延后项 / §11 row 5 MVP ship。修选项 = owner 上下文（历史 ask、撞过的坑、偏好）注入 system prompt。低 ROI，因为 (a) 上下文收集机制不成熟 (b) 注入反而干扰 LLM。

---

## 3. Owner 没识别但结构性问题 3 项（gap，未承认）

这 3 项 owner 还没撞到，但**结构上存在于 v5 wrap-around 设计中**。不是 bug，但 owner 视角下是真实 UX 摩擦或限制。

### 3.1 approval 羊群效应（设计权衡，残余摩擦）

- **现象**：D44 修后 read-only 4 次 bypass approval。35 场景剩 9 次非 read-only approval 仍走 `WaitForApproval`。
- **owner 视角**：高频触发"确认"按钮会养肌肉记忆。owner 一周撞 50 次后，对真危险操作（删文件 / 改生产配置）的警觉度下降。
- **结构根因**：policy-gate 没有"trust 模式"——一旦信任建立，所有低风险命令免审批；当前实现是"per-command 静态判定"。
- **当前状态**：decline (2026-09-09 D51，详见 `docs/superpowers/notes/2026-09-09-d51-decline-gaps.md`)。修选项 §18 没列入且不再评估。
- **触发条件**：owner 撞 1 次"我刚误点了一个 delete"。

### 3.2 真实 LLM 质量量化不可达（方法论限制）

- **现象**：B 类 10 场景 0 工具 0 审批，纯 LLM 文本。35 scenario fixture 是手工"好 bot"行为，**不是真 LLM**。`recordings/` 是真 LLM 录音但没量化手段。
- **实证**：v8 PRD candidate A/B/C 全部 REVERT（3/3 REVERT），原因 = temperature model 单 round 验证不可靠——35 场景单一 snapshot 不能区分 fix vs model variance。
- **owner 视角**：owner 真撞"bot 答案质量差"目前无改进路径。`pnpm diff:real-llm` 能跑 aggregate 对比，但 fix 候选 C (D47 fixture-recording) 同源风险。
- **结构根因**：LLM 输出是概率性的，单 round snapshot 不构成稳定 baseline；多 round + prompt freeze 才能稳定 baseline，但成本 4 min × N round。
- **当前状态**：decline (2026-09-09 D51，详见 handoff doc `docs/superpowers/notes/2026-09-09-d51-decline-gaps.md`)。方法论限制确认 + v8 3/3 REVERT 同源风险未解除前不启。
- **触发条件**：owner 实测 1 周后明确指出"B 类某场景答错了"。

### 3.3 multi-tool chain 撤销未覆盖（边界 gap）

- **现象**：D46 F1+F2 覆盖单 tool 写撤销（`popMostRecentWrite` + `resetUndoStack`）。D1 场景"写 → 跑 test → 失败 → 修 → 再跑"是 5 步链，撤销仅覆盖第 1 步写。
- **owner 视角**：35 场景没出现"撤销多步"，但撞到会很惨——5 步链中间某步出错，owner 想回到第 1 步前的状态，bot 答"已撤销第 1 步的 helper.ts"，但中间 4 步的副作用还在。
- **结构根因**：当前 `UNDO_STACK` 只 track `write_file`，不 track `run_command` / `apply_patch` / 多 write 组合。
- **当前状态**：未识别为 gap。35 场景没暴露是因为 owner 没真撞。
- **触发条件**：owner 实测 1 周后撞 1 次"撤销刚才那 5 步"。

---

## 4. Owner 撞出的产品力（不是 bug，是真价值）

这 3 项是 owner 视角下的核心信任源。**不是修复项，是要保持 / 强化的能力**。

### 4.1 诚实承认 gap（B1 / B8 / B10）

- **观察**：B1 owner 问"v5 现在有什么问题"，bot 列"未量化 / 未 owner 实测 / 无埋点"3 类 gap。B8 撞埋点缺失时 bot 直接说"（诚实回答）我没有使用率埋点"。
- **owner 视角**：这种 honesty 是产品向 owner 负责的关键能力。比"装作能做"更值得信任。
- **保持**：system prompt 已有 `reply-style` + `take-action bias`，但"承认局限"是隐含能力。建议在 system prompt 加 1 行"不知道就说不确定"，避免 LLM 幻觉补偿。

### 4.2 结构化 reply + WeChat 手机屏可读（A1 / A4 / B3）

- **观察**：表格 / 列表 / 缩进的密度合适，单条 reply 100-200 字，不挤压不碎片。
- **owner 视角**：v5 是微信入站，reply 在 6.7 寸手机屏。结构化让 owner 不用放大就能扫读。
- **保持**：`reply-style` baseline (D5/A2/A8 mobile-friendly) 已 ship in `d3b3478a`。v7-current baseline metric 已有。

### 4.3 advice-not-action（A10）

- **观察**：owner 问"加 unit test"，bot 先 read 已有 test，发现 line 271 + 448 已有 conflict 测试，**反问要补哪条**——而不是直接动手写。
- **owner 视角**：owner 真撞时会发现 bot 不擅自扩展 scope = 信任。
- **保持**：system prompt `take-action bias` 已 ship（A2 6 → 2 toolCalls, 639 → 197 chars, latency -26%）。但要警惕"过度延伸"——只在 owner 明确说"做了"时才动；其他时候先反问。

### 4.4 多 turn context 保留（D1-D5）

- **观察**：D1 写 → 跑 → 失败 → 修 → 再跑，approval 双向 + resume + context 保留都正常。
- **owner 视角**：多 turn 是真实对话的基础，context 丢失 = 体验崩塌。当前 0 丢失。
- **保持**：acceptance harness 已锁 5 case。**不能在 product change 中无意破坏**。

---

## 5. Fixture Harness 作为 Owner 视角代理

### 5.1 方法论价值

35 realistic scenarios (`aadf23ce`) 是 owner 视角的代理，**比单元测试更接近 owner 真撞**：

- **单元测试** = "v5 内部 invariant 是否保持"（§3 / §5 / §20）
- **fixture harness** = "v5 在 owner 真实任务下的反应"（4 类 35 场景）
- **真实 LLM 录音** = "v5 在真模型下的概率分布"（35 recordings，temperature-dependent）

3 层互补。fixture harness 价值在于：**5 个 P0-P2 gap 都是第一次跑就暴露的**（inline-approval y/👌, read-only bypass, 撤销空承诺, 长 spam），不是事后回归测试。

### 5.2 fixture harness 的局限

- fixture 是手工"好 bot"行为，不是真 LLM。覆盖 = 手工覆盖面。
- 35 场景 = 当前 owner 已知任务的样本。新任务类型（如"接 Slack / Telegram / MCP 接入"）撞出的 gap 没在 35 场景里。
- fixture 不能模拟"owner 撞到产品崩溃后的反应"——这是真实 LLM 录音的价值（v7-current recordings/）。

### 5.3 owner 撞出真 bug 的概率

按 7 轮 recordings baseline 演化：
- **v1 → v2** = context injection 修 B1 类
- **v2 → v3** = reply-style 修 mobile readability
- **v3 → v4** = loop-exhausted clarification 修 D1 degradation
- **v4 → v5** = read_file-first 修 A9 over-trigger
- **v5 → v6** = firstNonFlagArg 修 A9 regression
- **v6 → v7** = bounded find + convergence prompt 修 D4 turn 2

**6 轮 fix = 6 次 owner 撞出 gap → fix → 录音对比验证**。每轮 4 分钟。**owner 实测是唯一的"无法伪造"信号源**。

---

## 6. 下批入口（按 deferred-trigger-conditions 协议）

按 §18 trigger guard + §11 row 5 + §11.4 deferred-trigger-conditions 协议：

| 触发源 | 协议 | 状态 |
|---|---|---|
| Owner 真撞 P0/P1/P2/P3 新 gap | `pnpm diff:real-llm` 跑出 aggregate 退化 → 启动 D49 | ⬜ 等触发 |
| B10/D5 owner 视角个性化撞点 | §18 row 3 (low ROI) | ⬜ 等 owner 撞 |
| multi-tool chain 撤销 (3.3) | owner 撞 1 次"撤销 5 步" | ⬜ 等触发 |
| approval 羊群效应 (3.1) | owner 撞 1 次"误点确认" | × declined (D51) |
| 真实 LLM 质量量化 (3.2) | owner 撞 1 次"答错了" | × declined (D51) |
| D47 fixture-recording | 同源风险 v8 3/3 REVERT | ⚠️ 需固化 multi-round + prompt freeze |
| D48 owner 实测 1 周笔记 | v8 candidate D (本笔记第 5 节) | ✅ 当前 |
| §18 5 项延后 | trigger guard | ⬜ 等 owner |

**当前 D48 = owner 视角观察性笔记，不修任何代码。下批按 owner 真撞顺序启动 D49+。**

---

## 7. Lessons（owner 视角的元观察）

1. **5/35 P0-P2 gap 都由 fixture harness 暴露**——这是 acceptance harness 的产品层价值，远超单元测试。下一阶段保持 35 场景不能缩。
2. **v8 PRD 3/3 REVERT 实证方法论限制**——temperature model 单 round 验证不可靠。"v8 后唯一可执行路径 = owner 手试真问题触发"。D48 笔记本身是这条路径下的产物。
3. **3 个结构性问题（approval 羊群 / LLM 质量量化 / multi-tool 撤销）没识别 = 因为 owner 没撞**——不是 v5 wrap-around 团队的盲点，是 fixture harness 样本的盲点。要么扩 fixture 覆盖，要么等 owner 实测。
4. **4 项产品力（诚实 / 结构化 / advice-not-action / 多 turn context）是 v5 的核心资产**——任何 system prompt / policy change 必须保持这 4 项不退化。`recordings-archive/` 7 轮 baseline + 未来每轮 fix 前 snapshot 是唯一防退化机制。
5. **D44 + D46 = 6 commit ship 5 项 owner 痛点**——这说明 owner 真撞痛点从 fixture harness 识别到 ship 的 cycle 是可控的（平均每痛点 1-2 commit）。下一批触发后 cycle 估计类似。

---

**End D48 owner 视角笔记。**
