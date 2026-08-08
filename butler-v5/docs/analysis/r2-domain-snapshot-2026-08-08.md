# v5 Domain 现状快照（2026-08-08）

## conversation/

- 已存在：context.ts, transitions.ts, types.ts, index.ts
- 缺失：完整 Project / Turn 单独 ADT，UserMessage 事件载荷
- R2.1 计划补全

## memory/

- 已存在：pure.ts, types.ts, index.ts
- 缺失：Search query schema、recency decay policy、conflict resolution
- R2.2 计划补全

## permissions/

- 已存在：types.ts, index.ts
- 缺失：decidePermission 纯函数、Capability Lease ADT
- R2.3 计划补全

## projects/

- 已存在：pure.ts, types.ts, index.ts
- 缺失：Project lifecycle 状态机、WorkspaceRoot isolation
- R2.1 计划补全

## tools/

- 已存在：pure.ts, types.ts, index.ts
- 缺失：ToolDefinition ADT、CommandSpec 收口
- R2.2 计划补全

## workflows/

- 已存在：transitions.ts, types.ts, index.ts
- 缺失：WorkflowRun/Step ADT、Channel 多分支实现
- R2.2 计划补全

## errors.ts

- 现有 11 种 ButlError 变体；R2.3 复核是否需要补 Approval/Network

## ports/src/index.ts

- 现有 11 个 Effect Tag；R2.3/R2.4 需对齐规格 §6.1/§8.1

## 公共观察

- 大多数 domain/ports/shared 使用 `export { X }` 形式，会被 ts-prune 标记为 "used in module"（同包 re-export）；R2 已通过修改 `scripts/typecheck-gate.sh` deadcode 段忽略 "used in module" 警告解决。
- 现有 9 个 domain 上下文已就位，但内部状态机/ADT 完整度不一。
- v5 工程五大门禁（lint / test / typecheck / format:check / deadcode）通过；R2.0 闭环。
