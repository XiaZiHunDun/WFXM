# 会话交接（新对话先读本文）

> 更新：**2026-11-24** | 适用：WFXM / Butler v5 主线
> 用途：新对话没有历史聊天记录时，用本文在 5 分钟内恢复上下文。
> 配套：[`PROGRESS.md`](PROGRESS.md)（阶段台账）、[`FEATURES.md`](FEATURES.md)（能力清单）、
> [`ENV.md`](ENV.md)（环境变量）。

## 0. 一句话现状

Phase 1–4 均已完成。Phase 4 已用 WFXM 真实开发出 Ledger Lite 记账应用，并额外验证了
**开放任务、多项目、真实微信入口、沙箱 Git 身份**。线上微信网关已加载最新代码并重启。

## 1. 新对话先读顺序

1. 本文；
2. [`PROGRESS.md`](PROGRESS.md) 的 Phase 2 / 3 / 4 小节；
3. 需要改代码时再读 [`../AGENTS.md`](../AGENTS.md) 与对应 spec。

## 2. 当前运行态（2026-11-24 10:29 起）

| 组件 | 状态 | 检查方式 |
|------|------|----------|
| 微信网关 | 运行中，user systemd 服务 | `systemctl --user status butler-v5-gateway.service` |
| 网关 API | 端口 3000 | `curl -s http://127.0.0.1:3000/healthz` → `{"status":"ok","wiring":"v5"}` |
| iLink | 端口 3001 | `curl -s http://127.0.0.1:3001/health` |
| Demo 控制台 | 已停止 | 重启命令见 §7 |
| Ledger Lite | 独立本地仓库，无 remote | `git -C projects/ledger-lite log --oneline -3` |
| wakeup-cli | 文件保留，无独立 Git 仓库 | `find projects/wakeup-cli -type f` |

主仓库已忽略 `projects/ledger-lite/` 与 `projects/wakeup-cli/`。

## 3. 关键提交（主仓库）

| 提交 | 内容 |
|------|------|
| `47519e2d` | 沙箱注入宿主 Git 身份，修复 `Author identity unknown` |
| `e7217a57` | Phase 4 文档：多项目 / 模糊需求 / 真实微信入口 |
| `32b090ed` | 补充真实微信回复与网关重启结果 |
| `69671a63` | Demo 真实 LLM 工作区模式 + Phase 4 spec |
| `623cde86` | C3 每周周报（手动 `/周报` + 定时推送） |
| `8453db83` | C1 提醒 + C2 审批预览 |

Ledger Lite 仓库（`projects/ledger-lite`）：`eface05`（奶茶账本），无 remote，未推送。

## 4. 能力开关（默认全部关闭）

| 能力 | 变量 | 默认 |
|------|------|------|
| 自然语言提醒 | `BUTLER_V5_REMINDERS_ENABLED` | `0` |
| 审批前预览 | `BUTLER_V5_APPROVAL_PREVIEW` | `0` |
| 每周周报 | `BUTLER_V5_WEEKLY_DIGEST_ENABLED` | `0` |
| 周报接收人 | `BUTLER_V5_WEEKLY_DIGEST_TO` | 空 |

关闭时对应工具 / worker / 命令不注册，已有数据保留。

## 5. 重要文件地图

| 主题 | 文件 |
|------|------|
| 沙箱 Git 身份 | `packages/adapters/src/sandbox/bubblewrap-runner.ts`（`resolveSandboxGitIdentityEnv`） |
| 命令工具接线 | `apps/api/src/workspace-tools.ts` |
| 提醒 worker | `apps/api/src/reminder-worker.ts`、`reminder-config.ts`、`reminder-time.ts` |
| 审批预览 | `apps/api/src/approval-preview.ts` |
| 周报 | `apps/api/src/weekly-digest.ts`、`weekly-digest-worker.ts`、`wechat-weekly-digest-command.ts` |
| Demo 真实模式 | `scripts/demo-server.ts` |
| Phase 4 spec | `docs/plans/active/phase4-real-project-2026-11-23/spec.md` |
| Phase 2 选点 | `docs/plans/active/phase2-feature-deepening-2026-11-23.md` |

## 6. 未完成 / 下一步

1. `wakeup-cli` 自动测试未补：SSH 重连后浏览器代理无法连接 4521；文件与 README 已就绪。
2. Ledger Lite 可选增强：CSV 金额统一两位小数、编辑交易、分页与图表、多用户鉴权。
3. 若继续真实开发验证，优先用真实微信或恢复浏览器端口转发，而不是只跑单测。

## 7. 验证命令

```bash
pnpm format:check
pnpm typecheck
pnpm lint
pnpm test
```

单文件复跑：

```bash
pnpm exec vitest run packages/adapters/src/sandbox/bubblewrap-runner.test.ts
```

Demo 真实 LLM（浏览器控制台）：

```bash
BUTLER_V5_DEMO_REAL_LLM=1 \
BUTLER_V5_DEMO_WORKSPACE=/home/ailearn/projects/WFXM/projects/wakeup-cli \
BUTLER_V5_DEMO_PORT=4521 \
pnpm demo:real
```

重启网关：

```bash
systemctl --user restart butler-v5-gateway.service
```

## 8. 约束与已知坑

- 所有文档 / 回复用中文；代码注释沿用中文。
- **不自动提交、不自动推送**；提交需 owner 明确指令。
- 受保护文件（见 `AGENTS.md`）修改后提交需在 message 加 `[MANUAL-OVERRIDE]` 并写明理由。
- `pnpm test` 全量在负载高时，`apps/api/src/tool-boundary-helpers.test.ts` 可能 10s 超时；
  单独复跑通常通过，先复跑再判断回归。
- 全量测试可能生成 `tests/acceptance/scenarios/_analyze.md`，会导致 `format:check` 失败，
  提交前先格式化或删除该生成物。
- 浏览器代理在 SSH 重连后可能无法访问本机 4521；服务本身正常（`curl` 200），需恢复端口转发。
- 沙箱 HOME 是临时目录；Git 身份通过环境变量注入，不再依赖 `~/.gitconfig`。

## 9. 新对话开场白（可直接复制）

> 先读 `docs/HANDOFF.md` 和 `docs/PROGRESS.md` 的 Phase 2–4 小节，确认当前状态后继续。
> 不要自动提交或推送，完成一步先汇报。
