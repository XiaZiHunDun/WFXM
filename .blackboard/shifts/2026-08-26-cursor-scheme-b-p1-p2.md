---
shift_id: 2026-08-26-cursor-scheme-b-p1-p2
agent: cursor
status: done
---

# 班次卡：方案 B + P1 Policy + working-set + DeepSeek + P2 allowlist 抽测

> 新会话开篇：**先读** [`.blackboard/state.md`](../state.md) → 本文 §2–§6。

---

## 1. 当前位置（一句话）

**微信 dev 主链（方案 B）+ CI/T4/T5 + P1 统一 Grant + dev working-set + DeepSeek V4 thinking disabled + P2 sandbox allowlist 生产抽测均已绿**；`butler-v5` **908→913 vitest**（末轮 913 pass，以 `pnpm test` 为准）。

---

## 2. 本班交付摘要

### 2.1 方案 B（Child Run + MiniMax Exec）— 已完成

| 项 | 说明 |
|----|------|
| 默认路径 | `dev_task` → Plan Loop（DeepSeek）→ `delegate_to_subagent` → Child Run（`MODEL_EXEC`）→ 异步验收 |
| Legacy | `BUTLER_V5_DEV_DIRECT_EXEC=1` 才主 Loop 直调 exec |
| T1–T3 | 语料、delegate 全链、LLM fixture（CI `:3010`） |
| T4/T5 | `smoke:prod-tune`、`smoke:ilink` 生产抽测 PASS |
| ADR | [`docs/plans/decisions/v5-wechat-dev-exec-child-run-2026-08.md`](../../docs/plans/decisions/v5-wechat-dev-exec-child-run-2026-08.md) §8 已勾选 |

### 2.2 体验债（本班续做）

- **ProjectState**：`lastChildRun*`；`/状态` 展示子代理进度
- **Intake 语料**：模糊 dev 短句 + `DEV_TASK_RE` 扩充
- **MODEL**：`BUTLER_V5_MODEL_PLAN/INTAKE=deepseek-v4-flash`

### 2.3 P1 — 统一 Policy / ScopedGrant

- **`packages/runtime/src/scoped-grant-service.ts`**：`issuePreconfiguredGrants()`
- **Dev Session Grant** 迁入 PostgreSQL `scoped_grants`（不再用 `dev-sessions.json`）
- **委派 Grant**（`delegation-grants.ts`）复用同一服务
- **注意**：已开「开发模式」的用户需 **重新发「开发模式」** 才能在 DB 里签发 Grant

### 2.4 working-set 调优

- **`packages/runtime/src/working-set-budget.ts`**
- dev 任务默认 **20 条 / 8000 字**（`BUTLER_V5_DEV_WORKING_SET_*`）
- Intake 经 RunTrigger `payload.workingSetMode=dev` 注入（**未改**受保护 `wechat-inbound-butler.ts`）
- **`filterDevHistoryNoise`**：去掉较早 ping/pwd 等 chat 噪声

### 2.5 DeepSeek V4 thinking disabled

- **`packages/adapters/src/llm/deepseek-request.ts`**
- 对 `deepseek-v4-*` 默认请求体带 `thinking: { type: "disabled" }`
- env：`BUTLER_V5_DEEPSEEK_THINKING=disabled`（默认即 disabled，可不写）

### 2.6 P2 sandbox allowlist 生产抽测 — 本班末 PASS

| 命令 | 结果 |
|------|------|
| `pnpm smoke:allowlist-production` | PASS |
| `pnpm smoke:allowlist-slirp` | PASS（rawBlocked + slirp proxyPath） |
| `pnpm smoke:allowlist-pnpm` | PASS（live `registry.npmjs.org:443`） |

---

## 3. 生产 env 要点（`~/.config/butler-v5/env`）

```bash
# 方案 B / 子代理
BUTLER_V5_SUBAGENT_ENABLED=1
BUTLER_V5_RUN_NOTIFY_ENABLED=1
# 无 BUTLER_V5_DEV_PREFER_DELEGATE；无 BUTLER_V5_DEV_DIRECT_EXEC（Scheme B 默认）

# Model Router
BUTLER_V5_MODEL_PLAN=deepseek-v4-flash
BUTLER_V5_MODEL_INTAKE=deepseek-v4-flash
BUTLER_V5_MODEL_EXEC=MiniMax-M3
MINIMAX_API_KEY=（已配置）
BUTLER_V5_DEEPSEEK_THINKING=disabled   # 可选；代码默认 disabled

# P2 Sandbox
BUTLER_V5_SANDBOX=bubblewrap
BUTLER_V5_SANDBOX_NETWORK_MODE=allowlist
BUTLER_V5_SANDBOX_EGRESS_ISOLATION=slirp
BUTLER_V5_SANDBOX_EGRESS_UPSTREAM_PROXY=http://127.0.0.1:7890

# Working-set（可选覆盖）
# BUTLER_V5_DEV_WORKING_SET_MAX_MESSAGES=20
# BUTLER_V5_DEV_WORKING_SET_MAX_CHARS=8000
```

**Gateway**：`systemctl --user status butler-v5-gateway.service` — 改 adapter/env 后需 `restart`。

---

## 4. 验证命令（新会话起手）

```bash
cd ~/projects/WFXM/butler-v5

# 单测（改代码后必跑）
pnpm test

# CI 回归（fixture :3010，勿与生产 :3000 冲突）
bash scripts/cutover/ci-smoke-regression.sh

# 生产金丝雀（live LLM，不进 CI）
set -a && . ~/.config/butler-v5/env && set +a
pnpm smoke:prod-tune

# P2 allowlist 抽测
pnpm smoke:allowlist-production
pnpm smoke:allowlist-slirp      # 可选
pnpm smoke:allowlist-pnpm       # 可选，需外网 + upstream proxy

# iLink 抽测
pnpm smoke:ilink
```

末轮已知：**913 passed | 1 skipped**（`pnpm test`）。

---

## 5. 建议下一班优先级

| 优先级 | 项 | 说明 |
|--------|-----|------|
| P0 | **Gateway 重启** | 若尚未重启：加载 DeepSeek thinking + scoped_grants dev session 逻辑 |
| P1 | **微信 loopback E2E** | Owner approve `networkAllowlist` + `run_command`（如 `pnpm install`）端到端；CLI `butler approve --network-allowlist` |
| P2 | **Dev Session 迁移提醒** | 生产用户重新「开发模式」一次（JSON → DB Grant） |
| P3 | **路线图非紧急** | P3/P4 条件准入、working-set 进一步调参、Intake LLM 体验 |

---

## 6. 不要做

- 改 **`butler-v5/apps/api/src/wechat-inbound-butler.ts`**（受保护；工具面走 `wechat-intake.ts` + `wechat-tool-profile.ts`）
- 把 **`smoke:prod-tune` / `smoke:allowlist-pnpm`** 升格为 PR 硬门槛（live 依赖外网/代理）
- CI 与生产共用 **`:3000`**（CI 用 **`:3010`** + LLM fixture）
- 恢复 **`dev-sessions.json`** 旁路 Grant
- 从 **`docs/history/`** 或 v4 文档推断 v5 实现

---

## 7. 关键文件索引

| 主题 | 路径 |
|------|------|
| 方案 B ADR | `docs/plans/decisions/v5-wechat-dev-exec-child-run-2026-08.md` |
| 生产架构事实 | `docs/architecture/v5-production-architecture-2026-08.md` |
| Intake / 委派 | `butler-v5/apps/api/src/wechat-intake.ts` |
| Grant 统一签发 | `butler-v5/packages/runtime/src/scoped-grant-service.ts` |
| Dev Session | `butler-v5/apps/api/src/dev-session-grant.ts` |
| working-set | `butler-v5/packages/runtime/src/working-set-budget.ts` |
| DeepSeek thinking | `butler-v5/packages/adapters/src/llm/deepseek-request.ts` |
| Sandbox allowlist | `butler-v5/packages/adapters/src/sandbox/`、`docs/plans/active/v5-sandbox-network-allowlist-2026-08.md` |
| CI smoke | `butler-v5/scripts/cutover/ci-smoke-regression.sh` |
| 全链 delegate 测 | `butler-v5/apps/api/src/wechat-dev-delegate.test.ts` |
| dev session 链测 | `butler-v5/apps/api/src/wechat-dev-session-chain.test.ts` |

---

## 8. 上一班一句话

方案 B 闭环 + P1 Grant 统一 + dev working-set + DeepSeek thinking disabled + P2 allowlist 三档生产 smoke 全绿；下一班优先 gateway 确认与 allowlist 微信/Owner 端到端。
