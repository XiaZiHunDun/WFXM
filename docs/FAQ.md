# Butler v5 — Owner FAQ（D78 新增）

> **Version**: D78 (cycle 24) | **适用读者**: Owner（产品视角，非开发者视角）
> **生成日期**: 2026-09-21
> **关系**:
> - 文档索引卡片 → [`README.md`](README.md)（「我要…」问答）
> - 文档分层手册 → [`DOCUMENTATION.md`](DOCUMENTATION.md)
> - D-series 路线 → [`ROADMAP.md`](ROADMAP.md)
> - 视觉架构图 → [`architecture/v5-current-state-diagrams.md`](architecture/v5-current-state-diagrams.md)

---

## §1 D-series 是什么

**D-series** = Butler v5 项目采用的 **audit-driven ship cycle** 方法论。从 D22（首条 cycle）到 D78（本批），共 **24 cycles / 117 ship** 累计。

每个 cycle 流程：raw findings（`.audit/Dxx/raw-findings.json`）→ 5 ship → pause memo（`MEMORY.md` + `project-pause-state-*.md`）→ next cycle 启动。

命名规则：`D` + 两位数字（22-78+）= cycle 编号；`T` + 数字（1-7）= cycle 内 commit 序号（如 D77 T1-T7 = 7 commits）。

> 详细节奏: [`ROADMAP.md` §1](ROADMAP.md)

---

## §2 为什么 audit-driven 而不是 LLM-judge

**核心原因：deterministic + reproducible + cost**。

- **deterministic**: audit 跑固定规则（typecheck / lint / knip / acceptance / methodology），多次结果一致
- **reproducible**: raw findings JSON 存盘，下批 reference 不需要重新跑
- **cost**: 单 cycle audit < $1 LLM cost；vs LLM-judge 评估需多模型多 round

**历史教训**: D48/D50 撞点验证本身（ship claim 用 last batch green 不可信，必须 fresh full）；LLM-judge 评估在 owner 视角缺乏稳定判据。

**audit 适合**: 工程治理（finding 类型化 / 跨文件 pattern / 重复检测 / 安全 / spec cohesion）。

**不适合**: 产品力（owner 撞点判断）/ 主观质量（设计感）/ LLM 输出质量（需 human-in-loop）。

---

## §3 117 ship 是快是慢

**答：节奏正常，慢但稳**。

- 平均 ~5.3 ship/cycle（D55→D77 共 23 cycles × ~5.3 ship）
- D77 首次 7-ship cycle（部署 7 件套一次性 ship）
- D78 本批 5-ship（文档体系）

**vs 全量 feature branch**：单 feature branch 全量上线 = 风险集中；D-series = 渐进 ship + 每 cycle 验证 + pause memo 反思。

**判据**: cycle 密度看 owner 撞点（撞点 = 触发 next cycle 的信号）；撞点不频繁 = 健康（说明上一 cycle 已解决该维度问题）。

---

## §4 D77 的 7 件套是什么

**D77 cycle 23（部署 + CI/CD + 加固）7 件套**：

| # | 内容 | 用途 |
|---|------|------|
| 1 | `Dockerfile` + `.dockerignore` | 多阶段构建 + production deps |
| 2 | `release.yml` | multi-arch + cosign + SBOM |
| 3 | `dependabot.yml` | npm + github-actions + docker 三生态自动更新 |
| 4 | `docker-compose.yml` | butler service 加入 + healthcheck + resource limits |
| 5 | `/health` endpoint | liveness + readiness + §20 NON_LLM 2-tier |
| 6 | `production-hardening.md` | 7 节加固指南 + 13 ❌ anti-patterns |
| 7 | acceptance scenarios + M15 | 部署 acceptance 验证 + methodology check |

**累计**: 117 ship（D55→D77 共 23 cycles）。

> 详情: MEMORY.md "v5 Pause post-D77-FULL-CYCLE-2026-09-21" + `.audit/D77/` 8 commits

---

## §5 为什么 D-series 跨度这么大（D22→D78 = 1 cycle 多）

**答：cycle ≠ 1 天；cycle = 单 audit-driven 闭环**。

- 24 cycles 跨约 4 周（2026-08-22 → 2026-09-21）
- 每 cycle 实际耗时取决于：raw findings 数量 + owner 撞点节奏 + ship 验证
- D-series 不是时间维度，是**任务维度**

**密度**: D65-D68 连续 4 batch（Path C 第 1-4 批）= 高密度；D74-D75 间隔 = 等待 owner 撞点。

---

## §6 OSS 5 件套（CoC/SECURITY/Issue/PR/CHANGELOG）何时加的

**D76 cycle 22**（2026-09-21）一次性 ship：

1. `CHANGELOG.md`（D55→D75 回填 128 行 / 103 entries）
2. `CODE_OF_CONDUCT.md`
3. `SECURITY.md`
4. `.github/ISSUE_TEMPLATE/`（3 个模板）
5. `.github/PULL_REQUEST_TEMPLATE.md`

**T5.1 fix**: M14（accept scenarios 文件缺失）+ methodology check 锁 cycle gates。

> 详情: MEMORY.md "v5 Pause post-D76-FULL-CYCLE-2026-09-21"

---

## §7 怎么读 D-series pause memo

**三步读法**：

1. **入口**: `MEMORY.md` "Recent Sessions (2026-09-14..21)" 段 → 找最近 cycle memo
2. **链接**: 点击 → `project-pause-state-post-Dxx-FULL-CYCLE-YYYY-MM-DD.md`
3. **细节**: pause memo 包含 cycle # / 累计 ship / commits 表格 / gates / lessons / memory 写入

**raw findings**: `.audit/Dxx/raw-findings.json`（每 cycle 必存盘；D57 lesson #1 protocol）

**fix memos**: `project-fix-Dxx-Tn-YYYY-MM-DD.md`（每个 ship 单独记录）

---

## §8 维度 2/3/4 是什么

详见 [`ROADMAP.md`](ROADMAP.md)：

- **维度 1** ✅：部署 + CI/CD + 治理（D77 完成）
- **维度 2**：功能验证（D79 候选：Demo + E2E + self-hosting）
- **维度 3** ✅：文档体系（D78 本批完成 = ROADMAP + Mermaid + FAQ + docs index + AGENTS.md dedup）
- **维度 4**：长期演化（multi-owner / production-ready / 商业化）

---

## §9 AGENTS.md / CLAUDE.md / MEMORY.md 三者关系

| 文件 | 范围 | 何时读 | 谁维护 |
|------|------|--------|--------|
| `CLAUDE.md` (`~/.claude/CLAUDE.md`) | 全局（所有项目） | 每个会话开始 | Owner 全局偏好 |
| `AGENTS.md` (项目根) | Butler v5 项目 | AI 工具启动 | Owner + Agent 协作 |
| `MEMORY.md` (`~/.claude/projects/.../memory/`) | 本项目 session 记忆 | 撞点 / 交接 | Auto-memory |

**新会话 30 秒**：读 `.blackboard/state.md` → `MEMORY.md` "Current State" → `AGENTS.md` 必读表 → 撞点决定读哪。

---

## §10 怎么贡献 / 撞点

**撞点流程**（5 步）：

1. owner 撞点（产品 / 安全 / 性能 / 设计）→ 看 MEMORY.md 最近 cycle memo
2. 决定启动方式：`audit Dxx`（新 cycle）/ `ship Dxx Tn ...`（按已知 fix）/ `pause Dxx`（暂停总结）
3. raw findings 存盘：`.audit/Dxx/raw-findings.json`
4. ship 模板：1 file 1 commit（per D77 7-ship 模式）
5. pause 模板：MEMORY.md 更新 + project-pause-state memo

**AI 工具协作约束**：见 [`../AGENTS.md`](../AGENTS.md) §3（撞点流程）+ `butler-v5/AGENTS.md`（v5 代码约束）。

---

**End of FAQ** | D78 T3 | 10 段 owner 视角 FAQ
