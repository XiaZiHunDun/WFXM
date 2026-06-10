# 诊断入口矩阵（Phase C1）

> **状态**：2026-06-09  
> **用途**：区分三个名称相近的诊断入口，避免「发了 `/doctor` 以为看了模型/记忆」。  
> **关联**：[`health_report.py`](../../butler/ops/health_report.py) · [`butler/cli/doctor.py`](../../butler/cli/doctor.py) · [`security_audit.py`](../../butler/ops/security_audit.py)

---

## 1. 一句话对照

| 入口 | 场景 | 看什么 | 不看什么 |
|------|------|--------|----------|
| **微信 `/诊断`**（`/health`） | 运维排障、会话内自查 | 当前会话记忆/模型/队列/轮次/成本/边界观测 | 不是纯安全审计 |
| **`butler doctor`**（CLI） | 部署验收、发版前机器检查 | 目录、依赖、凭证、embedding 探活、模型 effective（无项目 L2） | 无微信会话、无当前项目绑定 |
| **微信 `/doctor`** | 安全审计 | **仅** `run_security_audit` 文本报告 | 不含记忆分层、模型块、队列 |

---

## 2. 详细对比

### 2.1 微信 `/诊断` / `/health`

- **实现**：`butler/gateway/commands/info_commands.py` → `build_health_report()`（`butler/ops/health_report.py`）
- **上下文**：绑定 `session_key`、当前激活项目、`orchestrator` 与上轮 `health` 快照
- **典型块**（有轮次后更全）：
  - 记忆分层、向量索引、混合权重、预取缓存（`memory/diagnostics.py`）
  - 默认项目策略、项目元数据（pack / Lead / lifecycle）
  - 有效模型（含 **project.yaml L2**）、runtime jobs、RAG、实验、用量/成本 rollup
  - 上下文预算、压缩状态、委派 stale、入站队列、出站推送、Harness 对标
  - eval 质量、诚实边界 G1/G2、stream probe、provider 熔断
- **别名**：`/health` 与 `/诊断` 同一 handler
- **Owner**：不要求（与会话内普通命令一致）

### 2.2 `butler doctor`（CLI）

- **实现**：`butler/cli/doctor.py` → `cmd_doctor`
- **上下文**：本机 `BUTLER_HOME`、可选「第一个含 `AGENTS.md` 的项目目录」作安全审计 workspace
- **典型块**：
  - `[数据目录]` `sessions` / `runtime` / `gateway` …
  - `[核心/可选依赖]` pip 包探测
  - `[配置]` `.env`、`MINIMAX_API_KEY`、`secrets.yaml` 状态行
  - `[观测演化 L7]` LangFuse、embedding provider、Recall@3 探活
  - `[开发质量 O7/O9]`、`[诚实边界 G1/G2]`
  - `[有效模型]` `format_model_diagnostic_lines(project=None)` — **无当前微信项目**
  - `[安全审计]` 与微信 `/doctor` 同源 `format_audit_report`
- **退出码**：存在 `critical` 级审计项时返回 `1`

### 2.3 微信 `/doctor`

- **实现**：`butler/gateway/commands/lifecycle_commands.py` → `_cmd_doctor`
- **内容**：**只有** `format_audit_report(run_security_audit(workspace=当前项目 workspace))`
- **Owner**：`require_owner` 门控
- **与 CLI doctor 区别**：不含依赖/目录/模型/记忆；与 `/诊断` 区别：不含运行态与会话诊断

---

## 3. 何时用哪个

```text
会话里「怎么突然压缩了 / 模型不对 / 队列堵了」  →  /诊断
新机部署、CI、发版前「目录和 key 齐不齐」         →  butler doctor
「终端开着吗 / permissions 松不松 / 工作区风险」  →  /doctor（Owner）
```

---

## 4. 维护说明

- 新增 `/诊断` 块：优先挂 `health_report._shared_diagnostic_lines` 或 `_turn_diagnostic_lines` 子模块，并在本文 §2.1 补一行。
- **不要**把全量 health 塞进 `/doctor`（保持安全审计单一职责）。
- CLI `doctor` 与微信 `/诊断` 可复用同一格式化函数（如 `format_eval_quality_lines`），但须在本文注明是否含 **project L2**。

---

## 5. 修订记录

| 日期 | 变更 |
|------|------|
| 2026-06-09 | Phase C1 初稿 |
