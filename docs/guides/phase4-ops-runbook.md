# Phase 4 运营巩固 + 灵文样板（A + B）

> 路线图：[`post-consolidation-roadmap-2026-05.md`](../plans/active/post-consolidation-roadmap-2026-05.md) §轨道 A/B  
> **前置**：观测演化 Phase 0–3 已完成（LangFuse、回归门、语料同步）。

**真机策略（2026-06-09）**：下文 A2/A3/A5/B1–B3、推送 drain、首周观察等**需微信或主公操作的项，统一放在规划末批真机验收**；开发阶段只跑本文「一键自动化守门」与 CLI 预演。勾选表见 [`pilot-log.md`](../../projects/LingWen1/docs/pilot-log.md) §真机验收策略。

---

## 一键自动化守门

```bash
cd ~/projects/WFXM

# 日常（约 3–8 分钟，不含 consistency-weekly）
bash scripts/butler-phase4-smoke.sh

# 发版
bash scripts/butler-phase4-smoke.sh --tier=full

# 含 A1 慢任务（consistency-weekly，可能数分钟）
bash scripts/butler-phase4-smoke.sh --with-consistency
```

### Gateway 生产依赖清单（`[gateway]` extra）

微信 Gateway 机推荐 **`pip install -e ".[gateway]"`**（`butler-gateway-ops.sh upgrade` 已对齐）。声明式 SSOT：[`projects/LingWen1/stack.yaml`](../../projects/LingWen1/stack.yaml)。

| 组件 | 安装/配置 | 验收 |
|------|-----------|------|
| Python `[gateway]` | wechat + mcp + embeddings + vectors + web | `bash scripts/butler-gateway-ops.sh preflight` |
| Node 18+ / npx | 系统包 | preflight `npx present`（`BUTLER_MCP_ENABLED=1` 时） |
| Firecrawl MCP | `~/.butler/mcp.yaml` + `FIRECRAWL_API_KEY` | `butler mcp status` / EXT-1 已验 |
| HTTP 代理 | 如 `127.0.0.1:7890` | `web_search` 省钱轨；**Firecrawl = 检索 SLA** |
| 语义记忆 | `BUTLER_SEMANTIC_MEMORY=1` + fastembed | `butler doctor` Recall@3 |
| 可选技能 | `bash scripts/butler-lingwen-skills-install.sh` | `butler skills list` 含 webnovel-*（**GitHub 远程**，非 `~/.claude/plugins`） |

**不装**在 Gateway：`dev`、`cli`、`documents`（EXT-3 ingest 走开发机或 sidecar）。

**部署剖面**：`BUTLER_DEPLOY_PROFILE=gateway|dev|all`（默认：Gateway 在跑 → `gateway`）。`butler-deploy.sh update` 与 [`dependency-terminology-2026-06.md`](dependency-terminology-2026-06.md) §4。

覆盖项：

| 路线图 ID | 自动化覆盖 |
|-----------|------------|
| A3 | `butler-runtime-smoke.sh` → `test_approve_mutating_one_shot` |
| A4 | `--tier=standard` / `--tier=full` |
| A6 | `butler doctor` Recall@3（O3 已完成） |
| B1–B3 | `butler-lingwen-lead-smoke.sh` + runtime 只读 job |
| A2 | `butler-inbound-media-smoke.sh`（代码路径；真机另做） |

---

## 轨道 A — 运营巩固

### A1 · consistency-weekly 首周观察

**目标**：周一 09:00 UTC 定时摘要进微信；观察推送限流与队列 drain。

```bash
# CLI 预演（默认不推微信）
butler runtime run consistency-weekly --project 灵文1号 --no-notify

# 真机推送验证
bash scripts/butler-wechat-push-verify.sh 灵文1号
```

**微信观察表**（首周填一次）：

| 检查项 | 通过 | 备注 |
|--------|------|------|
| 周一收到 consistency 摘要或 audit 路径 | ☐ | |
| 推送间隔 ≥ `BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS` | ☐ | 默认 25s |
| 限流时 `/诊断` 推送队列减少（drain timer） | ☐ | `butler-push-drain.timer`；限流后 **勿连点** `drain-push`（默认 300s 冷却） |

### A2 · 入站媒体真机

代码守门：`bash scripts/butler-inbound-media-smoke.sh`

| 步骤 | 微信操作 | 预期 |
|------|----------|------|
| M-img | 发项目相关截图 | 描述图中要点（VLM） |
| M-voice | 发 <30s 短语音 | 转写并回复要点 |

见 [`wechat-daily-smoke-checklist.md`](./wechat-daily-smoke-checklist.md) §入站媒体。

### A3 · mutating runtime 批准链

**自动化**：`pytest tests/test_runtime.py::test_approve_mutating_one_shot`

**真机**（`publish-archive` 默认 `enabled: false`，安全）：

1. `/定时` — 确认 mutating job 显示「需批准」
2. `/运行 publish-archive` — **应拒绝**
3. （可选）临时 `enabled: true` + `/批准运行 publish-archive` — 消耗批准、写 audit

审计：`~/.butler/runtime/runs/灵文1号/<job_id>/*.json`

### A4 · 发版节奏

| 场景 | 命令 |
|------|------|
| 日常合并 | `bash scripts/butler-smoke.sh --tier=standard` |
| 发版 / 大改 gateway | `bash scripts/butler-pre-release-smoke.sh` 或 `--tier=full` |
| 微信/工具子集（非全量 pytest） | `pytest tests/gateway/test_gateway_handler.py tests/test_tools_registry.py tests/test_intent_keywords.py tests/test_network_search_policy.py tests/test_tool_pair_repair.py -q` |
| 部署 | `bash scripts/butler-deploy.sh update`（含回归门） |

> **pytest 全量**：`pytest tests/` 仍有跨测状态泄漏（~100 fail，主集中 `test_tools_registry`）；**不以全绿为发版硬 gate**，见 `pilot-log` §分层 gate（2026-06-21）。发版以 `butler-pre-release-smoke.sh` + corpus 分层为准。

### A5 · 成本模型实测标定

见专文 [`cost-calibration.md`](./cost-calibration.md)。

微信：`/成本` → 对照 MiniMax/DeepSeek 账单，记录偏差。

### PIM 加密（opt-in，不默认强制）

理论 D7 支持 at-rest 加密；**默认仍为明文 JSON**（`BUTLER_PIM_ENCRYPT=0`），与登记册 G1-01 决策一致。

| 步骤 | 操作 |
|------|------|
| 1. 评估 | 多租户/共享主机/合规要求时再启用；单机自用可维持明文 |
| 2. 依赖 | `pip install cryptography`（或 `butler-system` 已含） |
| 3. 生成密钥 | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| 4. 配置 | `.env` 设 `BUTLER_PIM_ENCRYPT=1` + `BUTLER_PIM_ENCRYPT_KEY=<上一步输出>` |
| 5. 验证 | 新建一条 memo/联系人后检查 `~/.butler/tenants/<id>/` 对应 JSON 以 `FERNET:` 开头 |
| 6. 轮换 | 新 key 无法解密旧 `FERNET:` 记录；须先导出/迁移或接受旧记录只读残留 |
| 7. 回滚 | 设 `BUTLER_PIM_ENCRYPT=0` 后**新写入**恢复明文；已加密文件需手动解密或保留 |

**注意**：`BUTLER_PIM_ENCRYPT=1` 但 key 为空时，代码会打 warning 并**退化为明文**（见 `tenant_store._get_fernet`）。

### 诚实边界观测（G1/G2）

微信 `/诊断` 与 `butler doctor` 展示登记册 **G1/G2** 可读信号（非真机验收）。

```bash
bash scripts/butler-g1-checklist.sh        # G1 开放项：成本/inbound/真机话术提示
bash scripts/butler-g1-04-weekly-checkin.sh   # 窗内周打卡（--log）
bash scripts/butler-g1-04-closure-check.sh # G1-04：窗 06-09→07-31；exit 0=生产证据可结案
bash scripts/butler-ops-followup-check.sh  # 日常：G1-04 窗 + boundary + 推理/DoT smoke + secrets 契约 + EXT verify/sim
bash scripts/butler-secrets-contract-check.sh   # G1-13：extension + 平台 env 契约
bash scripts/butler-wechat-owner-sim.sh --quick # Owner manifest 模拟（core/slash/memory/search）
bash scripts/butler-wechat-owner-sim.sh --track ext,delegate  # MCP + 委派（写 owner-sim-smoke.md）
bash scripts/butler-wechat-core-sim.sh          # G1-11：核心微信剧本 handler 模拟（~60s，需 LLM）
bash scripts/butler-web-search-route-sim.sh     # G1-12 policy；--handler soft；--handler --strict-handler 发版前
bash scripts/butler-extension-wechat-sim.sh   # 单独：扩展验收话术（不经 iLink，~40s，需 MCP+LLM）
bash scripts/butler-reasoning-trace-smoke.sh # 推理 transcript 烟测（无 LLM）
bash scripts/butler-dot-lite-smoke.sh      # DoT-lite plan 图烟测（默认开；=0 时 skip 图断言）
bash scripts/butler-pytest-bisect.sh       # 分层 pytest gate（全量见 RUN_FULL=1）
bash scripts/butler-lingwen1-edit-capture.sh # 灵文改码失败 → L3 捕获演练
bash scripts/butler-lingwen-live-capture-checklist.sh # 灵文 live 捕获运营检查清单
bash scripts/butler-prod-delta-observe.sh    # 周中 prod_delta 快照（非周日也可跑）
bash scripts/butler-gap-observability.sh   # 全量 verbose；warn>0 时 exit 1
bash scripts/butler-ops-cadence.sh --weekly     # G1-04 + agent eval 周报
bash scripts/butler-ops-cadence.sh --quarterly  # 每季：周报 + capability baseline
bash scripts/install-butler-ops-cadence-timer.sh  # user systemd 周日/季初自动跑
bash scripts/butler-tcr-strict-readiness.sh     # TCR strict 升级前检查（~2min）
```

| ID | 自动化信号 | 仍须人工 |
|----|------------|----------|
| G1-02 | 成本基线是否已设 | ⏸️ **搁置**（现阶段不做账单对照；`/诊断` 提示可忽略） |
| G1-04 | `eval_feedback.jsonl` 窗内 + trigger 分类 | `butler-gap-observability.sh` / `butler doctor` 看 `g1_04_window`（窗 **06-09→07-31**） |

**G1-04 结案（窗满后）**

| 条件 | 命令 | 登记册表述 |
|------|------|------------|
| 窗满 + ≥1 **生产**来源硬反馈（`trigger` 非 B9） | `butler-g1-04-closure-apply.sh` | 管线已验 + 生产硬反馈 |
| 窗满但**仅 B9 测评** | `butler-g1-04-closure-apply.sh --pipeline-only` | 管线已验；**OT2 未证** |
| 窗未结束 | check exit **2** | 不结案（开发期预期） |

`butler-g1-04-closure-run-if-ready.sh` **不会**自动 `--pipeline-only`。

```bash
bash scripts/butler-g1-04-closure-check.sh   # exit 0/1/2/3 见脚本头注释
```

**认知层（2026-06-21 试点 → prod 默认开）**

| 变量 | 默认 | 说明 |
|------|------|------|
| `BUTLER_REASONING_TRACE` | `1` | LLM 推理摘要 + verify/stuck 反思 → transcript；`/诊断` 可见 |
| `BUTLER_PLAN_REASON_GRAPH` | `1` | 规划 `write_file` → DoT-lite 至 `~/.butler/sessions/<key>/reason_graph.json`；自动连边 fact→hypothesis→step→risk；`=0` 关闭 |
| `BUTLER_TURN_SUMMARY_LINE` | `1` | 长回复前附 `📎` 工具摘要；`=0` 关闭 |

```bash
# 烟测 + 日常 follow-up（G1-04 窗内 exit 2 为预期）
bash scripts/butler-ops-followup-check.sh
```

| G1-06 | M-img / M-voice 真机 | ✅ 2026-06-10 `pilot-log` |
| G1-08 | — | ⏸️ **搁置**（灵文试点；非平台 G1） |
| G2-01 | PII 压缩规则 | ✅ 边界已接受；`/诊断` 观测 |
| G2-02 | 推送队列 / outbox | ✅ 已验 2026-06-10；队列残留由 drain/timer 清 |
| G2-03 | P-PIM live | ✅ 94%/92%（2026-06-09）；发版前可复跑 live |
| G2-04~07/09 | 截断/atomic/Recall/LangFuse/索引 | ✅ 边界已接受；`butler-gap-observability.sh` |
| G2-08 | CA4 strict | ⏸️ **保持现状**（advisory；strict 未接线） |

### 开发质量看板（O7/O9）

微信 `/诊断` 与 `butler doctor` 展示 **Dev B1–B8 / Mem MB1–MB7 / B9 delegate** 最近一次审计（`~/.butler/audit/`）。

```bash
# 刷新 Dev+Mem+B9(oracle) 并写入 audit
bash scripts/butler-eval-regression.sh --no-langfuse

# 仅 B9（oracle 或 BUTLER_EVAL_LLM_BENCHMARK=1 live）
bash scripts/butler-eval-llm-benchmark.sh
```

### D3-6 · 经验挖掘周报（runtime）

灵文样板 job：`experience-mining-weekly`（周日 04:00 UTC，`enabled: true`）。

```bash
# CLI 预演（默认不推微信）
butler runtime run experience-mining-weekly --project 灵文1号 --no-notify
```

| 变量 | 默认 | 说明 |
|------|------|------|
| `BUTLER_EXPERIENCE_MINING` | `1` | `0` = handler 跳过 |
| `BUTLER_EXPERIENCE_MINING_AUTO_INGEST` | `0` | cron **强制** `auto_ingest=False`；高置信自动入库仅 CLI/微信显式开启时 |
| `BUTLER_EXPERIENCE_MINING_DAYS` | `7` | 扫描窗口 |

待审队列：`~/.butler/experience_mining/pending.json`；Owner 微信 `/经验挖掘` 或 `experience_mining_cli approve`。

---

## 轨道 B — 灵文单项目样板

### B1 · 维护态 / 新书态双剧本

专文：[`projects/LingWen1/docs/dual-playbook.md`](../../projects/LingWen1/docs/dual-playbook.md)

各发**一句**验收话术（维护态 + 新书态各 1 条）。自动化：`bash scripts/butler-wechat-dual-playbook-probe.sh --quick`（静态必跑；有 LLM key 时跑 handler sim）。

### B2 · 微信「测试」闭环

Lead **不**亲自 `terminal`；测试走 runtime 只读 job 或 `delegate_task` → dev：

```
请委派开发代理：在项目内只跑 pytest tests/test_inbound_media.py -q，汇报通过/失败，不要改其它文件。
```

### B3 · Lead 只读 job 复验

```
/运行 factory-status-daily
```

预期：摘要含 phase/step；audit 写入 `~/.butler/runtime/runs/`。

### B4 · 试点文档索引

[`projects/LingWen1/docs/README.md`](../../projects/LingWen1/docs/README.md)

---

## Agent 故障 10 分钟（AP-6）

> 结构化事件：`butler/core/structured_events.py` · 报告：`.butler/reports/tcr-latest.json`

| 分钟 | 动作 | 命令/入口 |
|------|------|-----------|
| 0–2 | 看进程指标与降级计数 | `python -c "from butler.ops import runtime_metrics; print(runtime_metrics.snapshot_global())"` |
| 2–4 | 区分 LLM vs 检索 | 查 `llm_api_call` / `retrieval_degraded` 计数；`/诊断 详细` RAG 行 |
| 4–6 | LangFuse（若开） | `BUTLER_LANGFUSE_ENABLED=1` trace 按 session |
| 6–8 | Loop 终止原因 | `/诊断` → `LoopTransitionReason` |
| 8–10 | 语义层（最后） | `transcript.jsonl` 工具行；勿先捞全文 prompt |

脚本：`bash scripts/butler-gap-observability.sh`（含 boundary + structured 摘要）

---

## Phase 4 完成标准

| ID | 完成条件 |
|----|----------|
| A1 | 首周观察表勾选 + consistency CLI 或定时摘要有记录 |
| A2 | inbound pytest 绿 + M-img/M-voice 真机各 1 次（或登记暂缓原因） |
| A3 | `test_approve_mutating_one_shot` 绿 + 真机 `/运行` mutating 被拒 |
| A4 | 团队约定 `--tier` 并写入本 runbook |
| A5 | `/成本` 与账单对照记录 1 份 |
| B1 | dual-playbook 文档 + `butler-wechat-dual-playbook-probe.sh` |
| B2 | dev 委派 pytest 闭环 1 次 |
| B3 | `/运行 factory-status-daily` 有 audit |
| B4 | `docs/README.md` 索引无重复清单 |

完成后进入 **Phase 5**：O9（LLM 端到端基准 B9）+ 轨道 C（多项目）。
