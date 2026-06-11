# 记忆模块运维与效果提升

> 个人管家试点：开满语义记忆 + 预取，用运维表与冒烟话术验证「记得住、记得准」。

## 两阶段落地（推荐顺序）

| 阶段 | 脚本 | 内容 |
|------|------|------|
| **A** 基建 | `bash scripts/butler-memory-phase-a.sh` | `SEMANTIC_MEMORY=1` + fastembed + reindex + MB1–MB7（**隔离 tmp**，不污染经验库）+ doctor |
| **B** 运营 | `bash scripts/butler-memory-phase-b.sh` | `SYNC_CONVERSATION=0` + queue_prefetch + recall 冒烟 + 微信 M1–M7 话术 |
| **C** 工程 | `bash scripts/butler-memory-phase-c.sh` | `add_experience` IndexSync + 向量陈旧检测 + 守门 pytest |
| **种子** 经验指针 | `butler memory seed` 或 `bash scripts/butler-memory-seed-owner-experiences.sh` | 清理 MB5 filler + 写入 `skill:`/`tool:` 种子（幂等） |

发版 / 升级记忆模块后：**先 A 再 B 再 C**；网关改 `.env` 后需 `systemctl restart butler-gateway`。

**ChromaDB**：`butler/memory/vector_store.py` 未接入主召回链；生产语义检索走 `SemanticMemoryIndex`（`memory_vectors.db`）。

**Skill 与经验**：默认 `BUTLER_SKILL_INJECTION_MODE=fallback` — 有经验召回时跳过未验证 Skill 全文；经验可用指针点名：

| 指针 | 作用 |
|------|------|
| `skill:<kebab-name>` | 加载 Skill 正文；并 pin 其 `preferred_tools`（即使跳过正文） |
| `tool:<builtin_name>` | pin 内置工具（如 `tool:run_workflow`） |
| `mcp:<registered>` 或 `mcp:<server>/<tool>` | deferred MCP 下 promote 点名工具 |

见 [`memory-roadmap.md`](../architecture/memory-roadmap.md) §检索信任级联、§执行信任级联；全链路工程详设见 [`execution-surface-design.md`](../architecture/execution-surface-design.md)。

### 经验指针 Authoring（微信可照抄）

写入 `tags` 或 `content` 即可（与正文长度无关）：

| 场景 | 示例 tags / content 片段 |
|------|--------------------------|
| 发版走 workflow | `skill:lingwen-project-lead tool:run_workflow` |
| 记忆检索优先 | `tool:butler_recall` |
| GitHub MCP（需 `mcp.yaml`） | `mcp:github/search` 或 `mcp:mcp_github_search` |

**种子（幂等）**：`butler memory seed` — 见 `data/seed_owner_experiences.json`。

**技能 lint**：`butler skills lint`（有 triggers 缺 `preferred_tools` 时 warn，不阻断）。

**目录型 skill 同步**：`bash scripts/sync-project-skills.sh <slug>` — 扁平 `*.md` 与 `foo/SKILL.md`（写 `foo.md` stub + `foo/`）一并同步到 `.butler/skills/`。

### 级联验证话术（微信冒烟）

| # | 发送 | 期望 |
|---|------|------|
| C1 | `/诊断` | 执行面块含 `skill_injection_mode`、经验条数；有 MCP 时见连接行 |
| C2 | 问一句**已有经验覆盖**的流程（如「发版流程」） | 回复引用经验要点；**不**堆砌未验证 Skill 目录 |
| C3 | 同上后发 `/诊断` 或看 loop diagnostics | `experience_pinned_tools` ≥ 1；含 `run_workflow` 等 pin |
| C4 | `butler memory search "phase-c" --scope experience --verbose` | Top1 为种子 `owner-seed-memory-release`（常见 id **218**），`tags` 含 `tool:butler_recall` |
| C5 | 改 `BUTLER_SKILL_INJECTION_MODE=always` 后重启网关再问同句 | 应注入 Skill 正文（对照组）；测完改回 `fallback` |
| C6 | 经验含 `mcp:` 但未配置 MCP | `/诊断` 或 `experience_mcp_rejected` 提示 `mcp_disabled` / `tool_not_found` |

可选：`BUTLER_MCP_DEFERRED_SAME_TURN=1` — 经验 `mcp:` promote 后**同轮**可见 MCP schema（默认下一轮）。

**C4 CLI 示例**（需已执行 `butler memory seed`；`BUTLER_SEMANTIC_MEMORY=1`）：

```bash
# 推荐：记忆发版种子（#218）
butler memory search "phase-c" --scope experience --verbose
butler memory search "butler-memory-phase-c" --scope experience --verbose

# 对照：厂长 Lead 种子（#216，含 skill: + tool:）
butler memory search "lingwen-project-lead" --scope experience --verbose
```

| query | 常见 Top1 | C4 判定 |
|-------|-----------|---------|
| `phase-c` / `butler-memory-phase-c` | #218 `tool:butler_recall` | ✅ 推荐 |
| `lingwen-project-lead` | #216 `skill:lingwen-project-lead` + `tool:run_workflow` | ✅ |
| `发版` | #216 厂长种子（非记忆发版） | ⚠️ 有指针但易误判 |
| `记忆模块发版` / `记忆模块发版流程` | #54/#107 bench filler，**无 tags** | ❌ 勿用 |

`--verbose` 应看到 `mode: hybrid`（或 `fts`）且 Top1 为 `experience:218` 一类种子行；查 `tags` 用 `--json`（`results[0].tags` 须含 `skill:` 或 `tool:`）。若长期只有 bench filler，先 `butler memory seed` 再 `bash scripts/butler-memory-reindex.sh`。

灵文试点写入边界与 O1–O8：[`projects/LingWen1/docs/memory-guide.md`](../../projects/LingWen1/docs/memory-guide.md)。

## 生产推荐 `.env`

| 变量 | 推荐 |
|------|------|
| `BUTLER_SEMANTIC_MEMORY` | `1` |
| `BUTLER_QUEUE_PREFETCH` | `1` |
| `BUTLER_SYNC_CONVERSATION_MEMORY` | `0` |
| `BUTLER_MEMORY_HALF_LIFE_DAYS` | `30`（检索时间衰减） |
| `BUTLER_MEMORY_ACCESS_BOOST` | `0.12`（访问次数加权） |

详见 [`.env.example`](../../.env.example) 与 [`memory-roadmap.md`](../architecture/memory-roadmap.md)。

## 效果度量（D2-4/D2-5）

微信 `/诊断` 展示 **记忆效果度量 (L2)**：`S_w` 写入存活率、`H_1` 首轮命中率、`E_d` 衰减误杀率。

```bash
bash scripts/butler-memory-metrics-smoke.sh
# CLI 工具
butler memory metrics   # 若已注册；或 agent 调用 butler_memory_metrics
```

持久化路径：`~/.butler/metrics/memory_metrics.json`（`BUTLER_MEMORY_METRICS_PERSIST=1` 默认开）

## 命令速查

| 命令 | 作用 |
|------|------|
| `butler memory search "<词>" --verbose` | CLI 检索调试：mode、fallback、chunk_id、混合权重 |
| `/诊断` | 向量条数、画像向量、三元组条数、衰减参数、最近检索 telemetry |
| `/记忆图谱` | 三元组只读展示（不参与检索） |
| `/记忆待审` / `/批准记忆` / `/拒绝记忆` | Pending 审批 |

## 发版 / 升级后必做

部署或合并记忆相关代码后，在仓库根目录执行一次（需 `.env` 中 `BUTLER_SEMANTIC_MEMORY=1`）：

```bash
bash scripts/butler-memory-reindex.sh
```

会重建 `memory_vectors.db`、Owner 画像向量、三元组表，并刷新各项目 `facts.json`。期望输出含 `ok: true`。

## 脚本

```bash
butler memory search "某项目决策" --scope project --verbose
butler memory search "pytest" --scope experience --json
bash scripts/butler-memory-smoke.sh      # recall fixture 回归
bash scripts/butler-memory-reindex.sh    # 重建向量（改 MEMORY / 升级记忆模块后）
# 等价: butler memory reindex
```

## 灵文1号试点

完整写入边界、运维检查表 O1–O6、微信冒烟 M1–M7：[`projects/LingWen1/docs/memory-guide.md`](../../projects/LingWen1/docs/memory-guide.md)。

## `/新对话` 行为

- 清空**本轮** Agent 上下文与会话回声
- **保留** Owner 画像、项目 MEMORY、经验库
- 对话足够长时可能提示「已提炼：长期记忆 +N 条」
