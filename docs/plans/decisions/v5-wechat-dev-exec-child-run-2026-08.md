# ADR：微信 Dev 执行模型 — 方案 B（Child Run + MiniMax Exec）

> **状态**：Accepted（2026-08-26）  
> **决策者**：Owner  
> **范围**：Butler v5 微信入站 · dev_task / dev_session / continue_dev 的执行路径  
> **关联**：[`butler-v5/DESIGN.md`](../../../butler-v5/DESIGN.md) §6 · [`v5-production-architecture-2026-08.md`](../../architecture/v5-production-architecture-2026-08.md) · [`v5-wechat-product-test-harness-2026-08.md`](v5-wechat-product-test-harness-2026-08.md)

---

## 1. 背景

微信产品诉求：

1. 用户发**开放式短句**，不必指定 `write_file` / `run_command`；
2. **规划/对话**用 DeepSeek Flash 类模型，**开发执行**用 MiniMax M3；
3. 长期对话 + 开发，并有**质量门禁**。

`DESIGN.md` 已定：模型调用走 **Model Port**（规划），副作用走 **Capability + Policy**；Child Run 是普通 Run，不是第二套状态机。

当前实现与目标存在**架构漂移**：为修体验债，dev 模式曾默认 **主 Loop 直调 exec 工具（plan 模型）**，与「开发用 MiniMax」不一致。

---

## 2. 决策

**Dev 执行任务走方案 B：Plan Loop 委派 → Child Run（Exec 模型 + exec 工具面）**

```text
用户消息 (WeChat)
  → Intake：Intent + ToolSurface(plan)
  → Plan Run（DeepSeek / MODEL_PLAN）
       Decision: Delegate(role=developer, task, capabilities=[write_file, run_command, …])
  → Child Run 入队（outbox / subagent worker）
  → Exec Loop（MiniMax / MODEL_EXEC）+ ScopedGrant（Dev Session / delegation grants）
  → 工具：write_file / run_command / read_file …
  → Dev Quality Gate（子代理完成后）
  → Run Notify → 微信推送【开发验收】
  → Plan Run 同步回复：已委派 + 任务摘要（不阻塞等 exec 完成）
```

**明确不做（本 ADR 否决）**

- **方案 A**（dev_task 另起独立 Exec Run 与 Plan Run 并列）— 过重，与现有 subagent worker 重复；
- **方案 C**（单 Run 内按 iteration 切换 Model Port）— Decoder/审计/Grant 边界复杂，违反「Run 有界、角色清晰」。

---

## 3. 模型角色矩阵（SSOT）

| 阶段 | ModelRole | 默认模型 env | 职责 |
|------|-----------|--------------|------|
| Intake 分类 | `intake` | `BUTLER_V5_MODEL_INTAKE` → DeepSeek | 意图：chat / dev_task / switch / … |
| 主 Loop（plan） | `plan` | `BUTLER_V5_MODEL_PLAN` → DeepSeek | 对话、只读工具、**发起 Delegate** |
| Child Run（exec） | `exec` | `BUTLER_V5_MODEL_EXEC` → MiniMax M3 | 写文件、跑命令、多轮 tool loop |
| 审批 resume | `plan` | 同 plan | 确认后恢复 Plan Run（不切换到 exec） |

**规则**

- Plan Run **不**向 LLM 暴露 `write_file` / `run_command`（dev_task 时工具面 = plan + `delegate_to_subagent`）；
- Exec 工具**仅**在 Child Run 内、经 Grant + Policy 执行；
- MiniMax 缺 key 时 exec **fallback 到 plan**（降级行为，须在 trace 标注 `exec-fallback:plan`）。

**DeepSeek V4 Flash**：API model id 以 `butler-v5/.env.example` + 本 ADR 附录为准；不得硬编码别名 `deepseek-chat` 为「正式版 Flash」而不文档化。

---

## 4. Intake 输出契约（Execution 只消费此结构）

```typescript
// 概念契约（实现可位于 packages/domain 或 runtime intake 包）
type WechatIntakeResult = {
  intent: "chat" | "dev_task" | "dev_session" | "switch_project" | "continue_dev"
  source: "rules" | "llm"
  toolSurface: "plan" | "plan+delegate"   // dev_* → plan+delegate；chat → plan
  modelRole: "plan"                       // 主 Run 始终 plan
  execVia: "none" | "child_run"           // dev_task / continue_dev → child_run
}
```

**Intake 规则优先级**（与 [`v5-wechat-product-test-harness-2026-08.md`](v5-wechat-product-test-harness-2026-08.md) 语料一致）

1. 规则命中非 chat → **锁定**，LLM 不可降级；
2. `dev_session` / `switch_project` → 短路回复，不进 Plan Loop；
3. `dev_task` → Plan Loop + delegate 面，**禁止**主 Loop 直调 exec 工具。

---

## 5. Dev Session · Grant · 质量门禁

| 项 | 行为 |
|----|------|
| Dev Session | 「开发模式」签发 subject 级 Grant；Child Run 通过 `delegation-grants` 继承 |
| 同步回复 | Plan Run 返回「已委派」+ `childRunId`；**不** inline 跑全量 verify |
| 质量门禁 | `enrichSubagentDevReply`：exec 完成后 async verify + `【开发验收】` |
| 推送 | `RUN_NOTIFY` → iLink；loopback 用 mock outbox + audit |
| ProjectState | 验收结果写入 `lastVerify*`；`/状态` 只读展示 |

---

## 6. 与当前实现的差距（迁移，非本 ADR 立即改代码）

| 现状（2026-08-26） | 目标（方案 B） |
|--------------------|----------------|
| `BUTLER_V5_DEV_PREFER_DELEGATE=0` 隐藏 delegate，主 Loop 直调 write/run | dev_task 时 **仅** delegate |
| Plan 模型执行 write_file | write_file 只在 Child Run |
| `smoke:prod-tune` 断言 `write_file@` 主 Loop trace | 断言 `delegate_to_subagent@` + audit/outbox + 落盘 |

**迁移顺序**（实现阶段须遵守，避免再次架构漂移）

1. **测试先行**：T1 语料 + T2 mock 轨迹（见 test harness ADR）覆盖方案 B 契约；
2. 调整 `resolveToolNamesForMode`：dev_task → plan 面，含 delegate，**不含** exec 工具；
3. 调整 `wechat-inbound-llm` prompt：dev 任务 **必须** Delegate，禁止 CallTool exec；
4. 默认 `BUTLER_V5_DEV_PREFER_DELEGATE=1` 或**删除该 flag**（行为固定为 B）；
5. 更新 `smoke:prod-tune` / architecture 文档；
6. 真机仅 T5 ping / 推送抽测。

---

## 7. 开放短句与推理

- **推理/规划**：Plan 模型（DeepSeek）在 Intake 后负责理解任务、拆步骤、写 `Delegate.task` 自然语言规格；
- **执行**：Child Run（MiniMax）负责 tool loop，**不要求**用户说工具名；
- **Intake LLM**：辅助模糊句；规则锁定后不可降级（已采纳）。

---

## 8. 验收标准（实现完成时）

- [x] dev_task 语料 100%：`execVia=child_run`，主 Loop trace 无 `write_file@` / `run_command@`
- [x] Child Run trace 含 exec 工具调用；worker 使用 MiniMax（或标注 `exec-fallback:plan`）
- [x] 异步 verify + notify/mock outbox 可在 CI T3 验证（`wechat-dev-delegate.test.ts` + `smoke-wechat-product-contract.mjs`）
- [x] `pnpm test` + `smoke:regression:quick` 绿；live LLM 仅 nightly（T4 `smoke:prod-tune`）

---

## 9. 附录：env 参考（目标态）

```bash
BUTLER_V5_MODEL_PLAN=deepseek-v4-flash          # V4 Flash stable id (replaces deepseek-chat)
BUTLER_V5_MODEL_INTAKE=deepseek-v4-flash
BUTLER_V5_DEEPSEEK_THINKING=disabled            # V4 default; adapter sends thinking.type=disabled
BUTLER_V5_MODEL_EXEC=MiniMax-M3
BUTLER_V5_INTAKE_ENABLED=1
BUTLER_V5_INTAKE_LLM=1
# BUTLER_V5_DEV_PREFER_DELEGATE — 迁移后删除或固定为 1
BUTLER_V5_DEV_VERIFY_ENABLED=1
BUTLER_V5_DEV_VERIFY_CMD=["pnpm","exec","vitest","run","apps/api/src/dev-quality-gate.test.ts"]
BUTLER_V5_DEV_VERIFY_INLINE=0
BUTLER_V5_SUBAGENT_ENABLED=1
BUTLER_V5_RUN_NOTIFY_ENABLED=1
```
