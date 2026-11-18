# 贡献指南

> Butler v5（``）是唯一活动实现。本文约定安装、检查、测试分层、提交门禁与提交信息风格。

## 安装

要求 Node.js 20+ 与 pnpm 9.15.0（`packageManager` 已固定）。

```bash

pnpm install          # postinstall 会安装 scripts/ai_guard 的 git hooks
cp .env.example .env  # 配置至少一个 LLM API Key
```

## 开发检查

提交前在 `` 下依次跑：

```bash
pnpm format:check
pnpm lint            # eslint --max-warnings 0
pnpm typecheck       # 各包 tsc --noEmit
pnpm test            # 单元 / 契约 / 架构测试
pnpm build
```

`pnpm typecheck` 之外，CI 还跑 `bash scripts/typecheck-gate.sh`（v5 类型门禁）；本地可用 `pnpm gate` 串联格式、类型、lint、测试与覆盖率。

## 测试分层

| 层        | 范围                                      | 命令                                                               |
| --------- | ----------------------------------------- | ------------------------------------------------------------------ |
| L1        | 单元 / 契约                               | `pnpm test`                                                        |
| L2        | 消息出口规范化                            | `pnpm vitest run packages/runtime/src/butler/presentation.test.ts` |
| L3        | 评估场景（gate）                          | `pnpm vitest run tests/eval`                                       |
| L4        | 渠道前验收窗口（真实路由 + 真实 runtime） | `npx tsx scripts/l4-smoke.ts`                                      |
| L4 可靠性 | 重投 / 并发 / 连续投递 / 无待审批         | `npx tsx scripts/l4-smoke.ts --suite reliability`                  |

验收与架构测试的其余入口：

```bash
pnpm test:acceptance     # 验收场景（生产 wiring + 内存 PGlite + 脚本化 LLM）
pnpm test:methodology    # methodology 19·19
pnpm vitest run tests/architecture
```

L4 脚本要求网关已启动，并从 `~/.config/env` 读取 `BUTLER_V5_INBOUND_SHARED_SECRET`。测试清单见 [`docs/TESTS.md`](docs/TESTS.md)。

## 提交前 AI Guard

`scripts/ai_guard/` 提供两个 git hook，由 `butler-v5` 的 `postinstall` 安装到 `.git/hooks/`：

| Hook                                | 作用                                                                               |
| ----------------------------------- | ---------------------------------------------------------------------------------- |
| `pre_commit_hook.sh` → `pre-commit` | secret 扫描（命中即阻止）；改动 v5 persistence 迁移时提示跑对应测试                |
| `commit_msg_hook.sh` → `commit-msg` | 暂存了 `protected_files.sh` 列出的受保护文件时，要求提交信息含 `[MANUAL-OVERRIDE]` |

规则：

- 受保护文件清单唯一来源是 [`scripts/ai_guard/protected_files.sh`](scripts/ai_guard/protected_files.sh)，两个 hook 都 source 该文件。
- 确需修改受保护文件时，在 commit message 中加 `[MANUAL-OVERRIDE]`，并在正文说明理由。
- 没有受保护文件改动时不要加该标记，避免掩盖审计。
- `--no-verify` 仅用于紧急情况；它同时跳过 secret 扫描。
- hook 与源文件不一致时，在仓库根运行 `bash scripts/ai_guard/install-pre-commit-hook.sh` 重新同步；CI 会检查二者是否漂移。

工程约束（文件大小、依赖方向、危险模式等）见 [`docs/GOVERNANCE.md`](docs/GOVERNANCE.md) 与 [`AGENTS.md`](AGENTS.md)。

## 提交信息风格

格式：`type(scope): 小写摘要`

- `type`：`feat`、`fix`、`refactor`、`test`、`docs`、`chore`、`build`、`perf`
- `scope`：模块名，如 `api`、`runtime`、`persistence`、`wechat`、`docs`
- 摘要使用小写短语，不加句号；必要细节放正文

```text
fix(runtime): handle empty compaction input
docs(tests): sync l4 smoke commands
feat(api): expose inbound shared secret check [MANUAL-OVERRIDE]
```

> 提交信息不要使用反引号，避免 shell 把内容当命令替换。

## 文档维护

行为变化时同步更新对应文档，而不是只在代码里注释：

- 架构 / 生产调用链 → [`DESIGN.md`](DESIGN.md)、[`docs/architecture/v5-production-architecture-2026-08.md`](docs/architecture/v5-production-architecture-2026-08.md)
- 环境变量 → [`.env.example`](.env.example) 与 [`docs/ENV.md`](docs/ENV.md)
- 测试 → [`docs/TESTS.md`](docs/TESTS.md)
- 索引 → [`docs/README.md`](docs/README.md)、[`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md)

## 发版

发版与自托管步骤见 [`docs/deployment/SELF-HOSTING.md`](docs/deployment/SELF-HOSTING.md) 与 [`docs/deployment/production-hardening.md`](docs/deployment/production-hardening.md)。
