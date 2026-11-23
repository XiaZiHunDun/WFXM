# Phase 3c 遗留清理 Checklist

> 对应 [spec.md](./spec.md) 与 [tasks.md](./tasks.md)。全部在 2026-11-23 复跑通过。

## 能力契约

- [x] 管家规则可识别 `/retry [任务ID]`、`/diagnose`、`/undo` 及其中文短语
- [x] `/retry` 不自动批准 paused 任务，running/paused/未知/无任务均有可读回复
- [x] `/diagnose` 不调用模型，输出项目、会话、任务计数、待审批、最近任务、记忆接入
- [x] `/diagnose` 在任务层查询失败时降级为「任务层：查询失败」并保留其余信息
- [x] `/undo` 只给边界说明，不执行文件操作
- [x] pi 适配器可重跑 failed/idle/closed 任务，paused 无 pending 恢复，paused 有 pending 原样返回

## 渠道 cutover

- [x] `BUTLER_V5_<CHANNEL>_ENGINE` 优先于 `BUTLER_V5_CHANNEL_ENGINE`
- [x] 未设置、非法值、`legacy` 均保持旧引擎
- [x] `BUTLER_V5_CHANNEL_PROJECTS` 命中优先，否则 `DEFAULT_PROJECT_ID`，再否则 `wechat`
- [x] 非法 JSON 静默回退，不阻断入站
- [x] butler 模式缺少 provider 返回 503；assembly 失败返回可读 503
- [x] legacy 模式不触发 assembly
- [x] Slack / Telegram butler 模式由 ChannelPort 投递，路由不二次发送
- [x] generic channel butler 模式使用 no-op 端口并在响应体回传 reply
- [x] detached 通知按 owner 渠道分发（wechat / slack / telegram / generic）

## 验证命令

- [x] `pnpm typecheck`
- [x] `pnpm lint`
- [x] `pnpm format:check`
- [x] `pnpm test` — 278 文件 / 2,401 通过 / 2 skipped
- [x] `pnpm verify:butler` — 3 场景 / 13 轮全过
