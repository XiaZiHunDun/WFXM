# Phase 2 C2 — 审批前预览任务

> **配套规格**：[`spec.md`](spec.md)
> **状态**：已交付（2026-11-23）

## 任务清单

### T1 — 纯渲染器

- [x] `packages/runtime/src/approval-preview.ts`：`renderApprovalPreview`。
- [x] `packages/runtime/package.json`：导出 `./approval-preview.js`。
- [x] 单测：run_command 全文、write_file 新建/覆盖、截断、路径脱敏、未知能力返回 null。

### T2 — 审批链

- [x] `capability-boundary.ts`：`ApprovalExecutionContext.preview`，Ask 回复追加预览，
      等待步骤 `input.preview` 落库。
- [x] `approval-runtime.ts`：`PendingCapabilityInput.preview` 解析。
- [x] 单测：有/无 preview 的回复与 step input。

### T3 — App 层

- [x] `apps/api/src/approval-preview.ts`：开关、旧内容读取、异常回退。
- [x] `tool-boundary.ts`：`workspaceRoot` 入参 + 预览注入。
- [x] `wechat-inbound-butler.ts`：传入 workspace root。
- [x] `owner-routes/approvals-runs.ts`：返回 `preview`。
- [x] 单测：开关关闭无预览、write_file diff、run_command 全文、owner 路由字段。

### T4 — 文档与验证

- [x] `docs/ENV.md`：补 `BUTLER_V5_APPROVAL_PREVIEW`。
- [x] `docs/FEATURES.md` / `docs/PROGRESS.md` 同步。
- [x] `docs/plans/README.md` 索引本 spec。
- [x] `pnpm format` / `typecheck` / `lint` / `test`。
- [x] 汇报结果，**不自动提交**。

## 完成定义

- 规格 §2 六条判据有对应自动化用例；
- 默认关闭时既有审批消息与接口零变化；
- 批准 / 拒绝 / 过期路径无回归。
