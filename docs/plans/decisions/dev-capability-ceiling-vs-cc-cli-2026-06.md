# ADR — Dev 能力上限：对标 Claude Code CLI（非 Cursor IDE）

> **状态**：已采纳（2026-06-23）  
> **实现 SSOT**：`butler/core/agent_loop.py`、`butler/tools/delegate_*`、`butler/dev_engine/`  
> **对照 SSOT**：[`cc-butler-gap-analysis-2026-05.md`](../active/cc-butler-gap-analysis-2026-05.md)  
> **产品边界**：[`roadmap-backlog-and-boundaries-2026-05.md`](roadmap-backlog-and-boundaries-2026-05.md) · [`wechat-core-scenario.md`](../../guides/wechat-core-scenario.md)

---

## 1. 问题

- 此前讨论 Dev「达不到 Cursor 级」时，混入了 **IDE 专有层**（LSP、内联 diff、多 tab、图形 merge）。
- Butler 主路径是 **微信远程管家 + 多项目 Lead → 委派 dev/content/review**；本机 Claude Code / Cursor 在文档中为 **主机工具**，不登记为 Butler 项目类型。
- 需要明确：**Dev 能力应对标谁、上限在哪、什么不必追**。

## 2. 决策

### 2.1 对标对象

| 不对标 | 对标 |
|--------|------|
| **Cursor IDE Agent**（LSP、@codebase UI、实时代码树） | **Claude Code CLI**（Loop + 工具 + 终端 + 子代理） |

**一句话上限**：

> Butler Dev ≈ **带门控与记忆的「远程 Claude Code 子会话」**；上限由白名单 terminal、委派深度、微信回合延迟决定，**不由 IDE 能力决定**。

### 2.2 三层上限

| 层 | CC CLI | Butler dev 委派 | 结论 |
|----|--------|-----------------|------|
| **机械层** | 近似完整 shell + git + MCP Host | workspace 读写 + argv 白名单 terminal + 可选 git；无 push/MCP Host | **刻意更低**（远程低信任） |
| **LLM/编排层** | 本机连续多轮 patch→test→fix | CC 线束 P0–P4 已对齐；多一层 Lead 委派与微信摘要 | **近 parity**；差在回合延迟与飞轮证据 |
| **产品层** | 单目录、开发者自用 | 多项目、Owner 门控、结构化报告、跨会话记忆 | **Butler 可更高** |

### 2.3 能力矩阵（摘要）

| 维度 | CC CLI | Butler dev | 判定 |
|------|--------|------------|------|
| Agent 循环 / 上下文经济学 | micro + spill + compact | 同赛道（CC 线束 ✅） | 近 parity |
| 编辑 | 多策略 | `patch` + read_state + dev_engine | 中 gap（multi-hunk 事务） |
| 搜索 | rg + 探索 | `search_files`（rg） | 小–中 gap |
| 终端 | 高自由度 | `BUTLER_TERMINAL_PROFILE=dev` 白名单 | **产品否决**全 shell |
| 验证 | 自主 TDD | dev_engine PLAN→VERIFY（opt-in） | 中 gap（依赖 env） |
| 子代理 | Task / runAgent | `delegate_task` depth≤2 | 各有优势 |
| MCP | 一等 Host | 薄客户端 opt-in | CC 更强；Butler 不做 Host |
| 记忆 / 多项目 | 弱 | L3/L4 经验 + MT3 记忆 | **Butler 优势** |

完整矩阵见 [`v4-dev-engine-theory.md`](../../architecture/v4-dev-engine-theory.md) §4.1；CC 对照见 [`cc-butler-gap-analysis`](../active/cc-butler-gap-analysis-2026-05.md) §2、§9。

### 2.4 与本机 CC 的关系

- **互补，非替代**：重编码任务在本机 CC；Butler 负责派工、验收摘要、记忆、提醒与多项目编排。
- **不立项**：把 CC/Cursor 嵌进 Loop 替代 `delegate_task`（见 §3 否决延续）。

## 3. 否决（延续 — 勿立项）

除非书面变更产品边界，下列 **不对标 CC CLI _full_ 也仍不做**：

| 项 | 原因 |
|----|------|
| 无限制 shell（`\|`、`bash -c`、push/pull） | 远程破坏面 |
| 全量 MCP Host | [`roadmap-backlog` §1.3](roadmap-backlog-and-boundaries-2026-05.md) |
| IDE / LSP / 实时代码树 | 非微信管家形态 |
| Prompt 管理平台（ToT/APE 全自动） | [`roadmap-backlog` S7](roadmap-backlog-and-boundaries-2026-05.md) |

## 4. 可选 Backlog（对标 CC CLI 的 ROI 项）

**未承诺排期**；立项须写验收标准与 `BUTLER_*` 开关。

| 优先级 | 项 | 验收 |
|--------|-----|------|
| P1 | **真机 dev 飞轮** | 微信委派 dev → patch → pytest（terminal dev profile）→ 摘要；非 B9 生产证据 |
| P1 | **project.yaml 标准 dev 命令** | `dev.test_command` / `lint_command` 驱动 VERIFY，少靠 LLM 猜 |
| P2 | **B9 / 经验 playbooks** | 委派 rescue、路径错误等写入 L3/L4 并可检索 |
| P2 | **Lead 越权压降** | workflow/只读类任务 `delegate_task` 率；handler sim `require_tools` |
| P3 | **本机 CC 桥接（可选）** | 重任务 Owner `/批准` 后本机 CC 执行，Butler 只收报告 |

**已落地守门（2026-06-23）**：

```bash
bash scripts/butler-wechat-dev-delegate-sim.sh --track lingwen   # 4/4 handler
bash scripts/butler-wechat-dev-delegate-sim.sh --quick
bash scripts/butler-dev-delegate-experience-probe.sh           # L3/L4 信息探针
PYTHONPATH=. pytest tests/test_verify_layered.py -q            # project.yaml → VERIFY
```

**P1 project.yaml VERIFY（2026-06-23）**：`butler/dev_engine/verify.py` 的 `verify_test` / `verify_lint` / `verify_build` 优先读取工作区 `project.yaml` → `dev.test_command` / `lint_command` / `build_command`（与 `/测试` 同 cwd + `PYTHONPATH=repo_root`）；未配置时 fallback 原有 pytest/ruff 逻辑。

**P1 真机飞轮运营（2026-06-23）**：

```bash
bash scripts/butler-dev-live-flywheel-checklist.sh        # env + project.yaml（exit 2=缺 env）
bash scripts/butler-dev-live-flywheel-checklist.sh --probe  # + 试点 VERIFY 探针
```

节奏：每月 `butler-wechat-dev-delegate-sim.sh --track lingwen` + `pilot-log`；每周 `butler-prod-delta-observe.sh` + `butler-lingwen-live-capture-checklist.sh`；每日 `butler-ops-followup-check.sh`。

**P2 playbooks + Lead 越权（2026-06-23）**：

```bash
bash scripts/butler-prod-playbook-seed.sh --apply     # L4 PROD_PLAYBOOK_*（rescue/path/read_state）
bash scripts/butler-wechat-lead-readonly-sim.sh --quick  # Lead 厂情禁 delegate_task
```

`prod_playbook_seeds` 注入 `build_production_delegate_blocks`；`/测试` 与 VERIFY 共用 `project_dev_subprocess_env()`。

**P3 CC 桥接（暂缓）**：见 [`dev-cc-bridge-optional-2026-06.md`](dev-cc-bridge-optional-2026-06.md) — 不立项；重任务仍走委派飞轮。

**G1-04 生产证据（2026-06-23）**：

- 真机 dev 委派成功/失败 → `eval_feedback` trigger `prod_delegate_verify_pass` / `prod_delegate_failure`（`BUTLER_EVAL_PROD_EVIDENCE=1`）
- 核对：`bash scripts/butler-dev-prod-evidence-checklist.sh`

```bash
# 网关推荐 .env（真机 terminal dev）
BUTLER_DEV_ENGINE=1
BUTLER_ENABLE_TERMINAL=1
BUTLER_TERMINAL_PROFILE=dev
BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES=1
BUTLER_EVAL_PROD_EVIDENCE=1
```

## 5. Agent 引用规则

- 讨论 **Dev 能力上限** → 引用 **本文**，勿用「Cursor 级」作默认参照。
- 讨论 **Loop/上下文/线束** → [`cc-butler-gap-analysis`](../active/cc-butler-gap-analysis-2026-05.md)（已收口 P0–P4）。
- 讨论 **工具/terminal/git 细节** → [`dev-ops-tools-design.md`](../../architecture/dev-ops-tools-design.md)。
- 提新 Dev 需求 → 先过 [`roadmap-backlog` §0 决策流](roadmap-backlog-and-boundaries-2026-05.md)。

## 6. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-06-23 | 初版：主公确认 Dev 对标 CC CLI 非 Cursor；纳入 sim 守门与 Backlog 五项 |
| 2026-06-23 | P1：`verify_test`/`verify_lint` 接入 `project.yaml` dev 命令 |
| 2026-06-23 | P1 飞轮：`butler-dev-live-flywheel-checklist.sh` + LingWen dev 路径修正 + `verify_build` |
| 2026-06-23 | P2：`prod_playbook_seeds` + Lead 只读 sim + gateway `/测试` env 对齐 |
| 2026-06-23 | P3 一页纸 + G1-04 `prod_delegate_*` 生产证据接线 |
