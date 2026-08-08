# WFXM 项目最新状态报告

> **状态日期**：2026-08-08  
> **盘点范围**：主仓库 `/home/ailearn/projects/WFXM` 的当前 `main`、最近 30 个提交、未提交工作区、Butler v4 主线、`butler-v5/` 原型、测试与文档体系  
> **结论口径**：已提交代码、未提交代码、实验原型和规划文档分别标注，不将“文件存在”视为“已交付”  
> **文档性质**：阶段性项目状态快照，不替代架构 SSOT、配置 SSOT 或发布门禁

<!-- AUTO-GENERATED: START -->

## 1. 一页结论

WFXM 当前是一个以 **Butler v4** 为生产主线的多项目微信 AI 管家系统。主线采用 Python 3.11+、自建 Agent Loop、原生 iLink 微信网关、分层记忆、工具/Skill/MCP 扩展、委派代理和人工审批门控。

截至本次盘点，项目同时存在三种不同成熟度的资产：

| 资产 | 当前定位 | Git 状态 | 成熟度判断 |
|------|----------|----------|------------|
| `butler/`（Butler v4） | 当前产品与运行主线 | 已跟踪；另有大量未提交修改 | **Beta 主线，可运行，正在进行架构深化** |
| 当前 Python WIP | Effects、事件体系、Tool Registry、验证、Skill、预算与守卫扩展 | 多个 modified / untracked 文件 | **测试覆盖较强，但尚未形成可发布提交** |
| `butler-v5/` | TypeScript + Effect-TS 的 FC/IS 重构原型 | 整目录 untracked，主树无运行时引用 | **独立技术原型，不是当前主线，也不能视为已发布 v5** |

综合判断：

- **产品能力成熟度高于仓库收口成熟度**：v4 已有完整微信、CLI、Agent Loop、委派、记忆、权限、运维与评估体系。
- **当前工作区不是可直接发布状态**：存在大规模未提交代码、运行数据二进制变化、未跟踪 v5 原型和未完成的全门禁验证。
- **近期演进方向明确**：从“功能堆叠”转向配置收敛、Effects/ADT、事件溯源、持久化、类型安全、工具注册表与分层架构。
- **最大管理风险不是缺功能，而是多条演进线未完成边界决策**：Python v4 深化与 TypeScript v5 原型并行，但尚无已提交 ADR 明确“继续演进 v4、渐进迁移或正式切换”的决策。

## 2. 项目定位与产品边界

### 2.1 当前产品定位

Butler v4 是面向个人或小团队的 **自托管多项目 AI 管家**：用户通过微信或 CLI 发出自然语言/斜杠命令，主 Agent 负责理解意图、切换项目、调用工具、委派子 Agent、运行工作流，并通过分层记忆延续跨会话上下文。

典型路径：

```text
微信 / CLI
  → Gateway / CLI 入口
  → Orchestrator（提示词、模型、Skill、记忆）
  → Agent Loop（prepare → LLM → tools → finalize）
  → Tool / MCP / Delegate / Workflow
  → 审批、出站、报告、记忆与观测
```

### 2.2 明确边界

当前主线明确选择：

- 自建 Agent Loop，不依赖 Hermes `AIAgent`；
- 微信 iLink 是主要远程入口；
- 多项目 workspace 隔离，工具受路径与权限门控；
- MCP、向量库、OCR、语音、观测等按 optional extra 或配置启用；
- 文件/JSONL/MEMORY 是主要事实源，SQLite/ChromaDB 多用于索引、查询和派生状态；
- 不默认建设全量 MCP Host、多租户 SaaS、IDE 内置 Agent 或每会话重型容器平台。

## 3. 当前架构

### 3.1 九层模型

| 层 | 职责 | 当前主要路径 |
|----|------|--------------|
| L1 接入与交互 | 微信、CLI、消息收发与会话入口 | `butler/gateway/`、`butler/cli/`、`butler/main.py` |
| L2 编排与控制 | Agent 工厂、工作流、委派与运行时任务 | `butler/orchestrator/`、`butler/workflows/`、`butler/delegate/`、`butler/runtime/` |
| L3 认知推理环 | Agent Loop、上下文、压缩、工具批次、LLM 重试 | `butler/core/` |
| L4 工具与能力 | 内置工具、MCP、Skill、开发引擎 | `butler/tools/`、`butler/mcp/`、`butler/skills/`、`butler/dev_engine/` |
| L5 记忆与知识 | 项目记忆、向量检索、经验、Observation | `butler/memory/`、会话后处理 |
| L6 模型与协议 | 多 Provider Transport、流式与协议转换 | `butler/transport/` |
| L7 策略与门控 | 权限、审批、人工确认、路径安全 | `butler/permissions/`、`butler/human_gate.py` |
| L8 可靠性与韧性 | 队列、outbox、幂等、重试与降级 | `butler/resilience/` 及 Gateway 可靠性模块 |
| L9 观测与运营 | 诊断、评估、报告、成本与运行指标 | `butler/ops/`、`butler/eval_integration/`、`butler/report/` |
| 横切契约 | Port、Registry、公共协议 | `butler/contracts/` |

### 3.2 Agent Loop 主链路

当前 v4 主循环由模块化包与兼容 shim 共同支撑：

1. **Prepare**：工具结果注入/预算、分级剪枝、遮蔽、内联压缩、模型转换、预防性压缩、消息修复与 API 卫生。
2. **LLM**：多 Provider 调用、流式响应、中断、空内容重试、schema 恢复和 failover。
3. **Tools**：注册表解析、权限/Hook/计划模式门控、并行或顺序调度、read-before-edit、结果 spill、审计与事件发射。
4. **Finalize**：生成 `LoopResult`、诊断、出站回复、完成通知、记忆/经验写入和后处理。

### 3.3 关键子系统

- **Gateway**：iLink 微信入站、会话注册、队列模式、出站重试、durable outbox、typing/progress/completion。
- **Tool Registry**：当前 WIP 正从模块级字典进一步收敛到线程安全 `ToolRegistry` 类，同时保留模块级兼容接口。
- **Memory**：项目 MEMORY、语义索引、ChromaDB、Observation Store、经验挖掘、预取与统一召回。
- **Dev Engine**：PLAN→LOCATE→EDIT→VERIFY→FIX，提供分层验证、回滚、诊断、代码搜索和委派成功门控。
- **Permissions**：项目规则、once/always 审批、Owner 确认、沙箱与外部目录边界。
- **Events**：已提交主线已把工具执行事件接入 ToolCalled/Completed/Failed；当前 WIP 继续扩展审批事件、消息事件、文件持久化、查询、清理、Saga、快照与回放。

## 4. 当前规模

现场统计（排除 `node_modules`）：

| 范围 | 文件数 | 行数 |
|------|--------|------|
| `butler/` Python | 1,490 | 196,873 |
| `tests/` Python | 824 | 127,488 |
| `docs/` Markdown | 252 | 64,313 |
| `butler-v5/` TypeScript | 83 | 5,806 |
| `butler-v5/packages/` | 76 TS 文件 | 5,220 |
| `butler-v5/apps/` | 2 TS 文件 | 58 |
| `butler-v5/tests/` 顶层契约/守卫 | 4 TS 文件 | 480 |

这说明 v4 已是大型单体/模块化混合代码库；v5 目前仍是小型架构原型，不能按文件规模与 v4 等量齐观。

## 5. 最近阶段演进

### 5.1 已提交演进

| 日期 | 主题 | 状态 |
|------|------|------|
| 2026-07-16 | Agent Loop 工具选择、执行缓存/去重、经验注入/写入、语义压缩 | 已提交 |
| 2026-07-23 | 配置默认值收敛、Effects 深化、事件溯源、类型验证、循环依赖修复、依赖审计 | 多批提交完成 |
| 2026-07-27 | 配置继续收敛、Effects/事件驱动架构、死代码接入主路径 | 已提交 |
| 2026-07-27 | 工具执行事件溯源接入、依赖可视化 | 已提交（`5a598165`） |
| 2026-08-04 | Claude Code hooks 配置 schema 修复 | 黑板卡已提交；`.claude/settings.json` 本体仍未提交 |

### 5.2 当前未提交 Python WIP

当前工作区有 25 个已跟踪文件发生修改，已跟踪 diff 约为 **1,651 additions / 515 deletions**；此外还有多组未跟踪模块和测试。

| 方向 | 代表路径 | 接入判断 |
|------|----------|----------|
| Tool Registry 面向对象化与兼容层 | `butler/tools/registry.py` | **主链路 WIP**；改动集中、影响面大 |
| Effects / ADT | `butler/core/effects/*`、`butler/core/adt.py` | Effects 已接公共导出；ADT 目前无主链路引用 |
| 输入与协议验证 | `butler/core/validation.py` | 有完整测试，但目前无主链路引用 |
| API 错误分类 | `butler/core/error_classifier.py`、`error_patterns.py` | 独立实现，有测试；尚未替换现有 Transport 分类器 |
| 事件持久化与治理 | `file_event_store.py`、`hybrid_event_store.py`、`event_query.py`、`event_cleanup.py`、`replay.py`、`saga.py` | 已进入 events 公共导出；除审批事件外，多数仍缺主链路消费 |
| 审批事件 | `approval_event_emitter.py`、`permissions/approvals.py` | **已接审批路径 WIP** |
| 消息事件 | `message_event_emitter.py` | 已导出，尚未发现 Gateway 主链路调用 |
| Skill 渐进披露与学习图 | `progressive_disclosure.py`、`learning_graph.py` | 独立模块与测试，尚未接现有 Skill manager/router |
| 工具预算与新守卫 | `budget_config.py`、`guardrails.py` | 独立模块，尚未接 Tool Registry/Loop 主路径 |
| 单例与内存分析 | `utilities/singleton.py`、`dev_engine/memory_profiler.py` | 支撑性模块；单例有测试，Profiler 已生成报告 |

关键判断：**当前 WIP 不是一个单一功能提交，而是多个架构方向的混合工作区**。在合并前需要按“已接主链路 / 可独立提交 / 仅实验”拆分责任边界。

## 6. `butler-v5/` 的真实状态

### 6.1 设计目标

`butler-v5/` 采用：

- TypeScript + Effect-TS；
- FC/IS（函数式核心 / 命令式外壳）；
- Domain / Ports / Application / Infrastructure / Config / Shared 分包；
- CQRS + Event Sourcing；
- PostgreSQL + Drizzle；
- WeChat Gateway 与 API 两个 app；
- 证据门控、承重代码、Owner 离线、签名、角色分离与自愈等 Guard。

### 6.2 与 v4 的关系

现场检索未发现 `butler-v5` 在 v4 主树中的运行时引用；整个目录也未被 Git 跟踪。因此当前应将其定义为：

> **针对下一代架构的独立可执行原型，而不是 v4 的已接入子模块，也不是已发布主线。**

### 6.3 现场验证

| 检查 | 结果 | 解释 |
|------|------|------|
| `pnpm typecheck` | 通过 | 8 个 workspace 包完成 `tsc --noEmit` |
| `pnpm test` | 显示 338 files / 3,355 tests 全过 | 结果被 workspace 的 `node_modules/@butler/*` 链接重复收集放大 |
| 唯一测试源 | 32 个 `*.test.ts` | 更接近真实测试源规模 |
| `pnpm lint` | **失败** | `@typescript-eslint/consistent-type-exports` 需要 `parserOptions.project`，当前 ESLint 配置未提供 |

v5 的测试配置使用 `packages/**/*.test.ts` / `apps/**/*.test.ts`，而 exclude 写为 `node_modules`，未可靠排除深层链接目录；因此 README/CHANGELOG 中的“3062+ tests”和现场“3355 passed”都不能作为唯一测试用例数。

## 7. 测试与质量状态

### 7.1 Butler v4

现场结果：

| 检查 | 结果 |
|------|------|
| 全量收集 | **12,058 selected / 12,603 collected / 545 deselected**，6.17s，退出码 0 |
| 当前 Python WIP 相关测试 | **703 passed**，5.81s |
| 默认排除 | `live_llm`（由 `pyproject.toml` `addopts` 控制） |
| 收集警告 | 存在兼容 shim 的 DeprecationWarning；发现未注册 `pytest.mark.security` |
| Fast gate | 本次运行超过 20 分钟仍停留在 quick smoke 的 pytest 阶段，随后停止；没有最终 pass/fail 结果 |

Fast gate 的 preflight 已确认 Python、`.env`、MiniMax Key、微信/MCP/Embedding/Vector/Web 依赖、iLink 账户、allowlist、Owner、OCR 与 ffmpeg 等生产依赖可用；唯一 preflight 警告是 `BUTLER_DEFAULT_PROJECT` 未设置，新会话需先 `/切换` 才能使用项目工具。

### 7.2 覆盖率与门禁口径

`pyproject.toml` 当前 coverage `fail_under = 55`。项目发布不以裸跑全量 pytest 为唯一标准，而以分层 gate 为准：

```bash
bash scripts/butler-pytest-fast-gate.sh
bash scripts/project-health-check.sh quick
bash scripts/butler-layer-import-gate.sh
bash scripts/butler-mypy-strict-gate.sh
PYTHONPATH=. pytest tests/contracts/ -q
```

### 7.3 当前不能得出的结论

- 703 个相关测试通过，不能替代完整发布门禁；
- pytest 收集成功，不能证明所有 12,058 个默认选择测试都已执行；
- v5 的 3,355 passed 是重复收集后的数字，不能表述为 3,355 个唯一测试；
- 本次未运行真实 LLM、真实微信端到端、全量 corpus、覆盖率报告或部署回滚演练。

## 8. 安装、运行与常用命令

### 8.1 Butler v4

| 场景 | 命令 |
|------|------|
| 基础安装 | `pip install -e ".[wechat]"` |
| 开发依赖 | `pip install -e ".[dev,wechat]"` |
| 新机上手 | `butler onboard --profile gateway` |
| CLI 对话 | `butler chat` |
| 单条执行 | `butler exec "列出所有项目"` |
| 微信绑定 | `butler wechat-setup` |
| 网关服务安装 | `bash scripts/install-butler-gateway-service.sh` |
| 网关状态 | `bash scripts/butler-gateway-ops.sh status` |
| 默认 pytest | `PYTHONPATH=. pytest -q` |
| 快速门禁 | `bash scripts/butler-pytest-fast-gate.sh` |
| 项目体检 | `bash scripts/project-health-check.sh quick` |

最小配置要求是至少一个 LLM Provider Key。生产微信还应配置微信账户、DM allowlist、Owner ID、工具安全根、runtime/outbox 等；完整变量以 `docs/config/reference.md` 与 `.env.example` 为准。

### 8.2 Butler v5 原型

```bash
pnpm --dir butler-v5 install
pnpm --dir butler-v5 typecheck
pnpm --dir butler-v5 test
pnpm --dir butler-v5 lint
pnpm --dir butler-v5 gate
```

当前 `typecheck` 与测试可执行，`lint` 仍需修复 parser project 配置后才能形成完整绿门禁。

## 9. 黑板、Backlog 与实际状态偏差

黑板是异构 Agent 的交接机制，但当前存在同步偏差：

- `.blackboard/state.md` 的 `_last_synced` 与 `_last_shift` 仍停在 **2026-07-16**；
- 已存在并提交 2026-08-04 shift card，但 `state.md` 未同步；
- `backlog.yaml` 仍保留：
  - `P2-#10 publish-archive / publish-merge`：deferred；
  - `G2-08-defer BUTLER_CODING_STRICT 默认升级`：pending；
- 黑板没有覆盖 7 月底以来的大规模 Effects / Events / v5 原型 WIP。

因此当前项目状态不能只读黑板；必须同时看 Git 历史、工作区和现场测试。

## 10. 文档健康度与陈旧项

### 10.1 90 天检查

按 `git log --follow` 检查 `docs/**/*.md`，截至 2026-08-08 **没有超过 90 天未提交更新的已跟踪 Markdown 文档**。这说明仓库文档更新频繁，但不等于内容没有语义漂移。

### 10.2 已发现的语义漂移

| 文档/位置 | 问题 |
|-----------|------|
| `docs/README.md` | 顶部日期为 2026-07-13，但文件在 2026-07-27 有提交；第 3 行链接闭合符号为中文 `）` |
| `docs/architecture/v4-architecture.md` | 顶部更新说明停在 2026-07-10，但后续正文和提交已包含 7 月中下旬变化 |
| `.blackboard/state.md` | 状态快照停在 7 月 16 日，晚于它的 shift 未汇总 |
| 测试数量 | `docs/README` 的“1200+”、`tests/README` 的“6565 selected”、v4 架构的“6250+”与现场 12,058 selected 不一致 |
| v5 测试数量 | README、DESIGN、CHANGELOG 分别写 3062+/3141+/3062，现场又显示 3355；实际存在重复收集 |
| `docs/analysis/` | 当前整目录 untracked；其中分析文档不应在未决策前被当作正式 SSOT |
| `scripts/docs-lint.sh all` | stale-status、plans 结构、env 同步和 dead-env 通过；broken-links 失败，包含 `docs/README.md` 的中文闭合符号、未跟踪分析文档中的本机 `file://` 引用，以及既有 superpowers 计划链接 |

## 11. 当前主要风险

### P0：仓库与发布边界

1. **大规模混合 WIP 未拆分**：核心注册表、Effects、Events、Skill、预算、测试、运行数据和 v5 原型同时存在于一个工作区。
2. **运行数据进入工作区变化**：`.wfxm_data/chromadb/*` 二进制文件发生修改，容易污染代码提交。
3. **v5 未跟踪**：完整原型、lockfile、文档和本地依赖都在 untracked 目录中，存在误删或误打包风险。
4. **发布门禁尚无最终绿结果**：相关测试通过，但完整 fast gate 本次超过 20 分钟仍未返回，随后被停止。

### P1：架构与集成

1. 多个新 Python 模块只有单测或公共导出，没有主链路调用；需避免“测试通过但功能未生效”。
2. v4 已有 Transport 错误分类器，新 `core/error_classifier.py` 形成潜在双实现。
3. Event Sourcing 当前同时包含已提交的工具事件主链路和未提交的治理/持久化扩展，需要明确持久化 SSOT 与失败语义。
4. v4 深化与 v5 重写之间缺少正式迁移决策、兼容窗口和退出条件。

### P1：工程线束

1. `.claude/settings.json` 的 Hook 命令使用相对路径 `python3 scripts/ai_guard/...`；在 Claude Code 隔离 worktree 中路径从 worktree CWD 解析，而脚本不存在，导致子 Agent 的 Read/Bash 全部被 PreToolUse 阻断。
2. v5 ESLint 缺少 `parserOptions.project`，完整 lint 不可运行。
3. v5 Vitest 对 pnpm workspace 链接目录重复收集，测试数字失真并浪费执行时间。

### P2：协调与文档

1. 黑板状态未跟上 Git 与工作区。
2. 文档对测试规模、日期和 v5 Guard 数量存在不同口径。
3. `docs/analysis/` 同时包含多份 v5 设计稿，但尚未纳入正式文档分层和决策入口。

## 12. 建议的收口顺序

### 第一阶段：保护现状与拆分责任线

1. 为当前 WIP 建立明确分支/提交计划；代码、测试、配置、运行数据和 v5 原型分别处理。
2. 明确 `.wfxm_data/` 哪些是运行态数据、哪些允许版本化，避免把 Chroma/SQLite 二进制随功能提交。
3. 将 Python 新模块分类为：
   - 已接主链路；
   - 可独立交付库；
   - 仅实验、暂不合并。

### 第二阶段：完成 v4 WIP 绿门禁

1. 先固定 Tool Registry 与事件接线的兼容契约；
2. 为“无主链路引用”的新模块增加真实集成测试，或暂时不导出；
3. 跑完整 fast gate、mypy strict、层依赖、契约、coverage 和必要的微信 smoke；
4. 只在所有结果有证据后更新架构 SSOT。

### 第三阶段：对 v5 作正式决策

建议新增 ADR，至少回答：

- v5 是研究原型、长期平行实现，还是正式替代路线？
- 若正式迁移，采用 strangler fig 的切入点是什么？
- v4 的事件、权限、记忆、工作流和数据如何迁移？
- 何时停止向 v4 增加架构级抽象？
- v5 的退出/继续条件和最小生产验收是什么？

ADR 之前，不建议把 `butler-v5/` 描述为当前产品版本。

### 第四阶段：修复线束与状态 SSOT

1. Hook 命令改为基于稳定项目根解析，验证主工作区与 worktree 两种场景；
2. 修复 v5 ESLint typed rules 配置和 Vitest `**/node_modules/**` 排除；
3. 同步 `.blackboard/state.md`、backlog 与最新 shift；
4. 统一测试数量口径为“收集数 / 默认选择数 / 实际执行数 / 唯一测试源数”。

## 13. 建议的项目状态标签

如果需要对外或在 README 中给出一句话状态，建议使用：

> **Butler v4 Beta 主线稳定运行，当前正在深化 Effects、事件溯源和工具注册表；Butler v5 为未合并的 TypeScript/Effect-TS 架构原型，尚未进入产品主线。**

## 14. 事实源索引

| 主题 | 事实源 |
|------|--------|
| 产品定位与快速开始 | `README.md` |
| 当前架构 | `docs/architecture/v4-architecture.md`、`AGENTS.md` |
| 文档分层 | `docs/DOCUMENTATION.md`、`docs/README.md` |
| Python 包与门禁 | `pyproject.toml`、`tests/README.md`、`scripts/butler-pytest-fast-gate.sh` |
| 环境变量 | `.env.example`、`docs/config/reference.md` |
| 协调状态 | `.blackboard/state.md`、`.blackboard/tasks/backlog.yaml`、`.blackboard/shifts/` |
| 近期演进 | `git log`、提交 `224fb8d5`、`edbc26fc`、`5a598165`、`e3047a84` |
| 当前 WIP | `git status`、`git diff --stat`、当前未跟踪模块与测试 |
| v5 原型 | `butler-v5/README.md`、`DESIGN.md`、`package.json`、`vitest.config.ts`、`.eslintrc.json` |

## 15. 本次验证记录

```text
v4 pytest collect:
  12058/12603 tests collected (545 deselected), exit 0

v4 current-WIP related tests:
  703 passed in 5.81s

v5 typecheck:
  8 workspace packages passed

v5 tests:
  338 files / 3355 tests reported passed
  caveat: pnpm linked node_modules caused duplicate collection
  unique source test files observed: 32

v5 lint:
  failed — @typescript-eslint/consistent-type-exports requires parserOptions.project

v4 fast gate:
  preflight passed with one warning (BUTLER_DEFAULT_PROJECT unset)
  quick smoke remained in pytest beyond 20 minutes and was stopped
  no final fast-gate pass/fail result was obtained

documentation hygiene:
  scripts/docs-lint.sh all failed only in broken-links section
  other sections passed: stale-status, flat-plans, bare-plans-links, env sync, dead-env
  the new status document introduced no reported broken relative link
```

<!-- AUTO-GENERATED: END -->
