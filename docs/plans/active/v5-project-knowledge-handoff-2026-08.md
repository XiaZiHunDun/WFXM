# Butler v5 Project Knowledge — 会话交接（2026-08-24）

> **状态**：K1 + K1.1 **Done**（生产已启用 + 微信 smoke 验收）  
> **立项 SSOT**：[`v5-project-knowledge-proposal-2026-08.md`](v5-project-knowledge-proposal-2026-08.md)  
> **生产事实**：[`v5-production-architecture-2026-08.md`](../../architecture/v5-production-architecture-2026-08.md) §6.0b–c  
> **路线图**：[`v5-post-boundary-roadmap-2026-08.md`](v5-post-boundary-roadmap-2026-08.md)  
> **黑板快照**：`.blackboard/state.md`

---

## 1. 下一会话开篇 30 秒

1. 读 `.blackboard/state.md`
2. 读本文 §2–§5（已完成 / 生产 / 验收 / 不要做）
3. 若要做**新能力**：先读 [`v5-product-boundaries-2026-08.md`](../decisions/v5-product-boundaries-2026-08.md)，**单独立项**，勿从 PK 会话顺手扩面
4. 改 `butler-v5/` 后：`cd butler-v5 && pnpm test`

---

## 2. 本线已完成（勿重复做）

| 阶段 | 交付 | 验收 |
| --- | --- | --- |
| **K1 MVP** | migration `0010`、`project_knowledge_items`、Owner API/CLI、`recall_project_knowledge`、Document promote 级联 | `pnpm test`；[`owner-project-knowledge-routes.test.ts`](../../../butler-v5/apps/api/src/owner-project-knowledge-routes.test.ts) |
| **K1.1** | `config/project-knowledge-sources.json`、sync 引擎、watch worker（5min）、markitdown chain | [`project-knowledge-sync.test.ts`](../../../butler-v5/apps/api/src/project-knowledge-sync.test.ts) |
| **生产 cutover** | inject fallback（query 无命中 → 最近 ingest）、`enable-project-knowledge-prod.sh` | env 三件套已开（见 §3） |
| **PDF markitdownGlobs** | scoped glob 修复；`tests/fixtures/ext5/*.pdf` → `ingested_document` | gateway 重启后 watch：`scanned=8, created=1` |
| **Sources 扩展** | + `butler-v5/AGENTS.md`、`v5-engineering-handoff` | sync：`scanned=10, created=2` |
| **微信验收** | inject（0 toolCalls → Accepted）+ `recall_project_knowledge` 工具链 | [`smoke-project-knowledge.mjs`](../../../butler-v5/scripts/cutover/smoke-project-knowledge.mjs) PASS |

**相关 commit（`main`）**：

```text
472e92fe  chore: blackboard after PK wechat smoke
7d15dd8b  test(v5): WeChat PK inject/recall smoke and expanded sources
c329105e  feat(v5): PDF markitdownGlobs ingest with scoped glob expansion
973bde39  feat(v5): enable PK working-set inject fallback and prod cutover
5c5cad00  feat(v5): Project Knowledge K1.1 — sources watch and markitdown chain
a90b175f  feat(v5): Project Knowledge K1 MVP
```

立项文档 §7 验收清单 **已全部 [x]**。

---

## 3. 生产现状

### 3.1 Gateway

- 服务：`systemctl --user status butler-v5-gateway.service`（模板见 `butler-v5/scripts/cutover/butler-v5-gateway.service`）
- API：`http://127.0.0.1:3000`
- v5 CLI：`cd butler-v5 && npx tsx cli/src/index.ts …`（**不要**用 miniconda 的 v4 `butler`）

### 3.2 环境变量（`~/.config/butler-v5/env`）

| 变量 | 生产值 | 含义 |
| --- | --- | --- |
| `BUTLER_V5_PROJECT_KNOWLEDGE` | `1` | 工作集 prefix 注入 |
| `BUTLER_V5_PROJECT_KNOWLEDGE_WATCH` | `1` | sources manifest 周期 sync |
| `BUTLER_V5_PROJECT_KNOWLEDGE_SOURCES_PATH` | `config/project-knowledge-sources.json` | 相对 `butler-v5/` |
| `BUTLER_V5_WORKSPACE_ROOT` | `/home/ailearn/projects/WFXM` | workspace 根 |

改 env 后：`systemctl --user restart butler-v5-gateway.service`

启用脚本（幂等）：`butler-v5/scripts/cutover/enable-project-knowledge-prod.sh`

### 3.3 数据面

- 表：`project_knowledge_items`（migration `0010_project_knowledge.sql`）
- 项目：**WFXM**；约 **14 条**（7 file_snapshot + 1 PDF ingested + 若干 manual/promote）
- sources 清单：[`butler-v5/config/project-knowledge-sources.json`](../../../butler-v5/config/project-knowledge-sources.json)
  - 9 text globs + 2 markitdownGlobs（`docs/**/*.pdf` 当前无匹配文件）

### 3.4 调用链（事实）

```text
微信/CLI inbound
  → runButlerLoop (wechat-inbound-butler.ts)
  → loadProjectKnowledgeSystemPrefix (opt-in inject)
  → recall_project_knowledge 工具（低风险 read，Allow）
sources watch / Owner sync
  → syncProjectKnowledgeFromManifest
  → text: file_snapshot | PDF: mcp_markitdown_convert_to_markdown → document → ingested_document
```

Sync 走 Owner 路径，**绕过 Policy**（直接 `tool.run`）。

---

## 4. 验收命令（下一班可先跑）

```bash
# 健康
curl -s http://127.0.0.1:3000/healthz

# PK CRUD / 列表
cd /home/ailearn/projects/WFXM/butler-v5
npx tsx cli/src/index.ts project-knowledge list --project WFXM

# 手动 sync（等同 Owner POST .../sync）
npx tsx cli/src/index.ts project-knowledge sync

# 微信 loopback smoke（需真实 LLM + PK=1）
node scripts/cutover/smoke-project-knowledge.mjs

# 单测子集
pnpm exec vitest run \
  apps/api/src/wechat-inbound-butler.test.ts \
  apps/api/src/project-knowledge-sync.test.ts \
  apps/api/src/project-knowledge-glob.test.ts \
  packages/domain/src/knowledge/project-knowledge-sources.test.ts
```

**真机微信（可选）**：

1. Inject：「WFXM Project Knowledge 立项是什么状态？」→ 期望 **Accepted**， ideally 0 toolCalls  
2. Recall：「manual note 里 MCP 生产拓扑一共几个 tools？」→ 期望 **22** 或调用 `recall_project_knowledge`

---

## 5. 关键文件索引

| 路径 | 作用 |
| --- | --- |
| `butler-v5/config/project-knowledge-sources.json` | ingest 白名单 globs |
| `butler-v5/apps/api/src/project-knowledge-sync.ts` | sync 引擎 |
| `butler-v5/apps/api/src/project-knowledge-glob.ts` | glob 展开（scoped 目录） |
| `butler-v5/apps/api/src/project-knowledge-inject.ts` | 工作集 prefix 注入 |
| `butler-v5/apps/api/src/project-knowledge-watch-worker.ts` | 5min watch |
| `butler-v5/apps/api/src/wechat-inbound-butler.ts` | inject 接线 + traces |
| `butler-v5/apps/api/src/tools.ts` | `recall_project_knowledge` |
| `butler-v5/packages/domain/src/knowledge/project-knowledge.ts` | 领域类型 + working-set 选择 |
| `butler-v5/packages/persistence/src/project-knowledge-store.ts` | 持久化 |
| `butler-v5/scripts/cutover/smoke-project-knowledge.mjs` | 生产 smoke |
| `butler-v5/scripts/cutover/enable-project-knowledge-prod.sh` | 生产 env 启用 |

---

## 6. 不要做（硬边界）

- **embedding / 向量 / RAG Studio / 全盘 workspace 索引**
- **跨 project 联合检索**（MVP 单 projectId）
- **Agent 写 ingest 工具**（`ingest_project_file`）— 立项未做；写仍走 Owner API
- **把 Run 压缩摘要写入 PK**
- 从 v4 `search_project_knowledge` **机械移植**
- 删除 `~/.butler/` — **D1 日历 2026-09-18 前 Owner 再确认**（见 [`v5-r10-handoff.md`](../../architecture/v5-r10-handoff.md) §8.1）

---

## 7. 建议后续工作（任选，需 Owner 拍板）

Project Knowledge **无 K2 在 active backlog**。下一班常见方向：

| 优先级 | 方向 | 说明 |
| --- | --- | --- |
| **运营** | 扩 sources / 灵文1号 projectId | Owner 原话：灵文非 Day-1；按需加 `projects.LingWen` |
| **运营** | 真机微信话术复验 | smoke 已 PASS；手机侧可选 |
| **工程 P0** | AI guard / `.cursorrules` 与 v5 守卫收敛 | [`v5-ai-guard-migration-checklist-2026-08.md`](v5-ai-guard-migration-checklist-2026-08.md) 标 Done，根规则仍含 v4 项 |
| **工程 P0** | 未接线包归档决策 | [`v5-unwired-packages-inventory-2026-08.md`](v5-unwired-packages-inventory-2026-08.md) |
| **日历** | D1 删 `~/.butler/` | 2026-09-18 后 Owner 决策 |
| **按需立项** | 新 MCP / Channel / Extension R&D | 各走边界 + 单独立项 |

**明确不立项**：Web UI、Playwright 浏览器、RAG Studio（见产品边界 Owner 记录）。

---

## 8. 上一班一句话

PK 从立项到生产 inject/watch/PDF/微信 smoke 全闭环；下一班从 P0 工程收口或按需运营扩 sources 接，**不要**顺手开 embedding 或 K2。

---

## 9. 相关链接

- MCP 交接：[`v5-mcp-multi-server-handoff-2026-08.md`](v5-mcp-multi-server-handoff-2026-08.md)
- 验收交接（P4）：[`v5-acceptance-handoff-2026-08.md`](v5-acceptance-handoff-2026-08.md)
- 工程交接规约：[`v5-engineering-handoff-2026-08.md`](../decisions/v5-engineering-handoff-2026-08.md)
