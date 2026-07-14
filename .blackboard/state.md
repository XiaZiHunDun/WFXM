# WFXM BlackBoard State

_last_synced: 2026-07-14 15:00_
_last_shift: 2026-07-14-claude-code-001_

## 进行中
（暂无）

## 待仲裁 / 阻塞
- G2-08 Phase B 真 sample 任务选择（需用户口径或在 delegate_impl task map 立项辨识哪个能产出 coding_knowledge.violated）

## 待认领
- 详见 `tasks/backlog.yaml`
- 已交付 P0/P1/P2/G2 全部收口（仅 P2 #10 + G2-08 Phase B deferred）

## 已交付（本会话）
- **G2-08 CA4 严格模式 pilot opt-in + 基础设施实证**（2026-07-14 14:00–15:00）
  - spec + plan：6 阶段全套 + 11 case 测试矩阵
  - `effective_coding_strict_safe(default=True → False)` + `effective_coding_knowledge_strict_safe` wrapper 默认协调
  - `tests/dev_engine/test_coding_strict_default.py`：3 pytest
  - `scripts/butler-coding-strict-opt-in.sh`：运维 on/off/status/audit
  - `tests/scripts/test_butler_coding_strict_opt_in_smoke.sh`：4 case bash smoke
  - `scripts/butler-coding-strict-pilot-smoke.sh`：Phase A 控型 4 case gate 实证
  - `scripts/butler-coding-strict-pilot.sh`：Phase B runner skeleton + 空 grep bug 修复
  - `docs/plans/pilot-reports/pilot-report-G2-08-2026-07-14-caveat.md`：Phase B deferred caveat
  - 4 文档口径同步（gap register / v4-dev-engine-theory / config reference / post-consolidation-roadmap）
  - `docs/plans/decisions/pilot-log.md` §G2-08 段
  - 9 commit `b1f1173e → b281fab9`（含 1 revert）；11/11 测试矩阵 ALL PASS；opt-in off 已退出严格

## 最近 5 个班次
- 2026-07-14-claude-code-001: G2-08 CA4 strict pilot opt-in + 基础设施实证 — spec→plan→6 阶段→11/11 测试→Phase B sample deferred
- 2026-07-13-claude-code-003: P1 #4 content vs dev 委派边界硬化 — spec→plan→TDD→hook→10 单测→smoke→loader 扩→配置收口
- 2026-07-13-claude-code-002: Phase 5 验收 — Cursor/Codex 异构 Agent 演练
- 2026-07-13-codex-001: 模拟 Codex 班次：读 README 后改 .blackboard/tasks/claims/.gitkeep
- 2026-07-13-cursor-001: 模拟 Cursor 班次：调整 log.md 格式

## 后续任务建议（用户主导）

### 已交付 — 2 个 deferred
- P0 #1/#2/#3/#3a + P1 #4/#5/#6/#7 + P2 #8/#9 + G2-08 全部 ✅（G2-08 Phase B 真 sample 待补）
- **P2 #10 publish-archive/publish-merge 审批流** — 已配齐（`enabled: false` + `approval.required: true`），不动除非演示需 smoke
- **G2-08 Phase B** — runner 脚本可复用，需在 `butler.tools.delegate_impl` task map 选真实 dev 任务再跑；阈值 85%

### 候选（新 scope，需用户拍板）
- **G1-02 成本标定**（gap register ⏸️）— 是否启动？
- 14 份 `plans/active/` 持续规划文档 — 多数为对照/收口挂载点，等主线触发

### 工作区卫生（提醒）
- `.claude/` 未跟踪未提交
- `projects/LingWen1/docs/interview-明天演示.md` 未跟踪未提交
- `.butler/todos.json` 引用但当前不存在，需用户口径确认

### 下次会话
按 README §会话开始：读 state.md + 最新 shift 卡 → 接活。
优先：G2-08 Phase B 真 sample 任务选择（preflight：在 delegate_impl task map grep 现有 dev 任务能产出 coding_knowledge.violated 的）。