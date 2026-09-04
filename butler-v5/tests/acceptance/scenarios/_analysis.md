# Acceptance Realistic Scenarios — 人工分析

> 配套：`_analyze.md`（自动跑出每场景 reply 抓取 + 工具/审批统计）；本文是 judgment 层。
> 生成：2026-09-04 | 35 场景 / 35 通过 / 2.35s / 13 次 approval / 33 次 tool call / 5179 字符 reply
> 方法：每场景手工编码"好 bot" fixture（不是真 LLM），跑出 v5 wrap-around 行为

---

## A. v5 wrap-around **强**的地方（5 项）

1. **A4 / B1-B10（探索性 + 反思）**：bot 知道"自己的局限"——B8 诚实承认"我没有使用率埋点"，B1 列出"未量化 / 未 owner 实测 / 无埋点"3 类 gap。这种 honesty 是产品向 owner 负责的关键能力。
2. **A10（建议而非动手）**：owner 问"加 unit test"，bot 先 read 已有 test，发现 line 271 + 448 已有 conflict 测试，**反问要补哪条**——而不是直接动手写。这是"理解请求 + 最小动作"原则的体现。
3. **A1 / A4 / B3（结构化 reply）**：表格 / 列表 / 缩进的密度合适，WeChat 手机屏可读性好。
4. **D1-D5（多 turn + 工具链 + 审批串联）**：写 → 跑 → 失败 → 修 → 再跑的链路在 harness 里走通，approval 双向 + resume + context 保留都正常。
5. **A2 / A5 / A6（多工具 + 审批触发）**：read → write → approval → resume 的 3 步在 30s 内完成，latency 体感可接受。

---

## B. v5 wrap-around **有真 gap** 的地方（按严重度）

### 🔴 P0 — C1 / C3：**approval intent 覆盖不全**

| 输入 | 实际 reply | 期望 |
|---|---|---|
| `y` | `[fixture exhausted: plan#0]`（被当普通问题，跑 LLM）| `当前对话没有待审批的操作。` |
| `好的` | `当前对话没有待审批的操作。` ✓ | 同左 |
| `👌` | `[fixture exhausted: plan#0]` | 同左 |

**根因**：`parseInlineApprovalIntent` 只识别 `确认` / `拒绝` 文本，不识别 `y` / `n` / `👌` / `ok` / emoji / 中英混合。

**owner 真撞场景**：bot 刚问"确认？"，owner 手快回个 `y` 或 👌（最自然的确认姿势），bot 反过来问"fixture exhausted"——**完全没听懂**。第一印象崩坏。

**修**：`apps/api/src/wechat-inline-approval.ts` 的 `parseInlineApprovalIntent` 加 case：
- `y` / `Y` / `yes` → approve
- `n` / `N` / `no` → deny
- 👌 / ✅ / 👍 → approve
- ❌ / 👎 → deny

测试文件已有 `tests/.../inline-approval-intent.test.ts` — 加 4-6 个新 case 即可。

### 🟠 P1 — A3 / A7 / A8 / A9：**read-only run_command 也走 approval**

`pnpm test` / `git log` / `git diff` / `pnpm typecheck` 都是只读 / 无副作用命令，但 v5 policy-gate 一律要求 approval。35 场景里 **13 次 approval，其中 4 次是只读命令**。

**owner 真撞场景**：owner 一天问 20 次"git log" / "跑 test" / "show diff"，每次都"确认" — 摩擦感极大。会养成"确认 = 无脑点"的肌肉记忆，**反而降低对真危险操作的警觉**（羊群效应）。

**修选项**：
- A: 扩 `ALLOWED_RUN_COMMANDS` 白名单 + 加 `readOnlyCommands` 集合（git log/diff/status/ls/cat/pnpm typecheck/pnpm test 走 read-only 路径，跳 policy）
- B: 加 `policy-gate.ts` 分支，read-only command（无写入副作用）→ 直接执行
- C: 设一个"低风险 trust 模式"（owner 显式 trust 后低风险免审批）

A 最简单；B 更通用；C 风险与便利平衡最好。

### 🟠 P1 — B8：**没有使用率埋点（自我承认）**

B8 是诚实的：
> "（诚实回答）我没有使用率埋点，所以无法直接告诉你哪些真没用。"

但 owner 撞 1 次就知道 v5 是**自反能力差**。加埋点是 P1（owner 真撞前提前 1 步做掉）。

**修**：每个 capability 调用（`/记住`、`/确认`、read_file、write_file、run_command、recall）埋一行 audit。owner 问"哪些我用过" → bot 跑 SQL 聚合。

### 🟡 P2 — C9：**"撤销" 是个空承诺**

bot 答"撤销哪个操作？请说具体文件名。" 但 v5 **没有 undo 机制**。owner 真说"撤销刚才的 foo.ts 改"，bot 也无法回滚。

**修**：在 tool 副作用前 commit git snapshot（轻量）；undo 路径用 `git checkout` 还原。或明示"暂不支持撤销，请手动 git diff + checkout"。

### 🟡 P2 — C4：**长消息抗 spam 弱**

200x "请帮我" + "看一下" = bot 真的去 read 文档，**没识别这是 spam / 灌水 / 试探**。owner 1 次"刷屏"测试就能撞到。

**修**：检测 (a) 重复 token > N 次 (b) 长度 > X 字符 (c) emoji 占比 > Y — 任一命中回"请说具体需求"，不浪费 LLM call。

### 🟢 P3 — B10 / D5：开放式回复有时太"教科书"

B10 "1 周 focus" 给出 5 条建议，结构清晰但**没结合 owner 当前上下文**（不知道 owner 实际撞过什么、关心什么）。D5 "它安全吗" 走 capability check 但**没引用具体 capability 风险**（只说"安全/risk/capability"）。

**修**：把 owner 上下文（历史 ask、撞过的坑）注入 system prompt，让开放回复"个性化"。低 ROI，可作 §18 延后项。

---

## C. 结构性观察

- **37% 场景触发 approval**（13/35）— 高频。owner 习惯后会"无脑确认"，削弱了审批的安全价值（见 P1-2）
- **B 类（10 开放性）0 工具 0 审批** — bot 完全靠 LLM 文本，**真实 LLM 质量没量化**（这正是验收基建要补的）
- **C1 / C2 / C3 暴露 inline-approval 覆盖度** — fixture harness 第一次扫就抓到真 bug
- **D1-D5 多 turn context 保留** — 跑通，没有 context 丢失问题

---

## D. 推荐优先级（按 ROI）

1. **🔴 修 C1/C3**（inline-approval intent 扩 emoji/y/n）— 30 min，4-6 个测试，owner 第一眼崩坏点
2. **🟠 修 P1-2**（read-only run_command 免审批）— 2-3h，需 policy-gate 分支设计，影响面中等
3. **🟠 修 P1-3**（使用率埋点）— 1-2h，audit 表加 1-2 字段，bot 跑 SQL 聚合
4. **🟡 修 P2-4 / P2-5**（撤销 + 长消息检测）— 各 1h，独立
5. **真实 LLM 质量回放**（即 acceptance harness 用真模型跑一遍，录音作 fixture 源）— 半天，需要 secrets

不主动启动，等你选 1-N。
