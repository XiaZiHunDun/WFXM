# ADR：微信产品自动化测试分层（T0–T5）

> **状态**：Accepted（2026-08-26）  
> **范围**：开放式短句、dev 委派、异步验收 — **不依赖人工真机**  
> **关联**：[`v5-verification-strategy-2026-08.md`](../active/v5-verification-strategy-2026-08.md) · [`v5-wechat-dev-exec-child-run-2026-08.md`](v5-wechat-dev-exec-child-run-2026-08.md) · v4 [`agent-testing-strategy-2026-06.md`](agent-testing-strategy-2026-06.md)

---

## 1. 问题

1. **轨迹集测试**（mock LLM 固定响应）覆盖不足，未绑定 Intake 路由与方案 B 全链；
2. **开放式对话测试**绑 live gateway + live LLM（如 `smoke:prod-tune`），**非确定、不宜进 PR 门禁**；
3. 异步路径（子代理、dev verify、notify）缺少与 `smoke-wechat-notify-acceptance` 同级的**统一 harness**；
4. 真机被误用于功能回归；应仅用于 **Channel 连通（T5）**。

---

## 2. 原则

| # | 原则 |
|---|------|
| P1 | **不断言 LLM 措辞**；断言 intent、toolSurface、trace 前缀、文件契约、ProjectState |
| P2 | **PR 门禁零外部 LLM**（T0–T3） |
| P3 | **Golden 语料**与 **mock 轨迹**分离：语料测 Intake，轨迹测 Execution |
| P4 | 真机 / live LLM = **T4/T5**，失败记趋势，不阻塞合并 |
| P5 | 方案 B 为 dev 契约 SSOT；测试与 [`v5-wechat-dev-exec-child-run-2026-08.md`](v5-wechat-dev-exec-child-run-2026-08.md) 同步 |

---

## 3. 分层（T0–T5）

```text
T0  纯函数         vitest，无 IO
T1  Golden 语料    intake-corpus → intent + locked
T2  Mock 轨迹      vitest + pglite + makeMockAdapter
T3  Loopback 集成  gateway + LLM fixture 注入（无外部 API）
T4  Live 金丝雀    nightly / 手动；smoke:prod-tune 降级到此
T5  Channel        smoke:ilink + 真机 1 条 ping
```

与现有金字塔映射：

| 新层 | 现有 |
|------|------|
| T0–T2 | L0 `pnpm test` 子集 |
| T3 | L1 loopback（应 stub LLM） |
| T4 | 原 L1 部分 live smoke |
| T5 | L3/L4 iLink / 真机 |

---

## 4. T0 — 纯函数

**路径**：`packages/runtime/src/decision.ts`、`apps/api/src/wechat-intake*.ts`、`wechat-tool-profile.ts`、`dev-quality-gate.ts`

**断言示例**：

- `classifyWechatIntent("ping").kind === "chat"`
- `shouldSkipIntakeLlm({ kind: "dev_task" }) === true`
- `resolveToolNamesForMode({ includeExecTools:false, devTask:true })` 含 delegate、不含 write_file（**方案 B 目标态**）

---

## 5. T1 — Golden 语料

**文件 SSOT**：[`butler-v5/config/wechat-intake-corpus.json`](../../../butler-v5/config/wechat-intake-corpus.json)

**条目 schema**：

```json
{
  "utterance": "帮我改一下登录逻辑",
  "expect": {
    "intent": "dev_task",
    "locked": true,
    "toolSurface": "plan+delegate",
    "execVia": "child_run"
  }
}
```

**运行**：vitest 加载 corpus，对每条调用 `classifyWechatIntent` + `classifyWechatIntentWithLlm`（LLM **mock 返回 chat** 时仍须保持 rules 锁定）。

**覆盖类别**：

- chat 短句（ping、几点、模糊进度问句）
- dev 自然句（帮我写/改/实现…）
- switch NL（切到 WFXM）
- dev_session
- 边界：含 `write_file` 字面 → dev_task locked

---

## 6. T2 — Mock 轨迹（方案 B 主链）

**场景 ID**：`wechat-dev-delegate-v1`

| 步 | Mock LLM（Plan） | 断言 |
|----|------------------|------|
| 1 | `Delegate(developer, task, …)` | trace `delegate_to_subagent@0` |
| 2 | — | outbox/audit 有 childRunId |
| 3 | Mock LLM（Exec）`CallTool(write_file)` | 文件契约 |
| 4 | — | `enrichSubagentDevReply` trace；verify scheduled |

**手段**：扩展 `wechat-inbound-butler.test.ts` 模式；subagent worker 用 inject exec adapter。

**禁止**：在本层启动真实 `pnpm test` verify（mock `runDevVerify`）。

---

## 7. T3 — Loopback + LLM Fixture

**目标**：替代当前 live `smoke:prod-tune` 作为 **CI 可跑**集成测。

**机制（设计，待实现）**：

- 环境 `BUTLER_V5_LLM_FIXTURE_DIR=config/llm-fixtures/wechat/` 或 test-only wiring；
- Gateway 测试模式：`pickLLMForRole` 读 fixture 而非 HTTP；
- 断言 HTTP inbound 响应 trace + mock notify outbox + project-state。

**脚本**：`smoke-wechat-product-contract.mjs`（新），入 `smoke:regression:quick`。

---

## 8. T4 — Live 金丝雀

保留：

- `pnpm smoke:prod-tune`（live LLM，**不进 CI**）
- 可选 nightly workflow

**记录**：trace 样本归档，供 Intake 语料扩充，**不**作为 merge 硬门槛。

---

## 9. T5 — Channel

不变：[`v5-verification-strategy-2026-08.md`](../active/v5-verification-strategy-2026-08.md) L3/L4。

---

## 10. 异步验收 harness（T2/T3 共用）

```text
1. BUTLER_V5_RUN_NOTIFY_MOCK_OUTBOX=/tmp/butler-v5-test-notify.jsonl
2. inbound dev_task → 立即断言 sync reply 含「已委派」
3. poll subagent audit / outbox（≤120s，与 notify-acceptance 相同）
4. 断言 outbox 含【开发验收】或 project-state lastVerifyOk
5. 可选：断言文件落盘
```

**禁止**依赖人工刷新微信。

---

## 11. 实施 backlog（设计已冻结，编码按序）

| 序 | 项 | 层 |
|----|-----|-----|
| 1 | `wechat-intake-corpus.json` + T1 vitest | T1 |
| 2 | 方案 B mock 轨迹 `wechat-dev-delegate-v1` | T2 |
| 3 | LLM fixture 注入 + `smoke-wechat-product-contract.mjs` | T3 ✅ |
| 4 | 产品代码迁移至方案 B（见 dev-exec ADR §6） | 实现 ✅ |
| 5 | `smoke:prod-tune` 文档降级 T4 | 文档 ✅ |
| 6 | architecture + `.env.example` 同步 | 文档 ✅ |

---

## 12. 完成定义

- PR 合并仅依赖 T0–T3 绿；
- 开放式 dev 短句在 T1+T2 有覆盖，**零真机**；
- 方案 B 与测试契约一致，无「主 Loop write_file@」回归用例（除非显式 marked legacy）。
