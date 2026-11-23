# Phase 2 C2 — 审批前预览（diff / 命令全文）规格

> **状态**：已交付（2026-11-23）
> **选点依据**：[`phase2-feature-deepening-2026-11-23.md`](../phase2-feature-deepening-2026-11-23.md) C2
> **默认开关**：`BUTLER_V5_APPROVAL_PREVIEW=0`（关闭时完全回退旧文案）

## 1. 目标

owner 收到审批时，不只知道「需要修改文件」，还能直接看到将执行什么：

- `write_file`：相对路径 + 增删行摘要（与现有内容对比，超限截断）；
- `run_command`：完整命令（argv 拼接）；
- 其他能力：回退现有文案。

非目标：

- 不改审批状态机、TTL、授权模型、Grant 匹配；
- 不新增 UI、不改变批准/拒绝接口；
- 不展示绝对路径、凭证、`.env` 原文。

## 2. 场景与判据

| # | 场景 | 期望 |
|---|------|------|
| 1 | 审批 `write_file demo-note.txt` | 消息含「文件：demo-note.txt」与新增/删除行数 |
| 2 | 覆盖已有文件 | 消息含 `+` / `-` 行摘要（截断时标注「已截断」） |
| 3 | 审批 `run_command ["pnpm","test"]` | 消息含「命令：pnpm test」 |
| 4 | owner `GET /v1/owner/approvals` | 每条含 `preview` 字段（字符串或省略） |
| 5 | 批准 / 拒绝 / 过期 | 行为与现版本完全一致 |
| 6 | 预览生成抛错 | 回退旧文案，审批继续，不阻断 |

## 3. 设计

### 3.1 纯渲染器

新增 `packages/runtime/src/approval-preview.ts`（无 IO，便于单测）：

```ts
renderApprovalPreview({
  capability, args, oldContent?, workspaceRoot?,
  maxLines?, maxChars?,
}): string | null
```

- `run_command`：`命令：<argv.join(" ")>`；换行与控制字符折叠；上限 600 字符；
- `write_file`：`文件：<相对路径>` + `新增 N 行，删除 M 行`；有 `oldContent` 时
  输出前后公共部分之外的 `-` / `+` 行，最多 12 行、800 字符，超出追加
  `…（已截断）`；
- 路径：若以 `workspaceRoot` 开头则转相对路径；绝对路径一律只保留 basename；
- 其他 capability 返回 `null`。

### 3.2 审批执行链

- `ApprovalExecutionContext` 增加可选 `preview?: string`（由 app 层计算）。
- `capability-boundary.ts` 在 `Ask` 分支：
  - 把 `preview` 写入等待步骤 `input.preview`（供 owner 路由读取）；
  - owner 可见回复变为 `[待审批] <question>\n\n<preview>`（无 preview 时保持原样）。
- `parsePendingCapabilityInput` 解析并返回 `preview`（类型可选）。

### 3.3 App 层预览构建

新增 `apps/api/src/approval-preview.ts`：

- `buildToolApprovalPreview({ capability, args, env, workspaceRoot })`；
- 开关关闭或非 `write_file` / `run_command` 时返回 `null`；
- `write_file` 用 `resolveUnderWorkspace` + `readFileSync` 读取旧内容
  （不存在视为新建，`oldContent = ""`）；
- 任何异常吞掉并返回 `null`（由调用方记录 debug 日志），不影响审批。

`makeToolExecutor` 增加 `workspaceRoot` 入参，在 `runButlerLoop` 中由
`BUTLER_V5_WORKSPACE_ROOT` / `process.cwd()` 解析后传入。

### 3.4 owner 接口

`GET /v1/owner/approvals` 增加 `preview` 字段（存在时才返回），
其余字段与顺序不变。

## 4. 失败可见性

- 预览生成失败：仅日志，不改变审批问题与状态；
- 内容超长：截断并显式标注；
- 敏感内容：沿用在 `finalizeReply` / `sanitizeForWechat` 已有的路径与凭证脱敏，
  预览本身不拼接 `.env` 内容以外的凭证字段。

## 5. 回滚

`BUTLER_V5_APPROVAL_PREVIEW=0`（默认）时：

- 不计算、不写入、不返回 `preview`；
- 审批消息与 owner 接口与现版本逐字节一致。

## 6. 验证命令

```bash
pnpm --filter @butler/runtime test
pnpm --filter @butler/api test
pnpm typecheck && pnpm lint && pnpm test
```

重点用例：命令全文、diff 增删统计、超长截断、绝对路径脱敏、开关关闭回退、
批准/拒绝行为不变。
