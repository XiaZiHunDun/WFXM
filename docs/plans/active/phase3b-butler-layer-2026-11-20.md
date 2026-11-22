# 管家层体检与打磨方案（2026-11-20）

> **状态**：体检完成；B11–B15 已交付，B16 待确认 | **前置**：任务层地基 B1–B10 已交付
> **范围**：`packages/runtime/src/butler/*`、`apps/api` 管家装配与路由、`packages/ports` 管家契约
> **方法**：静态阅读 + 既有测试比对，只记录有代码证据的问题；不确定项标「待验证」

---

## 1. 六块现状

| 块 | 结论 | 一句话说明 |
|----|------|------------|
| A 会话与路由 | 有缺口 | 会话归属校验到位；但文本审批依赖调用方传 `activeTaskId`，不从会话推导 |
| B 记忆 | 高危 | `summarize()` 生产未调用；记忆端口与召回缓存都没有 user 维度，靠单 owner 假设兜底 |
| C 审批 | 高危 | 只校验会话归属，不校验任务归属；知道 taskId 即可跨会话批准 |
| D 任务编排 | 有缺口 | 创建/列表有项目过滤；单任务查询与审批没有项目校验 |
| E 模型工具循环 | 较稳 | 有轮数/工具额度上限、错误兜底、空回复兜底 |
| F 用户可见出口 | 较稳 | `finalizeReply` 统一收口；术语与 workspace 路径已处理 |

---

## 2. 问题清单

| ID | 严重度 | 症状 | 证据 | 现有测试 | 用户影响 |
|----|--------|------|------|----------|----------|
| B-01 | 高 | 审批回调只校验会话属于该用户，不校验任务属于该会话/项目；`approve(taskId)` 也不校验 | `butler-runtime.ts` L242–256；`pi-task-adapter.ts` L165–172 | 仅覆盖“任务不存在/不在等待审批” | 任一会话知道 taskId 就能批准别人的任务 |
| B-02 | 高 | 记忆双轨且无 user 维度：`summarize()` 仅测试调用；`recallUserMemory(query)` 无 userId；召回缓存 key 为 `limit\|query` | `butler-runtime.ts` L172–179、L572；`butler-memory.ts` L45–48；`apps/api/src/index.ts` L98–110 | 有端口级用例，无生产写入链路用例 | 长期记忆可能根本不增长；多用户复用进程会串记忆 |
| B-03 | 中 | 裸“确认/拒绝”只在调用方传入 `activeTaskId` 时命中规则，不从会话/最近任务推导 | `rule-router.ts` L67–73；`butler-runtime.ts` L137–140；`routes/butler.ts` L104、L165 | 有传入 activeTaskId 的用例 | 微信适配器漏传时，文字审批失效 |
| B-04 | 中 | `status(taskId)` 与 `task_status` 工具不校验项目归属，可查其他项目任务 | `pi-task-adapter.ts` L122–126；`butler-runtime.ts` L546–550 | 列表过滤有测试，单任务无 | 项目隔离不完整，可能暴露别项目进度 |
| B-05 | 中 | 规则路径无 try/catch：`tasks.start/approve` 抛错时 `handle` 直接 reject | `butler-runtime.ts` L142–146；对比 agent 路径 L423–433 | 无故障注入用例 | 任务层/存储故障时用户收到 500 或无回复 |
| B-06 | 中 | 重复审批、越权审批、任务不存在都返回“当前不在等待审批”，无法区分 | `pi-task-adapter.ts` L165–168；`butler-runtime.ts` L256–261 | 重复审批未覆盖 | 用户重复点击卡片时提示含糊 |
| B-07 | 低 | `/status` 不支持指定 taskId，只能依赖 activeTaskId | `rule-router.ts` L47–52 | 有用例，但仅当前任务 | 多任务时排障不便 |
| B-08 | 低 | `activeTaskId` 由 HTTP 调用方传入，未持久化到会话 | `routes/butler.ts` L104、L165；`butler-session` 契约 | 有透传用例 | 跨进程/重启后文字审批失去上下文 |

---

## 3. 建议批次（承重顺序）

| 批次 | 主题 | 功能打磨 | 关键测评点（只测外部契约） | 状态 |
|------|------|----------|---------------------------|------|
| B11 | 审批授权与归属 | 任务绑定 `conversationId`；审批前校验归属；区分“已处理/无权/不存在” | 跨会话审批被拒；重复审批幂等；跨项目任务不可见 | ✅ 已交付 |
| B12 | 任务编排与 activeTaskId | `activeTaskId` 由会话推导并持久化；`status/list` 统一项目过滤 | 不传 activeTaskId 时“确认”仍可用；跨项目查询被拒 | ✅ 已交付 |
| B13 | 规则路径韧性 | `applyRule` 统一异常兜底；任务层/存储故障给可读回复且消息落库 | 故障注入下回复非空、用户消息不丢 | ✅ 已交付 |
| B14 | 记忆单一事实源 | 明确生产写入触发点；端口与召回缓存加 user/owner 维度；记忆失败隔离 | 两个 owner 同 query 不串；记忆失败不影响主回复 | ✅ 已交付 |
| B15 | 路由可用性 | 支持 `/status <id>`；未知 id 提示；帮助文案同步 | 显式 ID 查询、未知 ID 可读提示 | ✅ 已交付 |
| B16 | 体验收口 | 审批文案、长回复分段、术语/路径回归 | 对外文案不含原始工具名/绝对路径 | 待确认 |

---

## 4. 测评原则

- 硬关键点用确定性 vitest：授权、归属、幂等、故障兜底、状态转移。
- 软体验交给开放任务 + judge：措辞、追问风格、信息取舍。
- 明确放过：规则匹配的内部正则、模型轮数、prompt 文本、trace 字段顺序。

---

## 5. 下一步

1. 确认批次顺序（建议 B11 → B12 → B13 → B14 → B15 → B16）。
2. B11 先做：它是当前唯一的“越权”级问题，且改动面小、可逆。
3. 每批交付时同步补关键点用例，并做反向验证。

---

## 6. B11 交付记录（2026-11-20）

改动：

- `ButlerTaskPort.start` 接受 `conversationId`，`ButlerTaskRef` 透出；任务创建时写入 runner 的 JSON snapshot（无数据库迁移）。
- 审批回调与规则审批都先 `status(taskId)` 校验归属：任务属于其他会话时拒绝；无归属的旧任务回退到项目范围校验。
- 三类结果可区分：`没有找到任务` / `不属于当前会话` / `当前不在等待审批（可能已处理）`。
- 规则路径的 `start_task` 与模型工具 `start_task` 都会带上当前会话 ID。

测评：

- 跨会话卡片审批被拒，且 `approve` 未被调用；
- 跨会话文字审批（`确认` + `activeTaskId`）被拒；
- 同会话审批正常执行；
- 已处理任务返回“可能已处理”，不再误报“不在等待审批”；
- 新建任务自动绑定当前会话；
- adapter 的 `start` / `status` 均透出 `conversationId`；
- 反向验证：移除归属校验，跨会话用例按预期变红。

验证结果：

| 项 | 结果 |
|----|------|
| butler + adapter 测试 | 31 passed |
| `pnpm test` | 277 文件 / 2,344 通过 / 2 skipped |
| `pnpm typecheck` / `pnpm lint` | 全绿（0 warning） |
| `scripts/audit/test-internal-assertions.mjs` | 49 internal-only（2.4%） |

---

## 7. B12 交付记录（2026-11-20）

实现取舍：没有把 `activeTaskId` 写进 `butler_sessions`（避免数据库迁移），而是从任务存储按 `conversationId` 推导；任务的会话绑定在 B11 已持久化，因此重启后仍可用。

改动：

- 裸“确认/拒绝”在未传 `activeTaskId` 时，从该会话的 `paused` 任务推导：唯一则直接审批；没有则回复“当前没有待确认的任务”；多个则提示用卡片或 `/status`。
- `PiTaskSessionStore` 增加可选 `list()`；Memory 与 Drizzle 存储实现；runner 新增 `listStored()` 合并存储与内存记录；adapter 的 `list` 改为读存储，重启后 `/tasks` 可见。
- `task_status` 规则与工具都加项目过滤：跨项目任务返回“没有找到任务”。

测评：

- 不传 `activeTaskId` 的“确认”能命中该会话唯一待审批任务；
- 多个待审批任务时提示选择，不误批；
- 无待审批任务时直接回复，不调用模型；
- 跨项目 `状态` 查询被拒；
- 新 runner 共享同一存储时仍能列出旧任务（模拟重启）；
- 反向验证：分别移除推导、项目过滤、存储列表，对应用例均按预期变红。

验证结果：

| 项 | 结果 |
|----|------|
| butler + adapter + runner 测试 | 82 passed |
| `pnpm test` | 277 文件 / 2,349 通过 / 2 skipped |
| `pnpm typecheck` / `pnpm lint` | 全绿（0 warning） |
| `scripts/audit/test-internal-assertions.mjs` | 49 internal-only（2.4%） |

---

## 8. B13 交付记录（2026-11-20）

改动：

- 规则路径统一 try/catch：`applyRule` 抛错时回复“这个操作暂时没完成，请稍后再试。”并写 `rule:error` trace，不再把异常抛给渠道层。
- 待审批推导失败：`tasks.list` 抛错时回复“暂时无法查询待确认任务，请稍后再试。”
- 审批转发失败：`tasks.status` / `tasks.approve` 抛错时分别回复“任务操作暂时失败”与“审批暂时没提交成功”。
- 新增 `safePersist`：规则、审批回调、模型循环三条出口都改用它；存储故障只记 `store:error` 与 warning，回复照常返回。

测评：

- 任务层 `start` 抛错 → 用户收到可读回复，用户消息与兜底回复都落库；
- 待审批查询抛错 → 可读回复；
- 审批转发抛错 → 可读回复；
- 会话存储 `save` 抛错 → 规则与模型两条路径仍返回原文案；
- 反向验证：移除规则兜底，任务层故障用例按预期变红；
- 同步更新装配层旧用例：未知项目从“抛错”改为“可读回复”。

验证结果：

| 项 | 结果 |
|----|------|
| butler 测试 | 31 passed |
| `pnpm test` | 277 文件 / 2,353 通过 / 2 skipped |
| `pnpm typecheck` / `pnpm lint` | 全绿（0 warning） |
| `scripts/audit/test-internal-assertions.mjs` | 49 internal-only（2.4%） |

---

## 9. B14 交付记录（2026-11-20）

改动：

- 召回端口新增可选 `userId`；`recallBlock` 把 `session.userId` 传给端口，缓存 key 改为 `userId|limit|query`，同一查询不再跨用户复用。
- 新增 `summarizeIfDue`：按 `summaryEveryMessages`（默认 20，`<= 0` 关闭）触发记忆投影，用内存计数避免每轮重复；失败只记 warning。
- 生产写入点接在 `handleButlerInbound` 的回复投递之后，fire-and-forget，不阻塞用户响应。
- 记忆投影失败仍返回摘要事件并落库，召回失败继续走既有 `safeRecall` 空结果兜底。

测评：

- 两个用户同 query 分别召回，缓存不串；同一用户重复 query 命中缓存；
- 达到消息阈值后自动投影，事件带正确 `userId`；未达阈值返回 null；投影后不重复触发；
- 记忆写入抛错时摘要仍生成、调用不 reject；
- 反向验证：移除缓存 key 中的 `userId`，跨用户用例按预期变红。

说明：生产 `agent-rag` 端口仍绑定单 owner；`userId` 是契约层的显式维度，单 owner 部署行为不变，多用户复用同一进程时不再串缓存。

验证结果：

| 项 | 结果 |
|----|------|
| butler 测试 | 34 passed |
| `pnpm test` | 277 文件 / 2,356 通过 / 2 skipped |
| `pnpm typecheck` / `pnpm lint` | 全绿（0 warning） |
| `scripts/audit/test-internal-assertions.mjs` | 49 internal-only（2.4%） |

---

## 10. B15 交付记录（2026-11-20）

改动：

- `/status` 规则支持可选任务 ID：`/status <任务ID>` 直接查指定任务，缺省仍看 `activeTaskId`；`状态/进度` 两个词保持原语义。
- 未知任务 ID 回复 `没有找到任务 <id>，可以用 /tasks 查看项目任务。`，把用户引导到可枚举入口，而不是停在死路。
- `BUTLER_HELP_TEXT` 同步为 `/status [任务ID] 查看任务，缺省看当前任务`，帮助与实际行为一致。

测评：

- `/status t2` 且 `activeTaskId = t1` 时命中 `t2`，证明显式 ID 优先；
- `/status nope` 返回可读提示，且包含 `/tasks` 引导；
- `/help` 输出包含 `/status [任务ID]`；
- 反向验证：移除显式 ID 解析后，前两条用例按预期变红。

验证结果：

| 项 | 结果 |
|----|------|
| butler-runtime 测试 | 37 passed（butler 目录 71 passed / 5 文件） |
| `pnpm test` | 277 文件 / 2,358 通过 / 2 skipped |
| `pnpm typecheck` / `pnpm lint` | 全绿（0 warning） |
| `scripts/audit/test-internal-assertions.mjs` | 49 internal-only（2.4%） |

说明：全量跑时 `packages/persistence/src/db-open.test.ts` 的 pglite 重连用例在并行负载下超 10s 失败，单独重跑 3 passed / 1 skipped，属环境负载抖动，与本次改动无关。
