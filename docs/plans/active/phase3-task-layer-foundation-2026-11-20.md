# Phase 3 — 任务层地基打磨

> **状态**：已完成（B1–B10） | **日期**：2026-11-20 | **Owner**：主公
> **上游**：[`../../PROGRESS.md`](../../PROGRESS.md) · [`phase2-test-eval-system-2026-11-19.md`](./phase2-test-eval-system-2026-11-19.md) · [`phase3-eval-system-2026-11-19.md`](./phase3-eval-system-2026-11-19.md) · [`phase2-findings-2026-11-19.md`](./phase2-findings-2026-11-19.md)
> **定位**：Phase 2 解决“测评锚点从实现细节转向外部结果”；Phase 3 解决“按地基顺序把任务层打磨到可依赖，并让测评只锁关键点”。

---

## 1. 结论：任务层的地基是什么

任务层（`PiTaskRunner` + `PiTaskSessionStore` + `pi-native-tools` + `pi-task-adapter`）的地基**不是某个模块**，而是四条必须恒成立的不变量：

| # | 不变量 | 一句话定义 | 破坏后的后果 |
|---|--------|------------|--------------|
| I1 | **确定性重建** | 同一 `snapshot + prompt + model` 能重建同一条执行路径，turn 之间无进程内隐藏状态 | 重启后行为漂移，跨进程恢复不可信 |
| I2 | **单次执行** | 每个工具调用要么恰好执行一次，要么被显式标记“未执行”，不存在静默丢弃或重复执行 | 重复写文件、重复删库、审批被绕过 |
| I3 | **边界封闭** | 路径、命令、环境变量、输出体量都限制在 workspace 与安全策略内 | 越权读写、密钥泄漏、宿主机被污染 |
| I4 | **状态可恢复** | 任一时刻中断，都能从持久化记录继续，或明确终止并说明原因 | 任务卡死、状态说谎、用户收到空回复 |

这四条不变量由三层运行时底座承载：

- **执行引擎**：`vendor/pi-agent`（循环、工具批次、abort、消息累积）
- **IO 地基**：`pi-model`（模型流/重试）+ `pi-native-tools`（fs/subprocess）
- **状态地基**：`PiTaskSessionStore`（JSON 快照）+ `GlobalAgentLock`（进程内串行）

把上面两层合起来，Phase 3 的打磨顺序就是：**先钉死不变量 → 再补齐底座缺口 → 最后把结果交回用户**。

---

## 2. 分层模型（从下往上）

| 层 | 名称 | 职责 | 主要代码 | 当前状态 |
|----|------|------|----------|----------|
| L0 | 平台 | 进程、fs、子进程、时钟、env/密钥 | Node / `config` | 可用 |
| L1 | 任务契约与状态机 | taskId+projectId+cwd 绑定；turn 纯函数；`idle/running/paused/failed/closed` 转移 | `pi-task-runner.ts` L402–537、L608–791 | 部分 |
| L2 | 转录完整性 | snapshot 是唯一真相；toolCall↔toolResult 配对；system 消息唯一；版本校验 | `pi-task-runner.ts` L210–400、`pi-task-session.ts` | 部分 |
| L3 | 工作区边界 | realpath/相对路径/符号链接；读写/输出/超时上限；env 过滤 | `pi-native-tools.ts` L37–121 | **弱** |
| L4 | 工具协议 | 7 个 pi-shaped 工具；参数校验；`isError` 语义；名称归一化仅用于报告 | `pi-native-tools.ts`、`pi-tool-name-map.ts` | 中 |
| L5 | 审批闸门 | 策略判定；`pendingStep`；同批阻断；批准/拒绝；恰好一次 | `pi-task-runner.ts` L165–190、L682–719 | 中 |
| L6 | 持久化与恢复 | store 契约；跨进程重建；`open/close/delete`；损坏快照 | `pi-task-session.ts`、`task-session-store.ts` | 中 |
| L7 | 并发与调度 | 全局 FIFO 锁；同任务互斥；detached / `idle()` | `pi-task-runner.ts` L111–147、`pi-task-adapter.ts` | 中 |
| L8 | 模型与上下文 | streamFn、重试/中止、usage；systemPrompt + repo map + memory 投影 | `pi-model.ts`、`pi-task-adapter.ts` L94–111 | 中 |
| L9 | 结果契约（任务层→管家层） | 任务结果/原因/改动/待审批必须可达上层与用户 | `butler-task.ts`、`pi-task-adapter.ts` L119–168 | **弱** |
| L10 | 端到端可见性 | 微信回复、审批文案、错误不外泄、内部术语不泄漏 | `butler-runtime.ts`、`approval-notice.ts` | 中 |

> 说明：L9/L10 严格说在任务层之上，但 L9 是任务层能力的“出口”，缺了它前面所有打磨都对用户不可见，因此纳入同一阶段。

---

## 3. 现状体检（证据优先）

| ID | 严重度 | 问题 | 证据 | 状态 |
|----|--------|------|------|------|
| F3-01 | 高 | 工作区路径边界没有任何直接单测；`resolveInsideWorkspace` 只在源码与 eval 脚本中出现 | `Grep resolveInsideWorkspace` 命中 4 文件，无 `*.test.ts` | 已修（B3） |
| F3-02 | 高 | 工具额度耗尽/批次被 block 时，`reply` 可能为空：`lastAssistantText` 只找带文本的 assistant，被 block 的原因不在回复里 | `pi-task-runner.ts` L682–689、L755–758 | 已修（B1） |
| F3-03 | 高 | 任务结果不回流管家层：adapter 丢弃 `PiTaskTurnResult.reply`，`ButlerTaskRef` 无结果字段 | `pi-task-adapter.ts` L136–143、`butler-task.ts` L18–24 | 已修（B9） |
| F3-04 | 高 | 审批恢复跨进程不幂等：`resume` 直接执行 `pendingStep`，无 once 标记；两个进程可各执行一次 | `pi-task-runner.ts` L625–669 | 已修（B5） |
| F3-05 | 中 | `pause()` 置 `paused` 但不写 `pendingStep`；后续 `resume()` 仍注入“审批已通过”提示 | `pi-task-runner.ts` L513–530、L493–511 | 已修（B1） |
| F3-06 | 中 | snapshot 只校验“是数组”，`version` 未校验；损坏/旧版本可能静默进入执行 | `pi-task-runner.ts` L214–218、`pi-task-session.ts` L25–30 | 已修（B2） |
| F3-07 | 中 | 同任务并发 `start` 的 `running` 守卫在取锁前判断，存在竞态窗口 | `pi-task-runner.ts` L483–491 | 已修（B1） |
| F3-08 | 低 | `close()` 删除 store 记录，但 adapter 从不调用 `close`；记录生命周期语义不清 | `pi-task-runner.ts` L532–537、`pi-task-adapter.ts` | 已澄清（B6）：close 为显式终止，adapter 保留会话以便恢复 |

> F3-01…F3-08 已全部闭环；每项都在对应批次补了关键点测试，并做了反向验证。

---

## 4. 打磨顺序（三个里程碑）

### M1 — 地基稳固（L1–L4）

目标：让“一次 turn”成为可重放、边界封闭的纯执行单元。

| 批次 | 内容 | 功能打磨 | 测评关键点 |
|------|------|----------|------------|
| B1 | 任务契约与状态机 | 明确合法状态转移；同任务互斥；终态幂等；失败必须有可读原因 | K1.1–K1.5 |
| B2 | 转录完整性 | snapshot 版本校验；损坏快照显式失败；补齐 dangling toolResult；空回复兜底 | K2.1–K2.5 |
| B3 | 工作区边界 | 为路径逃逸/符号链接/超限/超时补齐行为与错误语义 | K3.1–K3.5 |
| B4 | 工具协议 | 7 工具的最小契约；`isError` 不中断 run；名称归一化只影响报告 | K4.1–K4.3 |

### M2 — 可恢复与可控（L5–L7）

| 批次 | 内容 | 功能打磨 | 测评关键点 |
|------|------|----------|------------|
| B5 | 审批闸门 | 跨进程恰好一次；同批阻断；拒绝不重试；审批 TTL 语义 | K5.1–K5.5 |
| B6 | 持久化与恢复 | `open/load/close` 生命周期；save 失败语义；损坏记录可诊断 | K6.1–K6.4 |
| B7 | 并发与调度 | 同任务串行；全局锁超时/排队可观测；detached 与 `idle()` 一致 | K7.1–K7.4 |

### M3 — 可用与可信（L8–L10）

| 批次 | 内容 | 功能打磨 | 测评关键点 |
|------|------|----------|------------|
| B8 | 模型与上下文 | 重试/中止映射；usage 汇总；repo map/memory 失败不阻塞 | K8.1–K8.4 |
| B9 | 结果契约 | `ButlerTaskRef` 增加结果摘要/失败原因/改动清单；adapter 回传 turn 结果 | K9.1–K9.4 |
| B10 | 端到端可见性 | 完成/失败/待审批都能形成用户可读回复；内部术语与路径不外泄 | K10.1–K10.4 |

---

## 5. 测评用例设计原则（本阶段的硬约束）

### 5.1 只锚定三类东西

1. **外部可观察结果**：文件内容、进程退出、返回状态、用户可见文本的“可发送性”。
2. **不变量**：I1–I4 及其派生（状态转移合法、审批恰好一次、路径不逃逸）。
3. **契约边界**：端口输入/输出字段、错误分类，不锚定内部调用序列。

### 5.2 判定法则（写测试前先过一遍）

> 如果这个断言在“换模型 / 换实现 / 换工具顺序但结果正确”时会失败，它就是过拟合，必须改成结果断言或删除。

### 5.3 三类处理

| 类型 | 处理 | 例子 |
|------|------|------|
| 硬关键点 | 确定性 vitest，改坏必红 | 路径逃逸被拒、拒绝审批后文件不变、跨 runner 恢复 |
| 软能力 | 开放任务 + judge，设基线，不锁步骤 | 选哪个工具先读、写几行、回复措辞 |
| 明确放过 | 不测 | 精确轮数、精确 prompt 文本、内部锁字段、工具调用次数 |

### 5.4 现有过拟合断言（本阶段顺带收敛）

| 位置 | 现状 | 建议 |
|------|------|------|
| `pi-task-runner.test.ts` 锁测试 | 断言 `lock.activeTaskId` / `queueLength` | 改为只断言可观察的串行顺序 |
| 拒绝审批测试 | 断言 snapshot 含“用户拒绝执行该操作” | 改为断言文件未变 + 下一轮模型输入可见拒绝 |
| 跨 runner 恢复 | 断言 user 消息数为 2 | 改为断言第二轮模型请求包含第一轮上下文 |
| adapter repo map | 断言 systemPrompt 含“仓库地图” | 改为断言模型请求上下文中出现仓库路径/符号 |

> 目标不是减少覆盖，而是把断言从“实现形状”移到“行为契约”；审计脚本预算只降不升。

---

## 6. 关键点清单（按层）

### M1

| ID | 层 | 关键点 | 断言方式 |
|----|----|--------|----------|
| K1.1 | L1 | 未知 task / 非法 cwd 的 `open` 明确失败 | 抛错含可读原因 |
| K1.2 | L1 | `start` 在 `paused` 上被拒；`resume` 在非 paused 上不产生副作用 | 状态 + 文件不变 |
| K1.3 | L1 | 同一任务并发两个 turn 不交错 | 可观察执行顺序 |
| K1.4 | L1 | turn 失败必须给出非空原因（模型错误/额度耗尽/中止） | `reply` 非空且类别正确 |
| K1.5 | L1 | 终态任务重复驱动不复活、不重复执行 | 无新工具调用 |
| K2.1 | L2 | 每个 toolCall 恰好一个 toolResult（批准/拒绝/同批跳过/中止） | 转录配对 |
| K2.2 | L2 | 跨 runner 恢复后 system 消息唯一、顺序合法 | 模型请求可解析 |
| K2.3 | L2 | 损坏/版本不匹配 snapshot 显式失败 | 抛错，不静默重置 |
| K2.4 | L2 | 空回复兜底：无文本但有 block/limit 原因时必须回传原因 | `reply` 非空 |
| K2.5 | L2 | 同批次被跳过的调用标记为“未执行”，不重放 | 工具结果语义 |
| K3.1 | L3 | `..`、绝对路径、符号链接逃逸全部被拒 | `isError`，workspace 不变 |
| K3.2 | L3 | 读/写/输出超限被拒且 run 可继续 | `isError` + 后续轮可执行 |
| K3.3 | L3 | bash 超时/中止会杀进程并返回 `isError` | 进程退出 + 结果 |
| K3.4 | L3 | 新建文件的父目录链也做边界检查 | 逃逸被拒 |
| K3.5 | L3 | bash 环境只含白名单 + 注入项 | 敏感 env 不可见 |
| K4.1 | L3 | 7 个工具均可被调用且返回非空结果 | 逐个最小调用 |
| K4.2 | L3 | 工具失败以 `isError` 返回，不中断 run | 后续 assistant 仍执行 |
| K4.3 | L3 | 名称归一化不影响执行与审批 | 只影响报告字段 |

### M2

| ID | 层 | 关键点 | 断言方式 |
|----|----|--------|----------|
| K5.1 | L5 | write/edit 默认必须审批；危险 bash 必须审批；普通 bash 不审批 | 状态 + 文件 |
| K5.2 | L5 | 同批首个待审批后，后续调用不得执行 | 文件不变 |
| K5.3 | L5 | 批准后恰好执行一次；拒绝后不执行且不重试 | 计数/文件 |
| K5.4 | L5 | 跨进程/重复 `resume` 同一 `pendingStep` 只执行一次 | 计数/文件 |
| K5.5 | L5 | 审批过期后明确拒绝，不悬挂 | 状态 + 原因 |
| K6.1 | L6 | save 后另一 runner `load` 可继续 | 第二轮成功 |
| K6.2 | L6 | `close` 后 `load` 为 null，且资源释放 | 返回值 |
| K6.3 | L6 | store 故障时 turn 结果可诊断，不静默成功 | 错误/状态 |
| K6.4 | L6 | 损坏记录不会导致进程崩溃 | 可读错误 |
| K7.1 | L7 | 不同任务串行，不并发跑模型 | 可观察顺序 |
| K7.2 | L7 | 同任务并发 `start` 不交错 | 状态 + 顺序 |
| K7.3 | L7 | detached 立即返回 running，`idle()` 等到终态 | 状态 |
| K7.4 | L7 | 锁队列可观测（等待数/当前任务） | 只读观测 |

### M3

| ID | 层 | 关键点 | 断言方式 |
|----|----|--------|----------|
| K8.1 | L8 | 429/5xx 重试后成功；最终失败映射为 `failed` + 可读原因 | 状态 + 原因 |
| K8.2 | L8 | timeout/abort 结束 turn，状态明确 | 状态 |
| K8.3 | L8 | usage 汇总与消息一致 | 数值 |
| K8.4 | L8 | memory 投影失败不影响 turn | 状态不变 |
| K9.1 | L9 | `ButlerTaskRef` 携带完成摘要/失败原因 | 字段存在且非空 |
| K9.2 | L9 | adapter 回传 turn 结果，不丢弃 `reply` | 上层可见 |
| K9.3 | L9 | 待审批信息完整（工具、原因、时间） | 字段 |
| K9.4 | L9 | 失败任务不伪装成完成 | 状态 |
| K10.1 | L10 | 完成/失败/待审批都能形成可发送回复 | 非空且无内部术语 |
| K10.2 | L10 | 路径/密钥/原始工具名不外泄 | 文本扫描 |
| K10.3 | L10 | 空结果有兜底话术 | 非空 |
| K10.4 | L10 | 审批文案按 provider 映射为中文服务名 | 文本 |

---

## 7. 验收口径

每个批次完成必须同时满足：

1. `pnpm typecheck`、`pnpm lint`、`pnpm format:check` 全绿；
2. `pnpm test` 全量通过，且新增关键点“改坏即红”（至少人工反向验证一次）；
3. `node scripts/audit/test-internal-assertions.mjs` 不超预算（当前 49 / 49，只降不升）；
4. agent-eval `trajectory` 18/18，`capability/heldout` 不低于既有基线；
5. 本批次的关键点清单全部有对应测试或明确“放过”说明。

---

## 8. 不做什么

- 不重写 `vendor/pi-agent` 循环；只在其上补契约与边界。
- 不改默认模型与成本策略（已由 Phase 2 矩阵定稿）。
- 不为每个工具写实现级单测；只测外部行为与边界。
- 不追求行覆盖；只追求“关键点改坏必红”。
- 不在 M1 阶段改用户可见文案（留给 B10 统一收口）。

---

## 9. 批次状态

| 批次 | 状态 | 备注 |
|------|------|------|
| B1 任务契约与状态机 | ✅ 已交付 | 2026-11-20；见 §9.1 |
| B2 转录完整性 | ✅ 已交付 | 2026-11-20；见 §9.2 |
| B3 工作区边界 | ✅ 已交付 | 2026-11-20；见 §9.3 |
| B4 工具协议 | ✅ 已交付 | 2026-11-20；见 §9.4 |
| B5 审批闸门 | ✅ 已交付 | 2026-11-20；见 §9.5 |
| B6 持久化与恢复 | ✅ 已交付 | 2026-11-20；见 §9.6 |
| B7 并发与调度 | ✅ 已交付 | 2026-11-20；见 §9.7 |
| B8 模型与上下文 | ✅ 已交付 | 2026-11-20；见 §9.8 |
| B9 结果契约 | ✅ 已交付 | 2026-11-20；见 §9.9 |
| B10 端到端可见性 | ✅ 已交付 | 2026-11-20；见 §9.10 |

### 9.1 B1 交付记录（2026-11-20）

改动：

- `PiTaskRunner` 增加 `queued` 标记与 `runExclusive()`：同任务第二个 turn 在取全局锁前即被拒绝，消除 `running` 检查与取锁之间的竞态（K1.3/F3-07）。
- `resume()` 先做状态校验：非 `paused` 且无 `pendingStep` 时直接失败，不产生副作用（K1.2）。
- 软暂停（`pause()` 置 paused 但无 `pendingStep`）用“继续完成任务。”恢复，不再注入审批话术（K1.2/F3-05）。
- `runTurn()` 增加 `terminationReason`：额度耗尽、超时、软暂停都会带原因；回复优先级改为“待审批原因 → 失败原因 → 暂停原因 → 终止原因 → 模型文本”，不再出现空回复或被旧文本覆盖（K1.4/F3-02）。
- `running` 状态统一由 `runExclusive()` 托管，`runTurn()` 不再自行置位。

测评：

- 新增 8 条关键点测试（`pi-task-runner.test.ts` 的 `task contract` 块），覆盖 K1.1–K1.5；
- 锁测试改为只断言可观察的串行顺序，移除 `activeTaskId/queueLength` 内部断言；
- 反向验证：临时移除 `terminationReason` 分支后，额度用例按预期变红，再恢复。

验证结果：

| 项 | 结果 |
|----|------|
| `pnpm vitest run packages/runtime/src/execution/pi-task-runner.test.ts` | 21 passed |
| `pnpm vitest run packages/runtime/src/butler/pi-task-adapter.test.ts` | 5 passed |
| `pnpm vitest run apps/api/src/butler-assembly.test.ts` | 5 passed |
| `pnpm typecheck` | 全绿 |
| `pnpm lint` | 全绿 |
| `pnpm format:check`（改动文件） | 通过 |
| `scripts/audit/test-internal-assertions.mjs` | 49 / 49，未上升 |

### 9.2 B2 交付记录（2026-11-20）

改动：

- 新增 `parseSnapshot(record)`：校验 `version === 1`、`messages` 为数组、每条消息 role 合法、首条必须是 system、system 消息唯一、`toolResult` 必须带 `toolCallId`；损坏或旧版本显式失败，不再静默重建（K2.3/F3-06）。
- `completeDanglingToolResults(messages, text)` 文本参数化，按结束原因标注“等待审批 / 已暂停 / 执行失败 / 被中断，本步未执行”（K2.5）。
- 修正悬空结果的插入位置：只插入到 assistant 之后的连续 `toolResult` 之后，绝不越过后续 user/assistant 消息（K2.1）。
- 入口修复历史遗留的悬空调用，出口在保存前补全本批次被中断的调用，保证持久化转录始终配对（K2.1/K2.2）。

测评：

- 新增 7 条关键点测试：版本不匹配、首条非 system、重复 system、跨 runner 单一 system、批次配对且延迟调用不执行、崩溃遗留悬空修复、批次中途中断补全；
- 覆盖 K2.1–K2.5，其中 K2.4 由 B1 的额度用例与 B2 的暂停/失败用例共同覆盖；
- 反向验证：临时移除保存前的 `completeDanglingToolResults`，中断用例按预期变红，再恢复。

验证结果：

| 项 | 结果 |
|----|------|
| `pnpm vitest run packages/runtime/src/execution/pi-task-runner.test.ts` | 28 passed |
| `pnpm vitest run packages/runtime/src/butler/pi-task-adapter.test.ts apps/api/src/butler-assembly.test.ts` | 10 passed |
| `pnpm typecheck` | 全绿 |
| `pnpm lint` | 全绿（0 warning） |
| `pnpm exec prettier --check`（改动文件） | 通过 |
| `scripts/audit/test-internal-assertions.mjs` | 49 internal-only，未上升 |

### 9.3 B3 交付记录（2026-11-20）

改动：

- `pathExists` 由 `stat` 改为 `lstat`：悬空符号链接会被视为“已存在组件”，从而进入 realpath 校验，而不是被当作新文件直接写入（K3.1/K3.4）。
- `resolveInsideWorkspace` 对无法 realpath 的已存在组件改为 fail-closed（悬空链接、权限错误），不再回退到词法路径；关闭“悬空链接写穿透 workspace”的逃逸路径。
- bash 中止时 `kill + finish("aborted")` 立即 resolve，避免 shell 的孙进程持有管道导致 tool 永久悬挂；`timer` 句柄前置，消除 TDZ 风险（K3.3）。

测评：

- 新增 `pi-native-tools.test.ts`，15 条边界测试：`..`/绝对路径逃逸、越界符号链接、悬空链接写入、悬空链接父目录、workspace 内多层新建、搜索不跟随符号链接、读写超限后可继续、bash 输出截断、超时、中止、env 白名单与显式注入；
- 覆盖 K3.1–K3.5；
- 反向验证：把 `lstat` 改回 `stat` 后，悬空链接解析与写入两条用例按预期变红。

验证结果：

| 项 | 结果 |
|----|------|
| `pnpm vitest run packages/runtime/src/execution/pi-native-tools.test.ts` | 15 passed |
| `pnpm vitest run packages/runtime/src/execution/pi-task-runner.test.ts packages/runtime/src/butler/pi-task-adapter.test.ts` | 33 passed |
| `pnpm --filter @butler/runtime typecheck` | 全绿 |
| `pnpm lint` | 全绿（0 warning） |
| `pnpm exec prettier --check`（改动文件） | 通过 |
| `scripts/audit/test-internal-assertions.mjs` | 49 internal-only，未上升 |

### 9.4 B4 交付记录（2026-11-20）

结论：工具协议本身已满足关键点，**功能侧无需改动**；本批次补齐契约测试，防止后续改动把“报告名”与“执行名”混用。

测评：

- 7 个 pi-shaped 工具存在且可调用，成功结果均为非空文本（K4.1）；
- 读取缺失文件、非法 grep 正则等失败以 `isError` 返回，随后仍可继续调用（K4.2）；
- runner 级验证：工具失败不会中断 turn，模型继续给出回复（K4.2）；
- 审批策略只看到原始 pi 名（`write`），报告字段 `rawName=write` / `normalizedName=write_file`，实际写入正常（K4.3）；
- 反向验证：把归一化后的名字传给审批策略，归一化用例按预期变红。

验证结果：

| 项 | 结果 |
|----|------|
| `pnpm vitest run packages/runtime/src/execution/pi-native-tools.test.ts packages/runtime/src/execution/pi-task-runner.test.ts` | 47 passed（17 + 30） |
| `pnpm --filter @butler/runtime typecheck` | 全绿 |
| `pnpm lint` | 全绿（0 warning） |
| `pnpm exec prettier --check`（改动文件） | 通过 |
| `scripts/audit/test-internal-assertions.mjs` | 49 internal-only，未上升 |

### 9.5 B5 交付记录（2026-11-20）

改动：

- `start` / `resume` 先 `refresh()`：从 store 重新加载最新记录，跨进程不再基于过期缓存做审批决定（K5.4/F3-04）。
- `PiTaskPendingStep` 增加可选 `decidedAt`：执行审批前先持久化“决策声明”，第二个进程看到后只结算、不重复执行（K5.4）。
- 新增审批 TTL：`PiTaskRunnerOptions.approvalTtlMs`（默认 30 分钟，`<= 0` 关闭）；过期审批不再启动模型，直接返回“审批已过期，本步未执行。”并清空 pending（K5.5）。
- 新增 `settleLocked()`：重复声明/过期两种情况都会写入一条 `isError` 工具结果并清除 pending，不启动新的 turn。

测评：

- 默认策略矩阵：write/edit 必审批、危险 bash 必审批、普通 bash/read 不审批（K5.1）；
- 拒绝后不执行、不重试，转录记录拒绝原因（K5.3）；
- 两个 runner 共享 store 时，同一 pending 只执行一次；重复 resume 明确报错（K5.4）；
- 已被 `decidedAt` 声明的 pending 不执行，返回“已处理”（K5.4）；
- 超过 TTL 的 pending 不执行、不悬挂，pending 被清空（K5.5）；
- 反向验证：移除 `resume` 的 `refresh()`，跨 runner 用例按预期变红。

验证结果：

| 项 | 结果 |
|----|------|
| `pnpm vitest run`（runner + native tools + adapter + assembly） | 62 passed |
| `pnpm --filter @butler/{ports,runtime,persistence} typecheck` | 全绿 |
| `pnpm --filter @butler/api typecheck` | 全绿 |
| `pnpm lint` | 全绿（0 warning） |
| `pnpm exec prettier --check`（改动文件） | 通过 |
| `scripts/audit/test-internal-assertions.mjs` | 49 internal-only，未上升 |

### 9.6 B6 交付记录（2026-11-20）

改动：

- `SessionState` 增加 `closed` 标记；`close()` 先置位再 abort、删除记录，运行中的 turn 结束时不写回，避免“关闭后被最后一笔 save 复活”（K6.2）。
- 保存失败统一包装为 `task <id>: failed to persist session: <原因>`，明确提示“本轮可能已执行但未持久化”，不再抛出裸驱动错误（K6.3）。
- 关闭中的 turn 返回 `status: "closed"` 与“任务已关闭。”，调用方不再误判为 idle（K6.2/F3-08）。
- 损坏记录继续由 `parseSnapshot` 显式拒绝，错误信息带 taskId（K6.4）。

测评：

- save 后第二个 runner 可加载并继续，转录包含两轮内容（K6.1）；
- close 后 `runner.load` / `store.load` / 另一 runner 均为 null，start 报 not found，重复 close 幂等（K6.2）；
- 运行中 close 不会复活记录，turn 返回 `closed`（K6.2）；
- store 保存失败时错误包含 taskId 与底层原因（K6.3）；
- `snapshot: null`、`messages` 非数组均显式拒绝且进程不崩溃（K6.4）；
- 反向验证：恢复“总是保存”，运行中 close 用例按预期变红。

验证结果：

| 项 | 结果 |
|----|------|
| `pnpm vitest run`（runner + native tools + adapter + assembly） | 67 passed |
| `pnpm --filter @butler/{runtime,persistence} typecheck` | 全绿 |
| `pnpm lint` | 全绿（0 warning） |
| `pnpm exec prettier --check`（改动文件） | 通过 |
| `scripts/audit/test-internal-assertions.mjs` | 49 internal-only，未上升 |

### 9.7 B7 交付记录（2026-11-20）

实现事实修正：`GlobalAgentLock` 是进程内 **FIFO 串行锁**（同一时刻 1 个 Agent），不是“可并行的上限锁”。因此本批次把 K7.2 落为“跨任务请求按 FIFO 串行、不交错”，而不是引入进程内并行；真正的并行需要独立设计（多 worker / 多进程），不在 B7 范围。

改动：

- `runExclusive()` 在拿到锁后检查 `session.closed`：排队期间被 `close()` 的任务不会消耗锁、也不会再跑一轮（K7.4），并立即释放锁。

测评：

- 三个任务共享锁，断言调用顺序严格为 A→B→C，回复与队列位置对应（K7.2）；
- 锁回调抛错后，下一次 `run()` 仍可正常获得锁（K7.3）；
- 任务 A 持锁时，任务 B 排队；`close(B)` 后释放 A，B 以 `closed` 拒绝且模型流从未被调用，随后任务 C 正常执行（K7.3/K7.4）；
- 同任务并发仍由 B1 的 `queued` 守卫拒绝（K7.1）；
- 反向验证：移除 `session.closed` 守后，排队关闭用例按预期变红。

验证结果：

| 项 | 结果 |
|----|------|
| `pnpm vitest run`（runner + native tools + adapter + assembly） | 70 passed |
| `pnpm --filter @butler/runtime typecheck` | 全绿 |
| `pnpm lint` | 全绿（0 warning） |
| `pnpm exec prettier --check`（改动文件） | 通过 |
| `scripts/audit/test-internal-assertions.mjs` | 49 internal-only，未上升 |

### 9.8 B8 交付记录（2026-11-20）

改动：

- 超时不再返回 `idle`：新增 `timedOut` 标记，超时的 turn 状态为 `failed`，回复保留 `任务执行超时（Xms）`，不再被“任务执行失败”覆盖（K8.2）。

测评：

- 超时用例：stream 延迟返回，`timeoutMs` 先到期，断言 `failed` + 回复含“超时”（K8.2）；
- usage 用例：一轮内两次模型调用（工具调用 + 最终文本），断言 `input/output/total` 为两次之和（K8.3）；
- memory 投影抛错时 turn 仍为 `idle`、回复完整、记录已持久化，仅记录 warning（K8.4）；
- 模型最终失败映射为 `failed` + 可读原因，由既有“surfaces a model error”用例覆盖（K8.1）；429/5xx 重试由 `createPiStreamFn` 委托 `retryAssistantCall`（pi-ai）负责，本批次未新增网络级重试用例；
- 反向验证：移除 `timedOut` 参与 `failed` 判定，超时用例按预期变红。

验证结果：

| 项 | 结果 |
|----|------|
| `pnpm vitest run`（runner + native tools + adapter + assembly） | 73 passed |
| `pnpm --filter @butler/runtime typecheck` | 全绿 |
| `pnpm lint` | 全绿（0 warning） |
| `pnpm exec prettier --check`（改动文件） | 通过 |
| `scripts/audit/test-internal-assertions.mjs` | 49 internal-only，未上升 |

### 9.9 B9 交付记录（2026-11-20）

改动：

- `PiTaskSessionSnapshot` 增加 `lastReply` / `lastError`（都在既有 JSON snapshot 内，无数据库迁移）；runner 每轮结束时持久化最新回复，成功轮清除旧的 `lastError`。
- `ButlerTaskRef` 增加 `lastReply` / `error`；adapter 的 `start`、`status`、`list`、`approve` 均带回结果。
- 管家层不再只回“已创建任务”：`/new`、审批回调、LLM `start_task` 工具、`/status` 都会展示任务结果或失败原因；暂停时仍由审批提示负责，避免重复。

测评：

- adapter：inline 启动与审批恢复都返回 `lastReply`；失败任务返回 `error`；
- butler：`/new` 返回已完成任务的结果文本；失败任务返回失败原因；
- 反向验证：移除 adapter 的 `lastReply` 透出，启动用例按预期变红。

验证结果：

| 项 | 结果 |
|----|------|
| `pnpm vitest run`（runner + native tools + adapter + butler + assembly + approval-resume） | 96 passed |
| `pnpm --filter @butler/{ports,runtime,api} typecheck` | 全绿 |
| `pnpm lint` | 全绿（0 warning） |
| `pnpm exec prettier --check`（改动文件） | 通过 |
| `scripts/audit/test-internal-assertions.mjs` | 49 internal-only，未上升 |

### 9.10 B10 交付记录（2026-11-20）

改动：

- adapter 对 `lastReply` / `lastError` 中的 workspace 绝对路径统一脱敏为“项目目录”，确保任务结果回流时不泄漏本地路径。
- 完成 / 失败 / 待审批三条路径均经 `finalizeReply` 收口：markdown、内部术语、空回复兜底、超长截断保持一致。

测评：

- 完成任务的结果文本、失败任务的失败原因均不含 workspace 根路径；
- 待审批路径由既有审批提示用例覆盖；
- 反向验证：移除脱敏后两条路径用例按预期变红。

全量验收（2026-11-20 复跑）：

| 项 | 结果 |
|----|------|
| `pnpm test` | 277 文件 / 2,340 通过 / 2 skipped |
| `pnpm typecheck` | 全绿 |
| `pnpm lint` | 全绿（0 warning） |
| `pnpm format:check` | 通过 |
| `scripts/audit/test-internal-assertions.mjs` | 49 internal-only（2.4%） |

阶段结论：B1–B10 全部交付，F3-01…F3-08 全部闭环；任务层从“能跑”推进到“可重放、边界封闭、可恢复、结果可见”。
