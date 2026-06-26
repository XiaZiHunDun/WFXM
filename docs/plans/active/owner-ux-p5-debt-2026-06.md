# PROD-P5 — Owner UX 债（真机暴露 · 2026-06）

> **状态**：立项 **2026-06-26** · 与 G1-04 观测窗并行（不挡 07-31 结案）  
> **登记**：[`roadmap-backlog` §3.9](../decisions/roadmap-backlog-and-boundaries-2026-05.md#39-产品体验-p5--真机-ux-债2026-06)  
> **前置**：PROD-P3/P4 ✅ · EXT-5 Verify 真机 ✅（[`ext5-wechat-phrases-card`](../../guides/ext5-wechat-phrases-card-2026-06.md)）  
> **证据会话**：2026-06-26 微信真机（灵文1号 · `wechat:…:灵文1号`）

---

## 0. 背景

P4 旅程收敛与 EXT-5 真机已功能通过，但 Owner 侧出现三类**可复现 UX 债**。功能结果正确，但**消息时序、意图路由、验收语义**增加认知负担。

**原则**（延续 P4）：

- 少反问、多执行；manifest 话术应 **一次到位**
- 完成卡只推 **与本条入站相关** 的任务
- ingest / 长期记忆 / 写盘 三路径 **人话可区分**

**不做**（§1 否决延续）：

- 微信内 diff 阅读器 · 取消 terminal 白名单 · 多 Owner Seat

---

## 1. 真机证据摘要

| 时间 | 现象 | task / 文件 |
|------|------|-------------|
| 11:44–11:45 | #2/#3 秒回 **11:33** 旧卡 `task_a2b748f6d218` | 自动化 sim 迟推 |
| 11:45–11:55 | 「放进记忆」→ 反问 `butler_remember` vs 写盘 | 未走 ingest |
| 12:21 | 新消息先收到 **11:46** `task_e4efa4c207b6` 完成卡 | outbox / pending 时序 |
| 12:21–12:22 | ingest 请求走 **dev 委派** + `DEV_VERIFY_GATE` | `task_809e46e118d9` |
| 12:22 | ingest 文件落盘 ✅ | `projects/LingWen1/.butler/ingest/ext5-fixture-sample.md` |

---

## 2. 立项表

| ID | 名称 | 批次 | 优先级 | 状态 |
|----|------|------|--------|------|
| PROD-P5-01 | 委派完成卡去陈旧（task 年龄 / outbox） | P5-A | **P0** | **done** 2026-06-26 |
| PROD-P5-02 | ingest 意图预路由（manifest 话术） | P5-B | **P0** | backlog |
| PROD-P5-03 | ingest/只读写盘跳过 DEV_VERIFY_GATE | P5-C | P1 | backlog |

**建议顺序**：P5-A → P5-B → P5-C（A 影响所有委派场景；B 解 EXT-5 #3 真机痛点；C 降验收卡噪声）。

---

## 3. PROD-P5-01 · 委派完成卡去陈旧

### 问题

后台委派完成推送（`completion_notify` · `durable_outbox`）可在 **新入站 turn 开头** 或与 **无关 task_id** 叠出，Owner 看到「已完成」但时间戳是上一轮（例：12:21 收到 11:46 的 `task_e4efa4c207b6`）。

### 范围

| 做 | 不做 |
|----|------|
| 完成卡携带 `task_id` + `completed_at`；推送前比对 **当前 turn 开始时间** | 取消后台委派通知 |
| outbox replay 跳过 **已完成且已推送** 且 **早于本会话最后活跃** 的 delegate 项 | 合并多条完成卡为长文 |
| 同 session 同 `task_id` **去重**（N 分钟内不重复推） | |
| handler sim：入站 B 时不推 task A 的完成卡 | |

### 触点（实现参考）

- `butler/gateway/completion_notify.py` — `flush_pending_delegate_completion` · `deliver_completion_push`
- `butler/gateway/durable_outbox.py` — replay / TTL
- `butler/gateway/outbound_bridge.py` — `_pending_delegate_report` 生命周期
- `butler/runtime/delegate_job.py` — 完成时间与 task 元数据

### 验收

1. **单元**：task 完成时间 &lt; turn_start − ε → 不 schedule push  
2. **handler sim**（`owner-p5` track）：  
   - 步骤1 触发慢委派 task_A  
   - 步骤2 在 A 完成前发无关短消息 → 仅短回复，**无** A 完成卡  
   - 步骤3 A 完成后发新消息 → **仅一条** A 完成卡，含正确 task_id  
3. **真机**：连续两条不同意图消息，第二条**不**附带第一条的旧 task 卡  

守门：`bash scripts/butler-owner-ux-p5-gate.sh`（P5-01 子集）

---

## 4. PROD-P5-02 · ingest 意图预路由

### 问题

Owner 说「转成 Markdown **放进记忆**」时，Lead 混淆：

- `butler_remember` / MEMORY 长期约定  
- content 写 `docs/`  
- EXT-5 **document ingest** → `{workspace}/.butler/ingest/*.md`

manifest 话术（[`.butler/extensions/markitdown-ingest/manifest.yaml`](../../../.butler/extensions/markitdown-ingest/manifest.yaml)）在 handler sim 可 PASS，真机却多轮反问。

### 范围

| 做 | 不做 |
|----|------|
| 入站 **pre-dispatch**（对齐 `/改`）：匹配 ingest 短语 → 展开为带 **ingest / MarkItDown MCP / .butler/ingest** 的 NL | 删除自然语言 ingest |
| 关键词：`放进记忆` + (`ingest` \| `markitdown` \| `pdf` \| `参考书` \| fixture 路径) | 自动 `butler_remember` |
| 命中时 **优先** `mcp_markitdown_convert_to_markdown` 或 `document_ingest.ingest_file` | 新 slash 命令（可选后续 `/ingest`） |
| 回复模板含 **ingest 路径** 一行 | |

### 触点

- 新建或扩展 `butler/gateway/owner_ingest_shortcuts.py`（mirror `owner_delegate_shortcuts.py`）
- `butler/gateway/inbound_pipeline.py` — `_phase_apply_pre_dispatch_rewrites`
- `.butler/simulation/wechat-owner-scenarios.yaml` — `owner-p5` / `ext5` 回归

### 验收

1. 微信（或 handler sim）发：  
   `把 docs/ext5-fixture-sample.txt 转成 Markdown 放进记忆`  
   → **一轮内**执行（或明确委派 content/MCP），回复含 `ingest` 或 `.butler/ingest/`  
2. **不**出现「butler_remember / 长期记忆太短」式反问（除非 Owner 明确说「请记住」）  
3. sim 对齐 EXT-5 话术卡 #3  

守门：P5-02 并入 `butler-owner-ux-p5-gate.sh` + `butler-extension-ext5-wechat-sim.sh` 回归

---

## 5. PROD-P5-03 · ingest 任务验收语义

### 问题

ingest / 只读写盘走 **dev 委派** 时触发 `DEV_VERIFY_GATE`（`BUTLER_DEV_VERIFY_SUCCESS_GATE=1`），验收卡显示「未通过验证」，Owner 误以为失败。真机 `task_809e46e118d9`：新建 1 文件 + gate 误报。

### 范围

| 做 | 不做 |
|----|------|
| 委派 meta 标记 `task_kind=ingest` \| `content_write` \| `readonly_check` | 关闭全局 DEV_VERIFY_GATE |
| 上述 kind **不** 应用 dev verify 失败 → `success=false` | 跳过真实 dev 代码任务的 verify |
| 验收卡：ingest → 「验证：—（ingest 写盘）」；测试行仍反映 project.yaml | |
| content 委派写 `.butler/ingest/` 默认走 content role | |

### 触点

- `butler/dev_engine/b9_delegate_gate.py`
- `butler/tools/delegate_phases.py` — attach meta
- `butler/report/acceptance_card.py`

### 验收

1. sim：ingest 委派成功 → `success=True` · 验收卡无 `DEV_VERIFY_GATE`  
2. sim：真实 dev 改代码且 verify 失败 → 仍 `DEV_VERIFY_GATE`  
3. 真机 EXT-5 #3 复跑：绿勾或无 ⚠️ gate 行  

---

## 6. 批次与工期（估算）

```text
P5-A（1–2 周）  P5-01 完成卡去陈旧 + outbox 去重
P5-B（1–2 周）  P5-02 ingest 预路由 + EXT-5 #3 sim 硬断言
P5-C（1 周）    P5-03 验收卡 / verify gate 分流
```

与 **G1-04 观测** 并行：每周 `butler-g1-04-weekly-checkin.sh --log` 不中断。

---

## 7. 守门链（目标态）

```bash
bash scripts/butler-owner-ux-p5-gate.sh          # P5 单元 + 计划验收（跳过的 backlog 测试）
bash scripts/butler-owner-ux-p4-gate.sh          # P4 回归
bash scripts/butler-extension-ext5-wechat-sim.sh # EXT-5 回归
bash scripts/butler-owner-week1-ops-sim.sh       # 首周节奏
```

---

## 8. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-06-26 | **P5-A** delegate push dedup + defer-during-inbound + max-age（PROD-P5-01） |
| 2026-06-26 | 立项：P5-01～03 · 真机证据 · 批次 P5-A/B/C |
