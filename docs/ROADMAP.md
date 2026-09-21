# Butler v5 — D-series 路线图

> **Version**: D78 (cycle 24) | **累计 ship**: 117 (post-D77) → 122 (post-D78) | **适用读者**: Owner / Cursor Agent / Claude Code
> **生成日期**: 2026-09-21
> **关系**:
> - 未来 P0-P4 优先级 → [`v5-post-boundary-roadmap-2026-08.md`](plans/active/v5-post-boundary-roadmap-2026-08.md)（v5 产品路线，**权威源**）
> - 已闭环 D-series 维度累计 → 本文件
> - 完整 changelog → [`../CHANGELOG.md`](../CHANGELOG.md)

---

## §1 D-series 累计（24 cycles / 117 ship → 122 ship）

> D-series = audit-driven ship cycles；从 **D22**（首条 cycle）到 **D78**（本批），共 **24 cycles / 117 ship**（D55→D77）+ **5 ship**（D78 本批）。

| Cycle # | ID | 维度 | 累计 | 关键 SHAs |
|---------|-----|------|------|-----------|
| 22 | D76 | OSS 门面 | 110 | `600c2975` CHANGELOG · `ea61f39f` CoC · `a69ebf7a` SECURITY · `e87f1c93` Issue 模板 · `dfa1b044` PR 模板 · `f5fc3a94` acceptance scenarios |
| 23 | D77 | 部署 + CI/CD + 加固 | 117 | `aa392db3` Dockerfile · `c4a729f8` release.yml · `4b085b82` dependabot · `29c99d67` compose · `4d423c11` health · `cea04051` hardening · `5054b4d1` scenarios |
| **24** | **D78** | **文档体系（5 件套）** | **122** | **ROADMAP / Mermaid / FAQ / docs index / AGENTS.md dedup（本批）** |

**节奏**: ~5.3 ship/cycle 平均。慢但稳，每 cycle = 单 audit-driven 闭环（raw findings → 5 ship → pause memo）。

> **节奏判据**: cycle 密度看 owner 撞点（D50 lesson: ship claim 用 last batch green 不可信，必须 fresh full）。

---

## §2 已闭环 D-series 架构锁定

来源：[`butler-v5/DESIGN.md`](../butler-v5/DESIGN.md) §3/§5/§6/§7/§10/§11/§12/§13/§17/§18/§20；D22-D38 全部 ✅，§14 13/14 first-class。

| § | 内容 | 状态 |
|---|------|------|
| §3 | 依赖方向与端口（硬规则） | ✅ |
| §5 | Domain（纯规则层） | ✅ |
| §6 | Application（编排层） | ✅ |
| §7 | Ports（端口，依赖向内） | ✅ |
| §10 | Governance 与副作用咽喉 | ✅ |
| §11 | 混合数据模型 | ✅ |
| §12 G1-G5 | §18 row 3 最后项 closure | ✅ |
| §13 | Persistence | ✅ |
| §17 | Event Sourcing | ✅ |
| §18 | Cross-actor | ✅ |
| §20 | KNOWN_ENTRY_POINTS（LLM + non-LLM 2-tier） | ✅ |

**视觉化**: → [`architecture/v5-current-state-diagrams.md`](architecture/v5-current-state-diagrams.md)（D78 T2）

---

## §3 维度 1: 部署 + CI/CD + 治理 ✅（D77 完成）

7 件套（D77 cycle 23）：

1. `Dockerfile` + `.dockerignore`（多阶段构建 + production deps）
2. `release.yml`（multi-arch + cosign + SBOM）
3. `dependabot.yml`（npm + github-actions + docker 三生态）
4. `docker-compose.yml`（butler service 加入）
5. `/health` endpoint（liveness + readiness + §20 NON_LLM 2-tier）
6. `production-hardening.md`（7 节 + 13 ❌ anti-patterns）
7. acceptance scenarios + methodology check（M15 docker-deploy）

> 详细 cycle memo: `.audit/D77/` + MEMORY.md "v5 Pause post-D77-FULL-CYCLE-2026-09-21"

---

## §4 维度 2: 功能验证（D79 候选）

**范围**（未定 cycle）：

- Demo deployment（公开可访问的 demo 实例）
- E2E 测试覆盖（playwright 或 Vercel Agent Browser）
- Self-hosting runbook（社区自托管指南）
- 真实 LLM v8+ 迭代（[`v5-real-llm-v8-iteration-2026-09.md`](plans/active/v5-real-llm-v8-iteration-2026-09.md)）

**前置依赖**: D77 维度 1 已完成（部署地基）。

---

## §5 维度 3: 文档体系 ✅（D78 本批完成）

5 件套（本 cycle 24）：

1. [`ROADMAP.md`](ROADMAP.md)（本文件）— D-series 累计 + 维度候选
2. [`architecture/v5-current-state-diagrams.md`](architecture/v5-current-state-diagrams.md) — 3 张 Mermaid 视觉架构图
3. [`FAQ.md`](FAQ.md) — owner 视角 9 段 FAQ
4. [`README.md`](README.md) §子目录速查 — 导航中心（已有基础上 +50 行）
5. [`../AGENTS.md`](../AGENTS.md) 整文件重写为索引 — 16K → < 200 行

---

## §6 维度 4: 长期演化（未定）

**占位**（D-series 之外）：

- multi-owner / multi-tenant 支持
- production-ready（vs 当前 self-hosted 单 owner）
- 商业化 / OSS 社区运营（D76 已铺 OSS 门面）

**不在 D-series scope**: 这些是产品演化方向，非 audit-driven cycle 范围。

---

## §7 跨文件指针

| 需求 | 读这里 |
|------|--------|
| D-series 历史 raw findings | `.audit/Dxx/raw-findings.json` |
| D-series 累计 ship 详情 | `MEMORY.md` "Recent Sessions" 段 |
| v5 产品路线（P0-P4） | [`v5-post-boundary-roadmap-2026-08.md`](plans/active/v5-post-boundary-roadmap-2026-08.md) |
| v5 目标架构 | [`../butler-v5/DESIGN.md`](../butler-v5/DESIGN.md) |
| v5 生产事实 | [`architecture/v5-production-architecture-2026-08.md`](architecture/v5-production-architecture-2026-08.md) |
| owner FAQ | [`FAQ.md`](FAQ.md) |
| 视觉架构图 | [`architecture/v5-current-state-diagrams.md`](architecture/v5-current-state-diagrams.md) |
| 文档分层手册 | [`DOCUMENTATION.md`](DOCUMENTATION.md) |
| 文档索引卡片 | [`README.md`](README.md) |
| AGENTS 入口 | [`../AGENTS.md`](../AGENTS.md) |

---

**End of ROADMAP** | D78 cycle 24 docs-batch | cycle 25+ 待 owner 撞点启动
