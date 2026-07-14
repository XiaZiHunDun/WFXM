# Butler v4 实施方案（v3.0 理论推导后）

> **版本**：2.5 | 2026-06-09
> **基于**：`v4-theoretical-baseline.md` v3.1（10 定理 + OT1-OT2 / OA1-OA3）+ `v4-detailed-design.md` v2.0
> **前置**：[`consolidation-2026-05.md`](../archive/consolidation-2026-05.md) P0–P2 已完成
> **基线**：以 [`../../tests/README.md`](../../../tests/README.md) 与 CI 为准（`PYTHONPATH=. pytest -q`）
> **理论-实施映射**：每个实施项标注对应的定理/前提验证依据
> **决策 SSOT**：[`roadmap-backlog-and-boundaries-2026-05.md`](../decisions/roadmap-backlog-and-boundaries-2026-05.md)

---

## 0. 实施方法论

基于理论基线 v3.0 的实施遵循以下原则：

1. **理论驱动**：每个实施项有明确的定理/前提支撑，拒绝无理论依据的特性
2. **验证闭环**：实施 → 测试 → 理论映射表更新
3. **风险优先**：优先处理诚实声明中的已知限制
4. **可观测优先**：先建观测能力，再做优化

---

## 1. 当前站位（v3.1 理论验证后）

| 维度 | 结论 | 理论支撑 |
|------|------|----------|
| 平台 v4 | 微信网关 + 自建 Agent Loop + 项目/Lead/runtime 已落地 | 10 定理全部证明 |
| 观测演化 L7 | LangFuse + eval_bridge/feedback + 硬/软反馈已接 | OA1-OA3 / OT1 通过；OT2 生产证据观测中（G1-04） |
| PIM 三支柱 | 26 工具完整注册 + TenantStore 统一 + 提醒系统重构 | T7 有界性 (28 tests) |
| 安全体系 | 权限隔离 + 注入防护 + 记忆不污染 + 人工门控 | T3/T4/T6/T8 + P-INJ (22 tests) |
| 开发引擎 | DevEngine 4 阶段 + EditHistory + 终止保证 | T9/T10 (91 tests) |
| 成本模型 | 框架建立 + 分类正确 + 仅观测 | P-COST (14 tests) |
| LLM 适配 | MiniMax/DeepSeek 双 provider 验证通过 | P-PIM/P1-LIVE (94%/90%, 100% parse) |
| 事实提取 | 压缩前提取 + 锚点重注入 + PIM 跳过 | P6-LIVE (100%/91.7%) |
| 工程验证 | 全量 pytest **6565 selected**（CI 3.11/3.12 + coverage ≥55%）；含语料、域守门、历史 sprint 回归 | 第六章完整矩阵 |

**已完成的阶段性工作**：

| 阶段 | 状态 |
|------|------|
| 仓库整理 P0–P3 | ✅ |
| CC 线束 P0–P4 | ✅ |
| 四/五报告改进 | ✅ |
| 外部对标 A/B/C | ✅ |
| 理论基线 v1→v2.1→v3.0 | ✅ |
| 前提验证（344 tests，2026-05 基线） | ✅ |
| Sprint 1–6 详设落地 | ✅ |
| 记忆双轨合并 M1–M4 | ✅ |
| `/health` 诊断格式化 | ✅ |
| 微信 `/steer` | ✅ |
| DevEngine 子理论 + 度量/基准（91 tests） | ✅ |
| 记忆子理论 MA1-MA7 / MT1-MT7 + 度量/基准（47 tests） | ✅ |
| 编码能力理论 CA1-CA4 / CT1-CT5 集成 + 99 tests | ✅ |
| 全量回归测试修复（54→0 failures；2026-06 基线 **6565+ selected**） | ✅ |
| TenantStore 测试隔离修复 + 工具注册同步 | ✅ |
| Gateway 重部署（v4.0.0, commit=a8f98c3） | ✅ |
| **闭环优化 Phase 4**（butler-deploy.sh / LangFuse docker / CI eval-push） | ✅ |
| **闭环优化 Phase 1–3**（T02/T07 / 种子经验 / eval_feedback / 经验生命周期） | ✅ |
| **闭环优化 Phase 5**（多项目 LangFuse / per-project key / 指南） | ✅ |
| **理论修订 Phase 0**（L7 观测演化 / 记忆&编码知识矛盾修正 / 架构闭环图） | ✅ |
| **Phase 9 工程/文档收口**（差距登记册、观测脚本、eval 看板、理论补丁） | ✅ |
| **末批真机**（轨道 A/B 微信项 + G2-02 推送送达） | ✅ 2026-06-10（A2/G2-02 等见 `pilot-log`；A5/B1 搁置见 G1-02/08） |

---

## 2. 轨道与优先级

### 轨道 A — 运营巩固（建议先做）

> 理论依据：诚实声明 §7.4 条款 7（WeChat 通道中断不可用）+ 条款 3（HashingEmbedder Recall 有限）

| ID | 项 | 验收 | 理论映射 |
|----|-----|------|----------|
| A1 | 首周观察 `consistency-weekly` 微信摘要 + 推送限流 | `phase4-ops-runbook` 观察表 + 真机 | T2 队列收敛 |
| A2 | 入站媒体真机（M-img / M-voice） | inbound pytest ✅；真机 ✅ 2026-06-10（G1-06） | — |
| A3 | mutating runtime 批准链走一遍 | `test_approve_mutating_one_shot` ✅；真机 `/运行` 拒 mutating | T6 信息流安全 |
| A4 | 发版节奏：`--tier=standard` 日常；`--tier=full` 发版 | `butler-phase4-smoke.sh` + runbook | — |
| A5 | **成本模型实测标定**（v2.0 新增） | `cost-calibration.md` + `/成本` 对照账单 | P-COST |
| A6 | **API Embedder 生产部署** ✅（O3） | Recall@3 > 80% | P3 + FINDING-2 |

### 轨道 B — 灵文单项目样板

> 理论依据：三支柱架构 L5 项目管理层 + T8 管家-委派分离

| ID | 项 | 验收 | 理论映射 |
|----|-----|------|----------|
| B1 | **维护态/新书态** 双剧本 | `dual-playbook.md` ✅；`butler-wechat-dual-playbook-probe.sh` ✅ | T8 角色分离 |
| B2 | 微信「测试」闭环：runtime 只读 job 或委派 dev pytest | runbook 话术 + lead smoke ✅ | T8 |
| B3 | Lead 触发只读 job 场景复验 | `butler-runtime-smoke` factory-status ✅ | T6 |
| B4 | 试点文档收口 ✅ | `projects/LingWen1/docs/README.md` | — |

### 轨道 C — 多项目与接入（中期）

> 理论依据：A5 双域隔离 + L5 ProjectRegistry 设计

| ID | 项 | 验收 | 理论映射 |
|----|-----|------|----------|
| C1 | Git `butler project register` + 外部 repo 试点 ✅ | CLI + 微信 clone + 单测 | A5 双域 |
| C2 | 默认项目策略文档化 ✅ | `/诊断` 默认项目策略块 + 文档 | — |
| C3 | Lead 配置化：多项目 `lead: true` + Skill ✅ | 灵文1号 + 普通试点项目 Lead smoke | T8 |
| C4 | 新建选 `pack` 模板 ✅ | `butler create` / `/项目 新建` 模板 | — |

### 轨道 D — 理论驱动的架构增强（v2.0 新增）

> 理论依据：v3.0 诚实声明中的 9 条已知限制 + 前提验证暴露的优化方向

| ID | 项 | 来源 | 验收 | 理论映射 | 优先级 |
|----|-----|------|------|----------|--------|
| D1 | **PIM 路由消歧增强** ✅ | 诚实声明 §5 + P-PIM 错误分析 | 系统提示消歧规则 + 工具描述消歧提示 (9 tests) | P-PIM | 已完成 |
| D2 | **PII 泄露路径加固** ✅ | 诚实声明 §4 + T4 扩展 | 压缩提示 PII_EXCLUSION_RULE 注入 (4 tests) | T4 + P-INJ | 已完成 |
| D3 | **PIM 自由文本消毒** ✅ | 诚实声明 §8 + P-INJ 取舍 | name/address/note/message 长度截断 (3 tests) | P-INJ | 已完成 |
| D4 | **成本模型数值标定** ✅ | 诚实声明 §6 + P-COST | 事件落盘 + N 日汇总 + 账单基线对照 + `/成本` | P-COST | 已完成 |
| D5 | **Token 估算中文修正** ✅ | 诚实声明 §2 + FINDING-1 | CJK-aware heuristic (4 tests) | P-T1a | 已完成 |
| D6 | **提醒硬上限补全** ✅ | 诚实声明 §9 | MAX_ACTIVE_REMINDERS=100 + 创建检查 (3 tests) | T7 | 已完成 |
| D6b | **成本输出增强** ✅ | P-COST 延伸 | 分桶百分比 + 预估费用 (3 tests) | P-COST | 已完成 |
| D7 | **PIM 存储加密** | 诚实声明 §4 + 批评 4 | Fernet 加密 TenantStore | T7 | 低 · **条件触发**（G1-01 opt-in） |
| D8 | 识图 P3：无 OpenAI 时 MiniMax VLM / 本地 OCR | 媒体入站完善 | — | 低 · **条件触发**（见 deploy-profiles gateway 剖面） |
| D9 | 主机工具远期：`terminal` 白名单 | ADR 修订后实施 | — | 低 · **条件触发**（[`roadmap` §3.12](../decisions/roadmap-backlog-and-boundaries-2026-05.md#312-条件触发工程债-2026-06)） |

### 轨道 D2 — 记忆理论驱动增强（v3.0 新增）

> 理论依据：`v4-memory-theory.md` 公理 MA1-MA7 / 定理 MT1-MT7 / 度量模型 §6

| ID | 项 | 来源 | 验收 | 理论映射 | 优先级 |
|----|-----|------|------|----------|--------|
| D2-1 | **记忆前提验证** ✅ | MT1-MT7 前提 P-MT* | 27 tests 全绿 | MT1-MT7 | 已完成 |
| D2-2 | **记忆效果度量系统** ✅ | 诚实声明 §7.2 + 差距分析 §4.3 | `memory_metrics` 工具可用 + 6 指标采集 (10 tests) | §6 度量模型 | 已完成 |
| D2-3 | **记忆基准测试框架** ✅ | 度量模型 §6.2 MB1-MB7 | 7 项基准任务可运行 + 阈值对比 (10 tests) | MB1-MB7 | 已完成 |
| D2-4 | **写入存活率跟踪** ✅ | `register_write_probe` + recall 匹配 + 持久化 | D-L6-7 | 已完成 |
| D2-5 | **首轮命中率采集** ✅ | `on_prefetch` + `/诊断` S_w/H_1/E_d | D-L6-7 | 已完成 |
| D2-6 | **衰减误杀率监控** ✅ | `rerank` + `on_decay_evaluation` + `/诊断` | D-L6-7 | 已完成 |

### 轨道 D3 — 编码知识层增强（v4.0 新增）

> 理论依据：`v4-dev-engine-theory.md` 第九章 公理 CA1-CA4 / 定理 CT1-CT5 / 前提 H1-H12

| ID | 项 | 来源 | 验收 | 理论映射 | 优先级 |
|----|-----|------|------|----------|--------|
| D3-1 | **编码知识层前提验证** ✅ | CA1-CA4, CT1-CT5, CL1, H6/H8/H11/H13 | 99 tests 全绿（v1.4 扩展） | CA1-CA4 / CT1-CT5 / CL1 | 已完成 |
| D3-2 | **定理库 + 经验库数据模型** ✅ | CD2-CD4 | TheoremLibrary + ExperienceLibrary 可用 | CD2/CD3/CD4 | 已完成 |
| D3-3 | **双重验证门** ✅ | CA4 + CD6 | dual_verify 函数 + 激活函数 | CA4 / CD6 | 已完成 |
| D3-4 | **知识处理管线** ✅ | CD7 | process_task 端到端 | CD7 | 已完成 |
| D3-5 | **定理验证器深化** ✅ | CT1 + H2 | AST 级定理检查器 L1（9 个 checker 升级，regex fallback） | CT1 / H2 | 已完成 |
| D3-6 | **经验挖掘 Agent** ✅ | CA3 + CT3 | 挖掘/feed/changelog → 定理审查 → 待审队列 → 入库 | CA3 / CT3 | 已完成 |
| D3-7 | **知识层嵌入 DevLoop** ✅ | CD7 | DevState 扩展 + process_task 接入 + dual_verify 桥接 + 上下文注入 | CD7 / D-L4-8 | 已完成 |
| D3-8 | **经验库持久化 + 自动提取** ✅ | CA3 + CT3 | JSON 持久化 + 成功任务经验候选提取 | CA3 / CT3 / CD4 | 已完成 |
| D3-9 | **PIM 状态上下文注入** ✅ | PIMState | memory_prefetch 注入 PIM 概览 | 理论 S 中 PIMState | 已完成 |
| D3-10 | **CA4 严格模式 + auto_verify 定理门** ✅ | CA4 | `BUTLER_CODING_STRICT` env + `_run_auto_verify` 定理集成 + 56 tests；2026-07-13 已接 `apply_coding_strict_pilot_gate` 4-gate 链 + pilot opt-in 实证；2026-07-14 灵文1号 ch001 真跑（verdict NO_VIOLATIONS） | CA4 / CT5 | 已完成 |
| D3-11 | **部署依赖补齐** ✅ | 部署 | `pyproject.toml [all]` 含 fastembed/chromadb + 配置文档修正 | — | 已完成 |

### 轨道 O — 观测演化闭环（v3.1 新增，优先于 A）

> 理论依据：父理论 §2.7（OA1-OA3 / OT1-OT2）；闭环优化规划 Phase 1–4

| ID | 项 | 验收 | 理论映射 | 优先级 |
|----|-----|------|----------|--------|
| O0 | **理论修订 Phase 0** ✅ | L7 写入三份理论 + 架构闭环图 | OA1-OT2 | 已完成 |
| O1 | LangFuse 生产启用 + `butler-deploy.sh` 固化 ✅ | provision 脚本 + deploy init/update 集成 | OA1 | 已完成 |
| O2 | L2 度量接线（`on_retrieval` / `on_fact_extraction`）✅ | memory_prefetch + fact_extraction 生产路径 | OA3 | 已完成 |
| O3 | API Embedder 生产部署 ✅ | fastembed 默认 + `embedding_health` Recall@3 检查 | FINDING-2 | 已完成 |
| O4 | per-turn `eval_scoring` 接入 gateway ✅ | `eval_turn` + locked_phases finalize | OA1 | 已完成 |
| O5 | Synth/GenTC 注入 delegate prompt ✅ | `format_coding_guidance_block` → dev_context | §8.5 T1→T2 | 已完成 |
| O6 | eval_feedback → 硬反馈 ✅ | `eval_actions` + `eval_config_overrides` + audit | OT2 | 已完成 |
| O7 | B1–B8 发版回归门 ✅ | `butler-eval-regression.sh` + deploy update 集成 | B8 | 已完成 |
| O8 | 微信语料 → LangFuse Dataset 定期同步 ✅ | `butler-wechat-dataset-sync.sh` + weekly timer | OA1 | 已完成 |
| O9 | LLM 端到端基准（B9）✅ | `llm_delegate_benchmark` + `butler-eval-llm-benchmark.sh` | — | 已完成 |

### 轨道 E — 明确不做

- 外部云记忆（Honcho/Mem0）为默认 — 见 [`memory-roadmap.md`](../../architecture/memory-roadmap.md)
- 全书正文向量索引
- 平台 7×24 无人值守跑完全厂 25 步
- 每项目独立微信 Bot
- 修改 `reference/` 目录策略
- 显式意图分类器（P-PIM 已验证无需引入，见 §6.3.2 结论）
- 多实例消息队列 / 入站 WAL（见 `roadmap-backlog-and-boundaries`）

---

## 3. 推荐实施顺序

```text
Phase 0: O0 ✅（理论修订 — L7 观测演化层）
    ↓
Phase 1: O1–O3 ✅（LangFuse 投产 + L2 接线 + API Embedder）
    ↓
Phase 2: O4–O6 ✅（per-turn 评分 + 编码知识注入 + 硬反馈）
    ↓
Phase 3: O7–O8 ✅（发版回归门 + 语料 Dataset）
    ↓
Phase 4: A + B（自动化守门就绪；真机项延后至全计划完善后）
    ↓
Phase 5: O9 + C ✅（LLM 基准 + 多项目）
    ↓
Phase 6: D2-4–D2-6 ✅（记忆效果度量采集）
    ↓
Phase 7: D4 ✅（成本数值标定：落盘/汇总/账单对照）
    ↓
Phase 8: D3-6 ✅（经验挖掘 Agent + weekly runtime job）
    ↓
Phase 9: ✅ 工程/文档收口（差距登记册、理论补丁、非真机 Backlog — 见 §9）
    ↓
**末批真机** ✅（2026-06-10）：A2/G2-02 等已验；A5/B1 搁置（G1-02/08）。见 `pilot-log.md` §真机验收策略
    ↓
（以下为历史顺序，部分已完成）
Phase 1-legacy: A（运营巩固 + 成本标定 + Embedder 部署）
    ↓
Phase 2: B（灵文样板 + Lead 闭环）
    ↓
Phase 3: D1–D3,D5,D6,D6b ✅（路由消歧 + PII加固 + PIM消毒 + Token修正 + 提醒上限 + 成本增强）
    ↓
Phase 4: C.1（Git 试点）→ C.2–C.4（多项目）
    ↓
Phase 5: D4 ✅（成本模型数值实测标定）
    ↓
Phase 6: D3-5 ✅（AST 级定理检查器 L1 已完成）   ← D3-5/7/8/9 全部完成
    ↓
Phase 7: D7–D9（按需）
    ↓
Phase 7: D2-2,D2-3 ✅（记忆效果度量 + 基准测试，47 tests）
    ↓
Phase 8: D2-4,D2-5（存活率/命中率采集）
    ↓
Phase 9: D2-6（衰减监控，按需）
```

**与详设方案的映射**：

| Phase | 详设层 | 主要定理 |
|-------|--------|----------|
| 1 | L2 (CostTracker) + L6 (SemanticIdx) | P-COST, P3 |
| 2 | L4/L5 (DevEngine, Runtime) | T8, T6 |
| 3 | L2 (IntentRouter) + L6 (InjectionGuard) | P-PIM, T4 |
| 4 | L5 (ProjectRegistry) | A5 |
| 5 | L1 (Pipeline) + L2 (CtxPipeline) + L3 (PIM) | P-INJ, P-COST, T1 |
| 6 | L3 (TenantStore) | T7 |
| 7 | L6 (MemoryMetrics + Benchmark) | MT1-MT7, MB1-MB7 |
| 8 | L6 (度量采集集成) | D-L6-7 |

---

## 4. D1: PIM 路由消歧增强 — 详细实施

### 4.1 问题分析

P-PIM LLM-in-loop 测试暴露的路由错误模式：

| 错误类型 | 示例 | 根因 |
|----------|------|------|
| 省略动作识别不足 | "打卡" → 无工具调用 | 需要系统提示强化 |
| 同模块工具混淆 | `memo_update` → `memo_search` | 缺少上下文导致回退 |
| 语义近似选错 | `habit_stats` → `habit_list` | 工具描述区分度不足 |

### 4.2 实施步骤

| 步骤 | 内容 | 验收 |
|------|------|------|
| D1-S1 | 在 `butler_system.md` 中增加 10+ 同模块消歧示例 | git diff 确认 |
| D1-S2 | 工具 schema description 增加 "用于..." vs "不用于..." 提示 | schema 审查 |
| D1-S3 | 重新运行 P-PIM LLM-in-loop 测试 | 准确率 ≥ 95% |
| D1-S4 | 增加 5 条边界测试用例 | test_premise_v3_llm_live.py 更新 |

### 4.3 不做

- 引入独立分类器（当前准确率已满足阈值）
- 修改 tool_selector 核心逻辑

---

## 5. D2: PII 泄露路径加固 — 详细实施

### 5.1 问题分析

诚实声明 §4：PIM 数据在 LLM 上下文中的隐私风险未完全解决。当前缓解：

```
PIM 查询 → 结果 2 轮 pii_clearable 清空 → fact extraction 跳过 PIM 结果
                                          → 但压缩摘要可能保留 PIM 数据
```

### 5.2 实施步骤

| 步骤 | 内容 | 验收 |
|------|------|------|
| D2-S1 | 在 Compress 阶段的 LLM 指令中增加 "不要在摘要中保留联系人姓名/电话/金额" | prompt 审查 |
| D2-S2 | 增加 post-compact PIM 数据检测 heuristic | ≤ 3 false positive |
| D2-S3 | 增加相关单元测试 | 5+ tests |
| D2-S4 | 更新理论基线 §2.3.6 PIM 隐私泄露路径分析 | 文档同步 |

---

## 6. 文档与工程小债

| 项 | 说明 | 理论映射 |
|----|------|----------|
| pytest 基线 | `PYTHONPATH=. pytest -q` 全仓 **6565 selected**（7110 collected，545 `live_llm` deselected） | 第六章 |
| 发版冒烟 | `bash scripts/butler-pre-release-smoke.sh` | 发版手册 |
| v1 源码 | `git archive archive/butler-v1-20260522 archive/butler-v1` | — |
| 理论-实施同步 | 每完成一个 D 系列项，更新 `v4-theoretical-baseline.md` 对应节 | §6 |
| 详设同步 | 每完成一个 D 系列项，更新 `v4-detailed-design.md` 对应模块 | §9-10 |

---

## 7. 验证门（Gate）

每个 Phase 完成前必须通过的门：

| Phase | Gate | 命令 |
|-------|------|------|
| 1 | 全仓测试绿色 + `/成本` 可用 + Recall@3 > 80% | `PYTHONPATH=. pytest -q` |
| 2 | Lead 不含写工具 + runtime audit 通过 | `test_premise_t8_delegate_separation.py` |
| 3 | P-PIM ≥ 95% + PII 检测可用 | `test_premise_v3_llm_live.py` |
| 4 | 多项目 `/切换` 可用 + 双域不串 | `test_premise_p5_permission_isolation.py` |
| 5 | P-INJ 全绿 + token 估算 < 30% 误差 | `test_premise_v3_new.py` |
| 6 | T7 全绿（含提醒上限） | `test_premise_t7_pim_bounded.py` |
| 7 | MT1-MT7 前提 27 tests 全绿 + 度量工具可用 | `test_premise_memory_theory.py` + `test_memory_metrics_benchmark.py` |

---

## 9. Phase 9 核对表（工程/文档收口）

> **SSOT**：[`theory-implementation-gap-register-2026-06.md`](../decisions/theory-implementation-gap-register-2026-06.md)  
> **观测**：`bash scripts/butler-gap-observability.sh` · **运营**：[`phase4-ops-runbook.md`](../../guides/phase4-ops-runbook.md)

| ID | 项 | 验收 | 状态 |
|----|-----|------|------|
| G4 | 理论—实现冲突（G4-01/02/03） | `project_tools` + v3.1.1 补丁 + T8e 18/18 | ✅ |
| G1-03 | 经验挖掘 weekly runtime | `builtin:experience_mining_weekly` + 灵文 `experience-mining-weekly` | ✅ |
| G1-01 | PIM 加密 | 维持 opt-in；`phase4-ops-runbook` §PIM checklist | ✅ |
| G1-05 | B9 运营看板 | `eval_diagnostics` → `/诊断` + `butler doctor` | ✅ |
| G1-07 | P-CT4a 变异测试 | `gentc_mutation.py` + `test_gentc_mutation_pct4a.py` | ✅ |
| G2-obs | G1/G2 边界观测 | `boundary_observability` + `butler-gap-observability.sh` | ✅ |
| G2-02 | 推送限流缓解 | `PUSH_DRAIN_COOLDOWN` + outbox + drain | ✅ 2026-06-10 主公确认收到 |
| G2-03 | P-PIM live 门检 | `TestPPIMLiveRouting` ≥85% | ✅ 2026-06-09 MiniMax 94% / DeepSeek 92% |
| G2-01/04/05/06/07/09 | 诚实边界缓解 | `boundary_observability` 全 ok | ✅ 边界已接受 |
| G2-08 | CA4 strict 默认 advisory | `BUTLER_CODING_STRICT=0`；已接 4-gate 链；pilot opt-in 实证 + 2026-07-14 真跑 verdict NO_VIOLATIONS | ✅ **pilot opt-in + 真跑**（2026-07-13/14） |
| G3 | 文档同步 G3-01～09 | v3.1.1 + 子理论 §8.5 / memory v1.2 | ✅ |
| G1-02 | 成本 baseline | — | ⏸️ **搁置** |
| G1-08 | 灵文新书态 | 维护态已验 | ⏸️ **搁置**（试点业务） |
| G1-04 | OT2 硬反馈生产证据 | `eval_feedback.jsonl` | ⏳ 观测中 窗 **06-09→07-31**（剩 ~35d）；窗内 **61**、生产 **58**、`owner_hard_feedback` **3**；`ot2_closure_ready=false` |
| G1-06 | 入站媒体真机 | inbound pytest ✅ + 真机 M-img/M-voice | ✅ 2026-06-10 |
| doc-sync | 文档索引与降级说明 | 本文 §9 + `DOCUMENTATION` / `README` / `external-services` | ✅ |

**末批真机不在 Phase 9 范围内**；勾选表见 [`projects/LingWen1/docs/pilot-log.md`](../../../projects/LingWen1/docs/pilot-log.md)。

---

## 10. 相关文档

- [`theory-implementation-gap-register-2026-06.md`](../decisions/theory-implementation-gap-register-2026-06.md) — 理论—实现差距登记册（G1–G4）
- [`v4-theoretical-baseline.md`](../../architecture/v4-theoretical-baseline.md) — 理论基线 v3.1.1（10 定理 + OT1-OT2 / L7 观测演化）
- [`v4-detailed-design.md`](../../architecture/v4-detailed-design.md) — 详细设计方案 v2.0
- [`v4-dev-engine-theory.md`](../../architecture/v4-dev-engine-theory.md) — L4 子理论
- [`v4-memory-theory.md`](../../architecture/v4-memory-theory.md) — L6 记忆子理论（MA1-MA7 / MT1-MT7 / MB1-MB7）
- [`v4-architecture.md`](../../architecture/v4-architecture.md) — 实现记录
- [`cc-butler-gap-analysis-2026-05.md`](../active/cc-butler-gap-analysis-2026-05.md) — CC 线束（已全部落地）
- [`roadmap-backlog-and-boundaries-2026-05.md`](../decisions/roadmap-backlog-and-boundaries-2026-05.md) — 决策 SSOT
- [`reviews/project-deep-audit-2026-06.md`](../../reviews/project-deep-audit-2026-06.md) — 深度审计
- [`guides/project-onboarding.md`](../../guides/project-onboarding.md) — 项目引导
- [`architecture/project-lead-decision.md`](../../architecture/project-lead-decision.md) — Lead 决策

---

## 11. 版本记录

| 版本 | 日期 | 说明 |
|------|------|------|
| 2.6 | 2026-07-10 | Lead role + 仓库盘点 banner + tools/skills role-gate + 6× `_ops` 内联（P1-C）+ 3× pytest 收集错误修复 + 演示对话 sim + interview backlog（13 commit + 1 chore） |
| 2.5 | 2026-06-09 | G1–G4 登记册批次收口：§9 补 G2/G3 项；末批真机 ✅；G2 边界已接受；开放仅 G1-04 |
| 2.4 | 2026-06-09 | Phase 9 工程/文档收口；差距登记册与 `butler-gap-observability.sh` |
