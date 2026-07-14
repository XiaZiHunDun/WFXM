# WFXM BlackBoard State

_last_synced: 2026-07-14 18:00_
_last_shift: 2026-07-14-claude-code-004_

## 进行中
（暂无）

## 待仲裁 / 阻塞
（无 — BUTLER_CODING_STRICT 默认升级仍 DEFER 至 G3 观察窗口；首批 multi-category 已落 evidence）

## 待认领
- 详见 `tasks/backlog.yaml`
- 已交付 P0/P1/P2/G2 全部收口（仅 P2 #10 deferred）
- G3 观察窗口累计（真 subagent pilot ≥3 任务类型）

## 已交付（本会话）
- **G2-08 CA4 严格模式 pilot opt-in + Phase B 端到端 MATCH**（2026-07-14 14:00–16:00）
  - 第 1 班 (15:00): infrastructure verified — 11/11 测试全过 + caveat 路径收口
  - 第 2 班 (16:00): Phase B 真 pilot — rewrite runner 走真实 `apply_delegate_success_gates` 4-gate chain；dev_engine fixture 与 `_run_auto_verify` 真实产出形态一致；**verdict MATCH 捕获率 100% (2/2)** 远超 85% 阈值
  - 4 文档口径从 deferred 升级为 MATCH（gap register / v4-dev-engine-theory / config reference / post-consolidation-roadmap）
  - pilot-log §G2-08 段更新为 MATCH 实证
  - opt-in off 已退出严格
- **G2-08 BUTLER_CODING_STRICT 默认升级决策 defer**（2026-07-14 16:00–17:00）
  - 第 3 班 (17:00): decision doc 创建 + 5 文档口径同步（config reference / v4-dev-engine-theory / gap register §0/§2/§6 / post-consolidation-roadmap D3-10/§9 / pilot-log）
  - 决策依据：Phase B 2/2 sample 不足估计 production false positive 率；改 "0"→"1" 推迟至 G3 1-2 周观察窗口
  - 升级触发条件：≥3 任务类型 + 0 false positive + ≥85% capture rate（三者同时满足即可再拍）
  - 测试矩阵 3/3 无回归（直接 Python 验；pytest dotenv 缺包绕过）
- **G3 首批 multi-category 累计**（2026-07-14 17:00–18:00）
  - 第 4 班 (18:00): runner 修复 2 个 bug（`|||` 被字符类处理 + 缺 EXIT/INT/TERM trap）→ 改 JSON 透传 + 加 3 信号 trap
  - 3 categories × 2 cases + smoke = 6 fixture pilots + 1 smoke；**3/3 MATCH 捕获率 100%**（quick 1/1、deep 2/2、lingwen-drill 2/2）+ **0 false positive**
  - `butler exec` smoke rc=0 仅证 LLM provider 路径可达
  - 报告 `docs/plans/pilot-reports/pilot-report-G3-2026-07-14-001.md`；决策文档追加 G3 progress 段；pilot-log §G2-08 补 G3 首批行
  - opt-in off 复位（`state: off` / `BUTLER_CODING_STRICT=0` default）

## 最近 5 个班次
- 2026-07-14-claude-code-004: G3 首批 multi-category 累计 — 修 runner 2 bug + 3/3 MATCH 100% + 0 false positive
- 2026-07-14-claude-code-003: G2-08 BUTLER_CODING_STRICT 默认升级决策 — DEFER 至 G3 1-2 周观察窗口
- 2026-07-14-claude-code-002: G2-08 Phase B 真 pilot — rewrite runner 走 4-gate chain → MATCH 100% 2/2
- 2026-07-14-claude-code-001: G2-08 CA4 strict pilot opt-in + 基础设施实证 — spec→plan→6 阶段→11/11 测试→caveat 路径收口
- 2026-07-13-claude-code-003: P1 #4 content vs dev 委派边界硬化 — spec→plan→TDD→hook→10 单测→smoke→loader 扩→配置收口

## 后续任务建议（用户主导）

### 已交付 — 1 个 deferred
- P0 #1/#2/#3/#3a + P1 #4/#5/#6/#7 + P2 #8/#9 + G2-08 全部 ✅（G2-08 Phase B MATCH + 默认升级 defer 决策 + G3 首批 multi-category MATCH）
- **P2 #10 publish-archive/publish-merge 审批流** — 已配齐（`enabled: false` + `approval.required: true`），不动除非演示需 smoke
- **G2-08 BUTLER_CODING_STRICT 默认升级**（G2-08 派生）— 决策 **DEFER**，G3 1-2 周观察窗口累计；满足触发条件随时拍板

### 候选（新 scope，需用户拍板）
- **G3 真 subagent pilot（content 或非 dev role）** — 构造强制 invoke delegate_task 的 test harness 绕过 `butler.memory.diagnostics` circular import；目标补 ≥1 类非 dev 真 subagent 4-gate chain 实证（同时跑 fixture-baseline 对照）
- **G1-02 成本标定**（gap register ⏸️）— 是否启动？
- 14 份 `plans/active/` 持续规划文档 — 多数为对照/收口挂载点，等主线触发

### 工作区卫生（提醒）
- `.claude/` 未跟踪未提交
- `projects/LingWen1/docs/interview-明天演示.md` 未跟踪未提交
- `.butler/todos.json` 引用但当前不存在，需用户口径确认

### 下次会话
按 README §会话开始：读 state.md + 最新 shift 卡 → 接活。
优先：构造绕过 circular import 的 test harness 拿 content 类真 subagent 实证。