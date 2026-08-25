# D1 审计：`~/.butler/` 删除准备（2026-08-24）

> **状态**：EXECUTED（2026-08-25；prep + D1 删除均完成）  
> **决策 SSOT**：[`v4-butler-home-retention-2026-08-20.md`](../decisions/v4-butler-home-retention-2026-08-20.md)  
> **日历**：原 **2026-09-18**；Owner **2026-08-25 提前执行**（见执行交接）  
> **生产事实**：v5 gateway active；`BUTLER_V5_DB=postgres`；v4 gateway **未**运行

---

## 1. 结论（TL;DR）

**不能在 2026-09-18 无准备地「整目录删除 `~/.butler/`」。**

v5 生产曾 **硬依赖** `~/.butler/` 中 2 项；**2026-08-24 已迁移入仓/迁路径**（见 §3）：

| 依赖 | 原路径 | 现状 |
| --- | --- | --- |
| Todoist MCP OpenAPI spec | `~/.butler/openapi/todoist-v1-readonly.yml` | ✅ `butler-v5/config/openapi/` + manifest 相对路径 |
| Subagent 审计 JSONL | `~/.butler/audit/subagent-r8x9.jsonl` | ✅ 默认 `~/.config/butler-v5/audit/subagent.jsonl` |

D1 可行路径：**备份 → 删 v4 遗留子树**；§3 两项完成后不再阻断整目录删除（仍建议分块删 + smoke）。

---

## 2. 体量快照（本机 2026-08-24）

| 路径 | 大小 | 类别 |
| --- | ---: | --- |
| **`~/.butler/` 合计** | **~88 MB** | v4 运行时主目录 |
| `tenants/` | 9.6 MB | v4 租户（memory 9.3 MB 在 `default/memory/`） |
| `runtime/` | 7.7 MB | v4 运行时锁/队列/审批残留 |
| `audit/` | 3.9 MB | **v5 仍写** subagent JSONL + v4 审计 |
| `metrics/` | 3.6 MB | v4 指标 |
| `exports/` | 2.6 MB | v4 导出 |
| `sessions/` | 2.5 MB | v4 会话 JSONL |
| `drill/` | 2.5 MB | v4 演练 |
| `vector_store/` | 2.2 MB | v4 向量 |
| `gateway_outbox/` | 1.3 MB | v4 出站队列 |
| `openapi/` | 72 KB | **v5 MCP 依赖**（todoist/github spec） |
| `butler.db` | 52 KB | v4 SQLite 残留 |
| `secrets.yaml` | 172 B | v4 凭证；**v5 凭证已在** `~/.config/butler-v5/env` |

**不在 D1 范围**（勿与 `~/.butler` 混淆）：

| 路径 | 大小 | 说明 |
| --- | ---: | --- |
| `WFXM/.butler/` | 388 KB | 仓库内示例/报告；ilink-media 缓存应在 `WFXM/.butler/ilink-media`（workspace 相对） |
| `projects/LingWen1/.butler/` | — | 项目级 runtime（skills/ingest 等） |
| `butler-v5/.butler/` | — | v5 开发守卫（scope-boundaries 等） |
| `~/.config/butler-v5/` | — | **v5 生产配置 SSOT**（env、ilink-sync.json） |

**未使用**：`~/.butler/v5-data/` 不存在（生产 Postgres，非 PGlite 默认目录）。

---

## 3. v5 生产依赖链（删除前必须处理）

### 3.1 Todoist MCP OpenAPI（P0 阻断） — **Done 2026-08-24**

```text
butler-v5/config/mcp-manifest.json
  → --openapi-spec openapi/todoist-v1-readonly.yml (relative to manifest dir)
  → butler-v5/config/openapi/todoist-v1-readonly.yml
```

- Spec 已入仓；`resolveManifestStdioArgs` 在 bootstrap 时解析相对路径。
- **D1 前动作**：~~复制 spec~~ ✅；`pnpm test` + MCP smoke（lst-projects）待 gateway 重启后点验。

### 3.2 Subagent 审计 JSONL（P0 阻断） — **Done 2026-08-24（方案 A）**

```text
apps/api/src/audit-service.ts → audit-log.ts
  → ~/.config/butler-v5/audit/subagent.jsonl
  → override: BUTLER_V5_SUBAGENT_AUDIT_PATH
```

- 与 Postgres `appendAuditEvent` **并行**（双写）；JSONL 为 R8.x.9 遗留 tail/grep 用途。
- **D1 前动作**：~~路径迁 config~~ ✅；旧 `~/.butler/audit/subagent-r8x9.jsonl` 归档保留不删。

### 3.3 已不依赖 `~/.butler/` 的 v5 路径

| 能力 | 实际路径 |
| --- | --- |
| 主数据库 | Docker Postgres `butler_v5` |
| iLink sync_buf | `~/.config/butler-v5/ilink-sync.json` |
| 微信媒体缓存 | `{BUTLER_V5_WORKSPACE_ROOT}/.butler/ilink-media` |
| MCP 凭证 | `~/.config/butler-v5/env`（非 secrets.yaml） |
| Project Knowledge | Postgres + `butler-v5/config/` |

---

## 4. v4 遗留（迁移后可删 / 归档）

以下 **v5 生产不读**（仅 v4 脚本/.timer 可能引用）：

| 子目录/文件 | 说明 |
| --- | --- |
| `tenants/default/memory/` | v4 MEMORY；v5 用 `BUTLER_V5_DURABLE_MEMORY` + Postgres |
| `sessions/` | v4 会话 transcript |
| `runtime/` | v4 锁、push 队列、审批残留 |
| `vector_store/` | v4 向量索引 |
| `gateway_outbox/`, `gateway_queue/` | v4 出站 |
| `metrics/`, `drill/`, `exports/` | 运营/演练历史 |
| `mcp.yaml`, `config.yaml` | 已迁移到 v5 manifest + env |
| `butler.db` | v4 SQLite |

**建议**：D1 前 `tar czf ~/backup-butler-home-20260918.tgz ~/.butler`，再按 §5 分步删除。

**2026-08-25 备份**（提前完成）：

| 文件 | 大小 | SHA256 |
| --- | ---: | --- |
| `~/backup-butler-home-20260825.tgz` | 12 MB | `3b3caa7dd49de951d79fa7e9102b92b9026b13e13997fd33f5c867b6f1de19f0` |

校验：`sha256sum -c ~/backup-butler-home-20260825.tgz.sha256`

---

## 5. systemd / 脚本（D1 前清理）

| 单元 | 状态（2026-08-25） | 建议 |
| --- | --- | --- |
| `butler-v5-gateway.service` | **active** | 保留 |
| `butler-morning-brief.service` | **stopped**（原 activating 卡死已 kill） | ✅ disabled |
| `butler-b9-weekly-gate.service` | **inactive**（failed 已 reset） | ✅ disabled |
| `butler-push-drain.service` | **inactive**（failed 已 reset） | ✅ disabled |

**2026-08-25 执行**：`systemctl --user stop` + `reset-failed` + `disable` 上述三 service + 对应 timer（timer 本就 disabled）。v5 gateway 未受影响。

v4 相关 `scripts/butler-*-preflight.sh` 仍默认读 `~/.butler/mcp.yaml` / `secrets.yaml` — 删除后这些脚本仅用于考古，或改文档标 legacy。

---

## 6. `migration/v4-to-v5` 包

- 位置：`butler-v5/packages/infrastructure/src/migration/v4-to-v5.ts`
- 现状：**stub**（返回空数组），无实际从 `~/.butler` 抽数逻辑。
- D1 含义：删除 `~/.butler` **不丢 v5 已迁移数据**（已在 Postgres）；仅丢 v4 历史会话/记忆文件副本。
- 若 Owner 要保留 v4 memory 文本：D1 前从 `tenants/default/memory/` 导出归档，**非**跑 stub migration。

**2026-08-25 归档**（#5 Done）：

| 文件 | 大小 | 内容 |
| --- | ---: | --- |
| `~/backup-butler-v4-memory-20260825.tgz` | 694 KB | raw SQLite + profile；exports JSON/SQL（16 experiences，82 vectors） |
| SHA256 | — | `ac9a5287b548859c3c3bbc596192fcbadf18f559c536f6d586f7f645f75e13de` |

校验：`sha256sum -c ~/backup-butler-v4-memory-20260825.tgz.sha256`。解压目录含 `README.md`。

---

## 7. D1 当天建议流程（2026-09-18 后）

```text
T-7 日（2026-09-11）
  ☑ 完成 §3.1 manifest spec 迁入仓库
  ☑ 完成 §3.2 audit 路径迁移或停写决策
  ☑ disable v4 systemd 单元
  ☑ tar 备份 ~/.butler → ~/backup-butler-home-20260825.tgz

D1 日（2026-08-25 执行）
  ☑ curl healthz + smoke-project-knowledge.mjs + 微信一句（微信真机 Owner 点验）
  ☑ 确认 Todoist MCP 仍绿（gateway 日志无 openapi 路径错误）
  ☑ rm -rf ~/.butler/tenants ~/.butler/sessions ~/.butler/runtime …（分块删 v4 子树）
  ☑ openapi/、audit/ 已删（§3 已迁移）
  ☑ 最终：rm -rf ~/.butler（目录已不存在）

T+1（同日完成）
  ☑ gateway restart + 同上 smoke PASS
  ☑ 更新 v4-butler-home-retention 决策为 EXECUTED
```

---

## 8. D1 前优先 backlog（建议顺序）

| # | 任务 | 估时 | 阻断删除 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | Todoist OpenAPI spec 入仓 + manifest 改路径 | 30 min | **是** | ✅ 2026-08-24 |
| 2 | audit JSONL 路径迁 `~/.config/butler-v5/` 或停写 | 1 h | **是** | ✅ 2026-08-24 |
| 3 | disable v4 systemd（morning-brief / b9 / push-drain） | 15 min | 否 | ✅ 2026-08-25 |
| 4 | 备份 tar + 记录 checksum | 15 min | 否 | ✅ 2026-08-25 |
| 5 | （可选）导出 `tenants/default/memory/` 只读归档 | 30 min | 否 | ✅ 2026-08-25 |

---

## 9. 相关链接

- 保留决策：[`v4-butler-home-retention-2026-08-20.md`](../decisions/v4-butler-home-retention-2026-08-20.md)
- 未接线包（migration 保留至 D1）：[`v5-unwired-packages-inventory-2026-08.md`](v5-unwired-packages-inventory-2026-08.md)
- 备份脚本：[`scripts/backup-butler-data.sh`](../../../scripts/backup-butler-data.sh)
