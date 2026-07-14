# 理论—实现差距登记册（2026-06）

> **状态**：G1–G4 批次已收口（完善 / 决策 / 边界接受）| **2026-07-08** 增 G3-10～12（九层/竖切文档）  
> **理论 SSOT**：[`v4-theoretical-baseline.md`](../../architecture/v4-theoretical-baseline.md) **v3.1.2**  
> **实现 SSOT**：代码 + [`v4-architecture.md`](../../architecture/v4-architecture.md) + [`v4-layer-model.md`](../../architecture/v4-layer-model.md)  
> **层映射**：[`layer-theory-engineering-map.md`](../../architecture/layer-theory-engineering-map.md)  
> **产品边界**：[`roadmap-backlog-and-boundaries-2026-05.md`](roadmap-backlog-and-boundaries-2026-05.md)（与本登记册正交：本文只管「理论声称 vs 代码/运营」）

---

## 0. 用途与分类

当理论文档、路线图与代码不同步时，用本登记册归类差距，**避免误判为「理论错了」或「功能缺失」**。

| 类 | 含义 | 对推导的影响 | 默认动作 |
|----|------|--------------|----------|
| **G1 漏实现** | 理论/前提已通过，工程未补齐 | 不推翻定理；削弱保证或运营闭环 | 记入 Backlog，单独立项 |
| **G2 诚实边界+实现** | 理论承认风险，代码有缓解 | 无逻辑矛盾 | 验证缓解是否有效 |
| **G3 实现更优** | 代码强于旧文档 | 更新文档即可 | 同步理论/架构（不改证明正文） |
| **G4 实现冲突** | 与公理/定理陈述不一致 | 须修代码或收窄定理声称 | 优先修代码或补前提 |

**已收口（2026-06-09）**

| ID | 类 | 项 | 处置 |
|----|-----|-----|------|
| G4-01 | G4 | butler 从 `project.yaml` 继承写工具 | ✅ 代码：`project_tools._butler_allowed_tools` |
| G4-02 | G4 | 公理 A2「无 CLI」与运维 CLI 冲突 | ✅ 文档：v3.1.1 A2 Owner/运维二分 |
| G4-03 | G4 | T8 前提范围 < 定理陈述 | ✅ 文档：P-T8d + 命题 2.14；测试 18/18 |
| G3-批 | G3 | §2.7.1 / §7.4 #10–#11 / 附录 D 滞后 | ✅ 文档：v3.1.1 补丁 |
| G1-03 | G1 | D3-6 无 cron/自动调度 | ✅ `builtin:experience_mining_weekly` + `experience-mining-weekly` job |
| G1-01 | G1 | PIM 加密默认明文 | ✅ 维持 opt-in；运维 checklist 见 `phase4-ops-runbook` §PIM |
| G1-07 | G1 | P-CT4a 变异测试得分未测 | ✅ `gentc_mutation.py` + `test_gentc_mutation_pct4a.py`（7 tests） |
| G1-05 | G1 | B9 未纳入日常运营看板 | ✅ `/诊断` + `butler doctor` + `eval_diagnostics` |
| G1-02 | G1 | 账单 baseline 对照 | ⏸️ **搁置**（2026-06-09 产品决策：顶级个人助手阶段不考虑成本标定；P-COST 结构已验，数值标定待有参考用量后再做） |
| G1-08 | G1 | 灵文新书态一句探针 | ✅ **维护态+B1 handler sim**（2026-06-29）；真开新书时再验 `dual-playbook` |
| G1-06 | G1 | 入站媒体真机 M-img/M-voice | ✅ 2026-06-10 真机复测通过（出站修复后）；pytest 16/16 |
| G2-08 | G2 → G3 | CA4 严格模式默认 advisory | ✅ **已接线 + pilot opt-in**（2026-07-13）：`apply_coding_strict_pilot_gate` 已接入 4-gate 链；Phase A 4 case gate 实证 + 运维 opt-in 工具 + 默认协调已落地（infrastructure verified）；Phase B 端到端 4-gate chain 跑通（2026-07-14，捕获率 100% 2/2，verdict MATCH；见 `docs/plans/pilot-reports/pilot-report-G2-08-2026-07-14.md`） |
| G2-01 | G2 | PII 压缩残留 §7.4 #4 | ✅ 边界已接受：`PII_EXCLUSION_RULE` + `pii_clearable` 已接；残余为诚实边界 |
| G2-02 | G2 | 微信推送中断 §7.4 #7 | ✅ 2026-06-10 outbox+drain 主公确认收到；限流为诚实边界 |
| G2-03 | G2 | P-PIM 路由 ε>0 live 门检 | ✅ 2026-06-09 live：MiniMax 47/50（94%）、DeepSeek 46/50（92%），均 ≥85% |
| G2-04 | G2 | PIM 自由文本仅截断 §7.4 #8 | ✅ 边界已接受：字段 max length；无 `_reject_injection` 为设计取舍 |
| G2-05 | G2 | 单进程无跨记录事务 §1.5 | ✅ 边界已接受：`atomic_write_text` 已接；崩溃窗口为诚实边界 |
| G2-06 | G2 | Hashing Recall 有限 | ✅ 边界已接受：fastembed + `BUTLER_SEMANTIC_MEMORY=1`；Recall 信号正常 |
| G2-07 | G2 | LangFuse opt-in 独立 | ✅ 边界已接受：LangFuse 与硬反馈 env 独立；无 LangFuse 时读本地 audit |
| G2-09 | G2 | MA1/MT1 索引最终一致 | ✅ 边界已接受：写后索引 + `reindex`；Mem 基准 100% |
| G3-08 | G3 | 智能遗忘 `type_adjusted_half_life` | ✅ `v4-memory-theory` v1.2 §4.3 |
| G3-09 | G3 | 编码知识层成熟度收窄 | ✅ `v4-dev-engine-theory` §8.5（`process_task` T2；CD0/6/8 T1） |

| 2026-06-13 | **G1-09** 多项目编码经验作用域（L3/L4）| P0–P5 ✅：`MemoryScope`、委派硬过滤、`backfill-scopes` | 见 [`multi-project-memory-scope-2026-06.md`](multi-project-memory-scope-2026-06.md) |

**开放 G1（2026-06-13）**

| ID | 类 | 项 | 处置 |
|----|-----|-----|------|
| G1-09 | G1 | 编码经验库无 project 硬隔离 | ✅ P0–P5 已落地（L4 scope 写回 + L3 生产失败路径） |

---

## 1. G1 — 漏实现（理论有、验证通过，工程未补齐）

> **不修改**公理/定理证明正文；立项时附验收标准。  
> **真机/生产**：G1-04 OT2 观测窗已结案（2026-07-08）；含生产硬反馈。
> **已搁置**：G1-02、G1-08 — `/诊断` 对应提示可忽略。

| ID | 理论依据 | 现状 | 影响 | 建议 |
|----|----------|------|------|------|
| G1-04 | OT2 有条件目标 | ✅ **管线已验** + 生产硬反馈 68 条（窗 2026-06-09→2026-07-07；OT2 仍为有条件观测目标） | 窗满 + 生产证据 | 2026-07-08 |
| G1-10 | Extension R&D Verify 闭环 | **L0–L3 已落地**（2026-06-22）：manifest ×3、`butler-extension-verify.sh`、token sync、handler sim | 自助装 MCP 无人修 | `butler-extension-verify.sh` · `butler-extension-wechat-sim.sh` |
| G1-11 | 核心微信路径 handler sim 不足 | ✅ **2026-06-22**：`butler-wechat-core-sim.sh`（剧本 1–3+/诊断）+ `butler-ops-followup-check.sh` | 真机前无管家/项目/读文件链验证 | `butler-wechat-core-sim.sh` |
| G1-13 | 全站 secrets↔env 契约分散 | ✅ **2026-06-22**：`.butler/secrets-contract.yaml` + `butler-secrets-contract-check.sh`（合并 extension manifest） | MCP 外 token 断层 | follow-up 硬失败项 |
| G1-12 | 网络检索工具路由无 grounding | ✅ **2026-06-22**：policy golden + **G1-12b handler sim**（`--handler` soft）+ **strict-handler**（发版前硬断言）+ GitHub MCP 路由拦截 | web_search 与 MCP/Firecrawl 抢路 | `butler-web-search-route-sim.sh` |
| G1-14 | 审查知识层未产品化 | ✅ **2026-06-30**：`dev_review` + `review_static` + ADR | Verify≠Review；无结构化 findings | [`dev-review-optimize-adr-2026-07.md`](dev-review-optimize-adr-2026-07.md) |

---

## 2. G2 — 诚实边界（缓解已验 / 边界已接受）

> 理论**不承诺消除**风险；缓解有效或残余风险已产品接受后，日常仅 `/诊断` / `butler-gap-observability.sh` 观测。  
> **日常观测**：`butler/ops/boundary_observability.py` → `/诊断` / `doctor` / `butler-gap-observability.sh`

| ID | 诚实声明 / 边界 | 代码缓解 | 状态 |
|----|-----------------|----------|------|
| G2-01 | §7.4 #4 PII 压缩残留 | `PII_EXCLUSION_RULE`、`pii_clearable`、fact 跳过 PIM | ✅ **边界已接受**（2026-06-09）：规则已注入；残余 PII 为诚实边界；可抽样复核 |
| G2-02 | §7.4 #7 微信中断不可用 | `durable_outbox`、推送退避重试、`PUSH_DRAIN_COOLDOWN` | ✅ **已验**（2026-06-10）：主公确认收到；限流与队列残留为诚实边界 |
| G2-03 | §7.4 #5 路由 ε>0 | D1 消歧 prompt | ✅ **已验**（2026-06-09）：`TestPPIMLiveRouting` MiniMax 94%、DeepSeek 92%；ε 残余为诚实边界 |
| G2-04 | §7.4 #8 PIM 自由文本仅截断 | 字段 max length，无 `_reject_injection` | ✅ **边界已接受**（2026-06-09）：截断已接；误拦合法内容为已知设计取舍（v3.1.1 §7.4 #8） |
| G2-05 | §1.5 单进程无跨记录事务 | `TenantStore` 单文件 `atomic_write_text` | ✅ **边界已接受**（2026-06-09）：原子写已接；崩溃窗口为诚实边界 |
| G2-06 | FINDING-2 Hashing Recall 低 | 默认 fastembed + semantic memory | ✅ **边界已接受**（2026-06-09）：semantic=1 + fastembed；Recall 信号正常（doctor / MB1） |
| G2-07 | LangFuse opt-in | `BUTLER_LANGFUSE_ENABLED` 与 `BUTLER_EVAL_HARD_FEEDBACK` 独立 | ✅ **边界已接受**（2026-06-09）：二者独立配置；无 LangFuse 时硬反馈读本地 audit |
| G2-08 | CA4 严格模式 pilot（§9 CA4） | 默认 `BUTLER_CODING_STRICT=0`；`strict=1` 时生产 pilot 类别定理违例 → `CODING_STRICT_GATE`；软检查仍由 `BUTLER_DEV_AUTO_VERIFY` | ✅ **pilot opt-in + Phase A 4 case + Phase B 端到端 MATCH**（2026-07-14）：运维可通过 `scripts/butler-coding-strict-opt-in.sh` 重复 opt-in；捕获率 100% (2/2) 远超 85% 阈值；pilot report 见 `pilot-report-G2-08-2026-07-14.md` |
| G2-09 | MA1/MT1 索引最终一致 | 写后索引 + `reindex` 兜底 | ✅ **边界已接受**（2026-06-09）：Mem 基准 100%；偶发 miss 为 MB1 诚实边界 |

---

## 3. G3 — 实现更优或超前（文档同步）

> 更新文档**不破坏**推导；G3-01～12 + G3-批均已标 ✅。

| ID | 旧文档表述 | 代码现状 | 文档状态 |
|----|------------|----------|----------|
| G3-01 | per-turn 评分待接 | `eval_turn` + `locked_phases` | ✅ v3.1.1 |
| G3-02 | 硬反馈待接 | `eval_actions` → `agent_loop_phases` | ✅ v3.1.1 |
| G3-03 | 经验挖掘/Synth 未接生产 | `process_task`、`/经验挖掘`、runtime weekly | ✅ v3.1.1 + G1-03 收口 |
| G3-04 | 成本仅结构正确 | D4 `cost_calibration` | ✅ v3.1.1（数值 baseline 搁置，见 G1-02） |
| G3-05 | TenantStore 非原子 | `atomic_write_text` | ✅ v3.1.1 §1.5 脚注 |
| G3-06 | PIM 加密未实现 | `BUTLER_PIM_ENCRYPT` | ✅ v3.1.1 §7.1 |
| G3-07 | `v4-architecture` eval 待接入 | gateway 已接 | ✅ v4-architecture 一行 |
| G3-08 | 智能遗忘未做 | `type_adjusted_half_life` | ✅ `v4-memory-theory` v1.2 §4.3 |
| G3-09 | 子理论 CD0/CD6/CD8 仅测试级 | delegate 生产 `process_task`（CD7 T2）；CD0/CD6/CD8 仍 T1 | ✅ `v4-dev-engine-theory` §8.5 成熟度表 |
| G3-10 | 无九层工程 SSOT | `v4-layer-model.md` L1–L9 + contracts | ✅ 2026-07-07 + map 2026-07-08 |
| G3-11 | P2–P5 竖切未入理论 | `CYCLE_KEEP` 清零；15+ Port；A12–A13 | ✅ v3.1.2 §2.8 + contracts README |
| G3-12 | 记忆/审批竖切未文档化 | `RecallRouter`、`ApprovalStore`、gate pipeline | ✅ map + `formal-theory-2026-07` + `decoupling-assessment-2026-07` |

---

## 4. G4 — 实现冲突（开放项）

| ID | 冲突 | 状态 | 处置 |
|----|------|------|------|
| G4-01 | A3/T8：butler 可继承 project.yaml 写工具 | ✅ 已修 | `project_tools.py` |
| G4-02 | A2：「无 CLI」vs 运维 CLI | ✅ 已修 | v3.1.1 A2 |
| G4-03 | T8 验证范围 < 定理陈述 | ✅ 已修 | P-T8d + T8e 测试 |
| — | *（当前无开放 G4）* | — | 新冲突发现时追加本表 |

---

## 5. 维护规则

1. **新差距**：先归类 G1–G4，再决定立项；勿从 `docs/history/` 或对照报告正文直接立项。  
2. **G4 优先**：有真冲突先修代码或补前提（如 P-T8d），再改成熟度表。  
3. **G3 批量同步**：实现落地后改 `v4-theoretical-baseline` 补丁版本（如 v3.1.2），**不改** T1–T10 证明步骤。  
4. **G1/G2 关闭**：立项完成或验证通过后，将行移至 §6 变更记录，勿删除历史 ID。  
5. **与路线图关系**：`post-consolidation-roadmap` 轨道 A/B/D 运营项若在 G1/G2 出现，两边 ID 可交叉引用，但以本登记册管「理论对齐」。

---

## 6. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-07-08 | **九层理论复验**：v3.1.2（A12–A13）；`layer-theory-engineering-map`；`formal-theory-2026-07`；ENG-15；G3-10～12 ✅ |
| 2026-06-09 | 初版：G1–G4 全表；G4-01/02/03 与 v3.1.1 文档补丁标为已收口 |
| 2026-06-09 | G1-03：`builtin:experience_mining_weekly` + 灵文 `experience-mining-weekly`；G1-01：PIM opt-in checklist |
| 2026-06-09 | G2-02：推送限流暂缓；`BUTLER_RUNTIME_PUSH_DRAIN_COOLDOWN_SECONDS`；pilot-log 记录队列 3 条 |
| 2026-06-09 | G1-07：P-CT4a 等价类审查 + 变异测试得分（`gentc_mutation`） |
| 2026-06-09 | G1-05：`eval_diagnostics` — B9/Dev/Mem 纳入 `/诊断` 与 doctor |
| 2026-06-09 | G1/G2 观测：`boundary_observability` + `butler-gap-observability.sh` |
| 2026-06-09 | **Phase 9 文档同步**：`post-consolidation-roadmap` §9、`DOCUMENTATION`/`README`/`plans/README`/`guides/README`、`external-services` v1.2 |
| 2026-06-09 | **G1 清单启动**：`butler cost` CLI、`butler-g1-checklist.sh`；`pilot-log` §G1；G1-04 观测窗 2026-06-09→06-23 |
| 2026-06-09 | **G1-02 搁置**：无参考用量 + 产品阶段不考虑成本；P-COST 仅观测、无限流 |
| 2026-06-09 | **G1-08 搁置**：灵文新书态属试点业务，非平台通用 G1；维护态 Phase4 已验 |
| 2026-06-10 | **G1-06 收口**：M-img/M-voice 真机复测通过；出站 `mark_final_sent` 顺序修复 + gateway restart |
| 2026-06-10 | **G2-02 部分**：`drain-push` 2 条→成功 1/失败 1，队列剩 1（推送验证）；限流冷却后再 drain |
| 2026-06-10 | **G2-02 收口**：主公确认微信收到推送；outbox+drain 缓解有效 |
| 2026-06-09 | **G2-08 保持现状**：默认 advisory；`BUTLER_CODING_STRICT` env 未接生产阻断；opt-in 硬阻断 + CA4/delegate 关系待开发者详细理论分析后立项 |
| 2026-06-09 | **G2-03 收口**：P-PIM live 门检 MiniMax 94% / DeepSeek 92%（`test_premise_v3_llm_live.py::TestPPIMLiveRouting`） |
| 2026-06-09 | **G3-08/G3-09 收口**：登记册 §3 标 ✅；G3-09 章节引用修正为 `v4-dev-engine-theory` §8.5 |
| 2026-06-09 | **G1–G4 批次收口**：G2-01/04/05/06/07/09 标「边界已接受」；§0 批次摘要；同步 `post-consolidation` **v2.5** §9、`phase4-ops-runbook`、`pilot-log` |
| 2026-06-13 | **G1-04 观测打卡**：窗内 3 条 feedback，剩 10d；**G2-08 pilot**：`CODING_STRICT_GATE` 接生产类别；B9 周循环增 `experience_selection_precision` + affinity backfill |
| 2026-06-14 | **检索纠偏**：`test_driven_add` 需 anchor/inferred task；L3 灵文 edit capture probe；`butler-g1-04-closure-check.sh` |
| 2026-06-14 | **检索纠偏 v2**：`b9_task` 自动 anchor + 通用词过滤；周循环 `forward_selection_precision` |
| 2026-06-19 | **G1-04 观测打卡**：检索链真机 ✅；`butler-g1-04-closure-check.sh` 窗未结束（→06-23 结案）；EXT-1 Track 继续 |
| 2026-06-20 | **G1-04 观测打卡**：窗内 feedback=3、7d=0、剩 3d；`butler-gap-observability.sh` 全绿；EXT-2 Verify ✅ + Track 至 07-04；灵文 EXT-3 检索抽测 5/5（见 `pilot-log` §运营打卡） |
| 2026-06-21 | **EXT-2 Track**：Todoist token 轮换 ✅（微信列项目验证）；分层 gate 152 passed |
| 2026-06-22 | **G1-04 窗延期**：06-23 仅 B9 测评证据 → 窗延至 **07-31**；`closure_ready`→`ot2_closure_ready`（需生产 trigger）；B9-only 可 `--pipeline-only` 诚实结案 |
| 2026-06-25 | **G1-04 周打卡**：`butler-g1-04-weekly-checkin.sh`；窗内 production=48、剩 36d；P1 线 PROD-P1-01/03 done |
| 2026-06-26 | **G1-04 周打卡**：窗内 61 / production 58 / owner_hard 3 / 剩 35d；EXT-5 handler sim 复跑 + scenario `verify_files_exist` |
| 2026-06-21 | **认知层 prod 默认化**：`BUTLER_PLAN_REASON_GRAPH` 默认 `1`；推理 trace 维持默认开 |
| 2026-06-14 | **B9 周循环 v2 验证**：Tier-1 7/7、Tier-2 3/3、SWE 3/3、Promoted 6/6、灵文 3/3；`forward`=1.0（stored 27.5% 为历史误命中）；`prod_delta_clean` 仍 ±0 |
| 2026-06-14 | **第 7 道 prod 晋升**：`B9L_prod_lingwen_constants_docstring`（灵文 constants 样本）；`butler-prod-delta-observe.sh`；L3 capture OK |
| 2026-06-14 | **第 8 道 prod 晋升**：`B9L_prod_lingwen_validate_progress`（灵文 validate_progress 样本）；Promoted oracle **8/8** |
| 2026-06-14 | **周循环韧性**：Promoted 失败不阻断后续阶段；validate_progress playbook + oracle curriculum；LIVE 仍 7/8（模型 patch 未生效） |
| 2026-06-14 | **validate_progress Skill**：`b9-prod-lingwen-validate-progress` + `format_episode_skill_block` 强制注入；ASCII 单行 state；LIVE 仍 0/1（MiniMax 边界） |
| 2026-06-14 | **运营证明路线**：Promoted **core 7 + stretch 1**；`butler-lingwen-live-capture-checklist.sh`；`evaluation-guide` 运营看板 |
| 2026-07-13 | **G2-08 spec + plan + 6 commit**：4 文档同步；`effective_coding_strict_safe` 默认协调；运维 opt-in 脚本 + 4 case smoke；Phase A 4 case smoke；Phase B 灵文1号 pilot runner skeleton |
| 2026-07-14 | **G2-08 pilot 收口（deferred 路径）**：T6 真跑 Phase B 发现 `ch001-reproduce` 不在 `delegate_impl` task registry，sample 未触发 gate 链；commit `505e81b2` 已 revert；改走 caveat 路径 — Phase A 4 case gate 实证 + opt-in 工具 + 默认协调视为 infrastructure verified；Phase B 真 sample 待下次会话重选；详见 `pilot-report-G2-08-2026-07-14-caveat.md` |
| 2026-07-14 | **G2-08 Phase B 端到端跑通（verdict MATCH）**：rewrite pilot runner 改走真实 4-gate chain `apply_delegate_success_gates`（而非单 gate 函数）；dev_engine fixture 来自 `_run_auto_verify` 真实产出（`dev_state.py:159`）；strict=1 下 dev role + deep category + coding_knowledge.violated=[CA4,T8] → 完整 4-gate 链端到端阻断（仅 `apply_coding_strict_pilot_gate` 触发，其他 3 gate 正常 pass/未到）；捕获率 100% (2/2) 远超 85% 阈值；pilot report 见 `pilot-report-G2-08-2026-07-14.md` |

---

## 7. 相关索引

| 文档 | 用途 |
|------|------|
| [`v4-theoretical-baseline.md`](../../architecture/v4-theoretical-baseline.md) | 公理/定理/诚实声明 |
| [`post-consolidation-roadmap-2026-05.md`](../active/post-consolidation-roadmap-2026-05.md) | 运营/实施轨道 |
| [`projects/LingWen1/docs/pilot-log.md`](../../../projects/LingWen1/docs/pilot-log.md) | 真机验收勾选 |
| [`DOCUMENTATION.md`](../../DOCUMENTATION.md) | 文档分层 L0–L5 |
