# D1 执行交接：删除 `~/.butler/`（2026-08-25）

> **状态**：Active — **Owner 决定提前执行**（原日历 2026-09-18）  
> **前置审计 SSOT**：[`v5-d1-butler-home-audit-2026-08-24.md`](v5-d1-butler-home-audit-2026-08-24.md)  
> **保留决策 SSOT**：[`v4-butler-home-retention-2026-08-20.md`](../decisions/v4-butler-home-retention-2026-08-20.md)  
> **新会话开篇**：读本文件 → `.blackboard/state.md` → 按 §4 执行

---

## 1. 本班已完成（勿重复）

| # | 任务 | 完成日 | 证据 |
| --- | --- | --- | --- |
| 1 | Todoist OpenAPI spec 入仓 + manifest 相对路径 | 2026-08-24 | `butler-v5/config/openapi/todoist-v1-readonly.yml`；commit `94c8f06b` |
| 2 | Subagent audit 迁 `~/.config/butler-v5/audit/subagent.jsonl` | 2026-08-24 | `BUTLER_V5_SUBAGENT_AUDIT_PATH`；`audit-log.ts` |
| 3 | v4 systemd stop/disable（morning-brief / push-drain / b9） | 2026-08-25 | 三单元已 inactive；v5 gateway 仍 active |
| 4 | 全量 tar 备份 `~/.butler` | 2026-08-25 | `~/backup-butler-home-20260825.tgz`（12 MB） |
| 5 | v4 memory 只读归档 | 2026-08-25 | `~/backup-butler-v4-memory-20260825.tgz`（694 KB） |

**备份校验（2026-08-25 09:50 已通过）**：

```bash
sha256sum -c ~/backup-butler-home-20260825.tgz.sha256
sha256sum -c ~/backup-butler-v4-memory-20260825.tgz.sha256
# 期望 OK
```

| 文件 | SHA256 |
| --- | --- |
| `backup-butler-home-20260825.tgz` | `3b3caa7dd49de951d79fa7e9102b92b9026b13e13997fd33f5c867b6f1de19f0` |
| `backup-butler-v4-memory-20260825.tgz` | `ac9a5287b548859c3c3bbc596192fcbadf18f559c536f6d586f7f645f75e13de` |

**生产快照（交接时点）**：

- `butler-v5-gateway.service`：**active**
- `curl http://127.0.0.1:3000/healthz` → `{"status":"ok","wiring":"v5"}`
- `BUTLER_V5_DB=postgres`（Docker）；`~/.butler/v5-data/` **不存在**
- Todoist MCP 已用仓库 spec（gateway 日志可见 `config/openapi/todoist-v1-readonly.yml`）
- 最新相关 commit：`4125fcf2`

---

## 2. 下一班目标（D1 执行日 = 今天）

**Owner 意图**：在 **2026-08-25** 完成原定于 2026-09-18 的 `~/.butler/` 清理（非整仓误删）。

成功标准：

1. v5 gateway / 微信 / PK / MCP 删除后仍正常
2. `~/.butler/` 已删除或仅剩 Owner 明确保留的空壳
3. 保留决策文档更新为 **EXECUTED**
4. `.blackboard/state.md` 反映 D1 完成

---

## 3. 删除范围（必读）

### 3.1 本次要删

```text
~/.butler/          # v4 运行时主目录（~88 MB）
```

建议 **分块删**（§4），每步后 `healthz`；全部 v4 子树确认无回归后再 `rm -rf ~/.butler`。

### 3.2 绝对不要删

| 路径 | 原因 |
| --- | --- |
| `~/.config/butler-v5/` | v5 生产 env、ilink-sync、**新** audit JSONL |
| `~/backup-butler-home-20260825.tgz` | 全量回滚 |
| `~/backup-butler-v4-memory-20260825.tgz` | memory 只读归档 |
| `{WFXM}/.butler/ilink-media/` | 微信媒体缓存（workspace 相对） |
| `{WFXM}/.butler/` 其他 | 仓库内示例/报告（非 home） |
| `{WFXM}/butler-v5/.butler/` | v5 开发守卫 |
| `projects/LingWen1/.butler/` | 项目级 runtime |
| Postgres `butler_v5` | v5 主库 |

### 3.3 v5 代码与 `~/.butler` 关系（删除安全）

| 曾依赖 | 现状 |
| --- | --- |
| Todoist MCP openapi | ✅ 仓库 `butler-v5/config/openapi/` |
| Subagent audit JSONL | ✅ `~/.config/butler-v5/audit/subagent.jsonl` |
| PGlite 默认目录 | 生产用 Postgres；`~/.butler/v5-data` 本机不存在 |
| iLink media | `{WORKSPACE}/.butler/ilink-media` |

删除后 **仅 v4 legacy 脚本**（`scripts/butler-*-preflight.sh` 等）读 `~/.butler/mcp.yaml` 会失败 — 预期，标 legacy 即可。

---

## 4. 执行步骤（建议顺序）

### 4.1 删除前 smoke（必须）

```bash
curl -s http://127.0.0.1:3000/healthz
systemctl --user is-active butler-v5-gateway.service

cd /home/ailearn/projects/WFXM/butler-v5 && pnpm test   # 可选但推荐
node /home/ailearn/projects/WFXM/butler-v5/scripts/cutover/smoke-project-knowledge.mjs

# 备份再验一遍
sha256sum -c ~/backup-butler-home-20260825.tgz.sha256
sha256sum -c ~/backup-butler-v4-memory-20260825.tgz.sha256
```

微信：发一句简单消息，确认有回复（真机点验）。

MCP（若 `BUTLER_V5_MCP_ENABLED=1`）：确认 Todoist `lst-projects` 或 gateway 日志无 openapi 路径错误。

### 4.2 分块删除 v4 子树

```bash
B="$HOME/.butler"

# 大块 v4 数据（v5 不读）
rm -rf "$B/tenants" "$B/sessions" "$B/runtime" "$B/vector_store"
rm -rf "$B/gateway_outbox" "$B/gateway_queue" "$B/metrics" "$B/drill" "$B/exports"

# 已迁移 / 已有备份
rm -rf "$B/openapi" "$B/audit"

# 配置与 SQLite 残留
rm -f  "$B/butler.db" "$B/mcp.yaml" "$B/config.yaml" "$B/secrets.yaml"
rm -f  "$B/config.yaml.bak" 2>/dev/null

# 每步后可选：curl -s http://127.0.0.1:3000/healthz
```

查看剩余：

```bash
du -sh ~/.butler 2>/dev/null; find ~/.butler -maxdepth 2 -type d 2>/dev/null
```

若仅剩空目录或无关小文件：

```bash
rm -rf ~/.butler
ls -la ~/.butler 2>&1   # 期望：No such file or directory
```

### 4.3 删除后 smoke（必须）

```bash
systemctl --user restart butler-v5-gateway.service
sleep 5
curl -s http://127.0.0.1:3000/healthz

node /home/ailearn/projects/WFXM/butler-v5/scripts/cutover/smoke-project-knowledge.mjs
```

检查新 audit 路径（subagent 若启用时会写；未启用则目录可能尚未创建）：

```bash
ls -la ~/.config/butler-v5/audit/ 2>/dev/null || echo "audit dir not yet created (OK if subagent off)"
```

微信再测一句；MCP Todoist 再点验（若启用）。

### 4.4 文档与黑板收尾

1. 更新 [`v4-butler-home-retention-2026-08-20.md`](../decisions/v4-butler-home-retention-2026-08-20.md)：`Status: EXECUTED (2026-08-25)`
2. 更新 [`v5-d1-butler-home-audit-2026-08-24.md`](v5-d1-butler-home-audit-2026-08-24.md) §7 D1 日勾选
3. 更新 `.blackboard/state.md`：主线改为「D1 Done」；下一步换 post-D1 项
4. commit + push（message 示例：`chore: mark D1 ~/.butler cleanup executed 2026-08-25`）

---

## 5. 回滚（若删除后异常）

```bash
# 全量恢复（会覆盖 ~/.butler）
tar xzf ~/backup-butler-home-20260825.tgz -C ~

# 仅 memory
tar xzf ~/backup-butler-v4-memory-20260825.tgz -C ~
cp -a ~/backup-butler-v4-memory-20260825/raw/* ~/.butler/tenants/default/memory/

systemctl --user restart butler-v5-gateway.service
```

回滚 **不会** 恢复 v5 Postgres 数据（本来就在 Docker）；只恢复 v4 文件树。

---

## 6. 不要做

- 不要删 §3.2 列出的路径
- 不要跑 `migration/v4-to-v5` stub 声称已迁移
- 不要在本任务中做 PK K2 / embedding
- 不要改受保护 v5 生产文件（除非 smoke 暴露 bug 且 Owner 授权）
- 不要 disable / 停 `butler-v5-gateway.service`

---

## 7. 新会话推荐开场 prompt

```text
读 .blackboard/state.md 和 docs/plans/active/v5-d1-execution-handoff-2026-08-25.md。
Owner 已授权今天执行 D1：按交接 §4 删除 ~/.butler/，删除前后跑 smoke，最后更新决策文档和黑板。
不要重复 prep #1–#5；备份已在 ~/backup-butler-home-20260825.tgz。
```

---

## 8. 相关链接

- 审计报告：[`v5-d1-butler-home-audit-2026-08-24.md`](v5-d1-butler-home-audit-2026-08-24.md)
- v5 生产架构：[`docs/architecture/v5-production-architecture-2026-08.md`](../../architecture/v5-production-architecture-2026-08.md)
- 备份脚本（legacy v4）：[`scripts/backup-butler-data.sh`](../../../scripts/backup-butler-data.sh)
- Gateway unit：`butler-v5/scripts/cutover/butler-v5-gateway.service`
