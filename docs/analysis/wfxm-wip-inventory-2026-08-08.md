# WFXM 当前 WIP 分类（2026-08-08 冻结）

> 基线：`main` 工作区；依据本次实际 `git status --short`、`git diff --stat`、`git ls-files` 与文件内容核验。处理列表示 **R0 之后** 的边界决定，不代表现在可提交。
>
> 分类口径：**保留**＝v4 仅为 P0 生产/安全修复或迁移证据继续保留；**推 v4 main**＝已成熟且应独立过门禁后合并；**转 v5**＝只迁移契约、行为与测试意图，不直接混入 v5 提交；**删除/暂缓**＝运行产物、未接线实验或与终局不一致的实现。

## 冻结基线摘要

- 已跟踪变化：25 个 `M`、1 个 `D`；`git diff --stat` 为 26 files changed、1,656 insertions、515 deletions。
- `.wfxm_data` 有 7 个已跟踪文件，其中本次 3 个 `M`、1 个 `D`；它们是运行/派生数据，不是迁移输入提交。
- `git ls-files butler-v5` 无输出：`butler-v5/` 没有任何已跟踪文件。
- 短状态将 `butler-v5/` 与 `docs/analysis/` 折叠为目录；下文以该真实短状态条目分类，并列出目录内现场文件范围。

## 已跟踪并修改（M/D）

| 主题 | 文件 | 接入层级 | R0 后处理 | 依据/边界 |
|---|---|---|---|---|
| 协调 | `.blackboard/log.md` | repository/coordination | 推 v4 main | 只与对应 shift 卡、盘点文档组成独立文档提交，不夹带代码 |
| 工程线束 | `.claude/settings.json` | repository/tooling | 保留 | Hook schema 修复已存在；worktree 根路径问题仍须按 R0 P0 单独修复和验证 |
| 运行数据 | `.wfxm_data/chromadb/6c30fa72-245c-4733-bbac-afb59e6fa36f/data_level0.bin` | runtime data | 删除/暂缓 | Chroma 派生二进制，禁止进入功能提交 |
| 运行数据 | `.wfxm_data/chromadb/6c30fa72-245c-4733-bbac-afb59e6fa36f/index_metadata.pickle` | runtime data | 删除/暂缓 | Chroma 派生索引，v5 按记录重建 |
| 运行数据 | `.wfxm_data/chromadb/chroma.sqlite3` | runtime data | 删除/暂缓 | 运行 SQLite；不是 v5 迁移事实源 |
| 运行数据 | `.wfxm_data/experience_tree.db-shm` (`D`) | runtime data | 删除/暂缓 | SQLite 临时共享内存文件，不提交删除 |
| core | `butler/core/__init__.py` | core | 转 v5 | 懒导入及 ADT/validation 公共导出属于架构抽象；只迁移边界意图 |
| core | `butler/core/context_pipeline.py` | core | 删除/暂缓 | 仅新增宽泛 `__all__`，未形成 v5 迁移资产或 v4 P0 修复 |
| effects | `butler/core/effects/__init__.py` | core/effects | 转 v5 | Effects 懒加载与高级组合子公共面；v5 以 TS Domain/Effect 契约重建 |
| effects | `butler/core/effects/maybe_monad.py` | core/effects | 转 v5 | `fold`/`match` 行为可进入 v5 ADT 契约测试 |
| effects | `butler/core/effects/result.py` | core/effects | 转 v5 | 高级组合子导出面适合 v5 ADT/Effect 设计 |
| effects | `butler/core/effects/result_monad.py` | core/effects | 转 v5 | `fold`/`match`/值提取语义可迁移，Python 实现不直搬 |
| events | `butler/core/events/__init__.py` | core/events | 转 v5 | 文件/混合存储、查询、清理、审批、消息、Saga、Replay 被公开导出；v5 需重新定义 Event Store/Projection 边界 |
| events | `butler/core/events/event_store.py` | core/events | 转 v5 | Saga/Replay 兼容导出面；迁移行为而非 shim |
| events | `butler/core/events/session_events.py` | core/events | 转 v5 | `project_path` 投影语义应进入 v5 Conversation/Project 迁移契约 |
| permissions | `butler/core/two_phase_confirm.py` | core/permissions | 推 v4 main | 仅把函数内 import 上移；须独立验证循环依赖与启动成本后才可合并 |
| gateway | `butler/gateway/task_milestone.py` | gateway | 推 v4 main | 仅配置 import 上移；作为 v4 维护改动独立验证，不进入 v5 提交 |
| permissions | `butler/permissions/approvals.py` | permissions | 转 v5 | 审批路径已接事件发射，但广泛 optional import/吞异常；迁移审批事件语义，不直合并 |
| runtime | `butler/runtime/delegate_progress.py` | runtime | 推 v4 main | 仅配置 import 上移；作为迁移期 v4 维护改动独立验证 |
| registry | `butler/tools/registry.py` | tools/registry | 转 v5 | 线程安全对象化 Registry 与兼容层是主链路大 WIP；提取 Tool Port/Registry 契约和测试 |
| transport | `butler/transport/base.py` | transport | 删除/暂缓 | 仅新增宽泛 `__all__`，不是 P0 修复；v5 Port 另行定义 |
| transport | `butler/transport/llm_client.py` | transport | 删除/暂缓 | 仅新增 `__all__`；v5 LLM Port/Adapter 不复用该表面 |
| transport | `butler/transport/stream_probe.py` | transport | 保留 | 延迟指标改为可选导入降级；需按 v4 生产探针兼容性单独验证 |
| utilities | `butler/utilities/__init__.py` | utilities | 删除/暂缓 | 只接入未跟踪 singleton 公共导出；在其去留决定前不合并 |
| 测试 | `tests/blackboard/test_session_end.py` | tests/coordination | 推 v4 main | 将固定日期改为当天；与黑板线束修复独立提交并验证 |
| 测试 | `tests/test_tool_guardrails.py` | tests/tools/registry | 转 v5 | 大规模 Registry/Guardrail 行为测试；保留契约意图，随对应实现拆分 |

## 未跟踪（??）

| 分类 | 条目（按短状态） | R0 后处理 | 依据/边界 |
|---|---|---|---|
| 分析 | `.blackboard/shifts/2026-08-08-claude-code-001.md` | 推 v4 main | 既有只读盘点卡；仅获授权后与本清单组成手动新文件提交 |
| v5 原型 | `butler-v5/` | 转 v5 | **整目录未跟踪**；约含 apps、domain/application/infrastructure/ports/config/shared、测试、CI、pnpm lock、Compose 与文档。R0 前不得与 v4 WIP 合并；后续在 v5 边界独立纳管 |
| core | `butler/core/adt.py` | 转 v5 | ADT 原型及 `tests/test_adt.py` 的行为意图转入 v5 Domain |
| effects | `butler/core/effects/advanced.py` | 转 v5 | 高级 Effects 组合子原型，配合已修改 effects 导出面评估 |
| core | `butler/core/error_classifier.py`, `butler/core/error_patterns.py` | 转 v5 | 与现有 Transport 分类器并行；只迁移统一错误 ADT/分类契约 |
| events | `butler/core/events/approval_event_emitter.py` | 转 v5 | 已由 approvals WIP 调用；提取 Approval/Audit event 契约 |
| events | `butler/core/events/event_cleanup.py`, `event_query.py`, `file_event_store.py`, `hybrid_event_store.py`, `replay.py`, `saga.py` | 转 v5 | 已进入 events 公共导出但多为非主链路治理/持久化；按 PostgreSQL Event Store/Projection 重新实现 |
| events | `butler/core/events/message_event_emitter.py` | 删除/暂缓 | 只有公共导出，未见 Gateway 主链路调用；待 v5 Channel/Event 用例定义 |
| core | `butler/core/validation.py` | 转 v5 | 有独立测试但未接主链路；迁移 schema decode/validation 契约 |
| 分析 | `butler/dev_engine/memory_profiler.py` | 删除/暂缓 | 支撑性 profiler；生成报告是运行产物，不是产品迁移资产 |
| skills | `butler/skills/learning_graph.py`, `butler/skills/progressive_disclosure.py` | 删除/暂缓 | 未接现有 Skill manager/router，且不在 v5 首个生产切片目标内 |
| tools | `butler/tools/budget_config.py`, `butler/tools/guardrails.py` | 转 v5 | 未接 Registry/Loop；迁移预算与 Policy/Guard 契约，不直搬模块 |
| utilities | `butler/utilities/singleton.py` | 删除/暂缓 | v5 FC/IS 与 Effect Layer 不应迁移 Python 单例实现 |
| 分析 | `docs/analysis/` | 暂缓（逐份审阅；不可自动删除） | 现场含 10 份既有状态/设计/迁移分析稿；目录本身不是 SSOT。本清单是其中唯一由本任务新增文件 |
| 分析 | `docs/superpowers/plans/2026-08-08-wfxm-v5-replacement-implementation-plan.md` | 转 v5 | 已批准规格的执行计划，后续随 v5 决策文档边界纳管 |
| 分析 | `docs/superpowers/specs/2026-08-08-wfxm-rearchitecture-design.md` | 转 v5 | 已批准目标规格；与原型/代码分开提交 |
| 运行数据 | `memory_profile_report.json` | 删除/暂缓 | profiler 运行输出，不提交 |
| 测试 | `tests/test_adt.py` | 转 v5 | 对应 ADT 行为契约 |
| 测试 | `tests/test_budget_config.py` | 转 v5 | 对应 Tool Budget 契约 |
| 测试 | `tests/test_domain_event_integration.py` | 转 v5 | 对应 Domain Event 集成契约 |
| 测试 | `tests/test_error_classifier.py` | 转 v5 | 对应统一错误分类契约 |
| 测试 | `tests/test_event_cleanup_and_query.py`, `tests/test_event_store_persistence.py` | 转 v5 | 对应事件治理/持久化契约，目标存储改为 PostgreSQL |
| 测试 | `tests/test_progressive_disclosure.py` | 删除/暂缓 | 对应首切片非目标且未接主链路的 Skill 实验 |
| 测试 | `tests/test_singleton.py` | 删除/暂缓 | 对应不迁移的 Python singleton 实现 |
| 测试 | `tests/test_validation.py` | 转 v5 | 对应 schema decode/validation 契约 |

### `docs/analysis/` 现场文件范围

除本任务新文件外，短状态折叠目录内已有：`butler-v5-complete-design-2026-07-30.md`、`butler-v5-final-design-2026-07-30.md`、`butler-v5-final-review-and-plan-2026-07-30.md`、`butler-v5-functional-architecture-2026-07-30.md`、`butler-v5-optimization-from-projects-2026-07-30.md`、`current-project-analysis-2026-07-28.md`、`functional-architecture-migration-plan-2026-07-30.md`、`functional-migration-supplement-2026-07-30.md`、`project-status-2026-08-08.md`、`strangler-fig-migration-guide-2026-07-30.md`。这些文档须逐份审阅后才能决定是否作为历史分析纳管，不自动视为 v5 SSOT。

## 拒绝写入的提交

R0 结束前，任何提交都不得混合以下边界：

1. `.wfxm_data/` 的 ChromaDB、SQLite、pickle、SHM 等运行/派生数据；
2. 整个未跟踪 `butler-v5/` 原型；
3. 上述 v4 Python WIP、对应测试、实验分析与运行报告；
4. v5 规格/计划、R0 文档与产品代码。

本任务不执行 `git add`、不自动 stage、不 commit。只有用户明确授权后，才可手动只加入本清单与既有 `.blackboard/shifts/2026-08-08-claude-code-001.md`；预先存在的任何 v4 `M`/`D`/`??` 均不得加入。
