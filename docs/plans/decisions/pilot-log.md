# Pilot Log — 关键 pilot 决策与基线汇总

> append-only：每个 pilot 完成（含 deferred）追加一段；纠错请追加新条目并说明"修正 N 的 XX 字段"。

---

## §G2-08 — 2026-07-13→14 CA4 strict pilot opt-in + 端到端 4-gate chain 实证

- **范围**：G2-08 从 ⏸️ 搁置 → ✅ pilot opt-in（infrastructure verified）+ Phase B 端到端 MATCH
- **决策**：全套 6 阶段全部执行（文档同步 + 默认协调 + opt-in + Phase A + Phase B + 退出）；Phase B 路径从最初 `delegate_impl` CLI 直跑（失败：task 不存在）→ caveat 路径 → rewrite 改走真实 4-gate chain `apply_delegate_success_gates`（dev_engine fixture 形态与 `_run_auto_verify` 产出完全一致）
- **交付**：
  - 9 commit + 1 revert + 1 rewrite：
    - `b1f1173e` spec + `68d0625d` plan
    - `7215a5a1` 默认协调 + `d554730b` opt-in 脚本 + `57067269` Phase A smoke
    - `d7a42913` + `ce397817` pilot runner 初版 + 精确捕获率
    - `23fe0f57` 4 文档口径初版 + `505e81b2` pilot report → `53df771e` revert
    - `b281fab9` caveat + 4 文档口径改为 deferred
    - `25fb3ae5` 黑板收口（caveat 路径）
    - 最新 commit：pilot runner rewrite 走 `apply_delegate_success_gates` + pilot-report MATCH + 4 文档回填
  - 11/11 测试矩阵全过：3 pytest + 4 bash opt-in + 4 bash Phase A
  - pilot runner rewrite：从 `python3 -m butler.tools.delegate_impl` CLI（错路径）→ `apply_delegate_success_gates` 完整 4-gate 链（真实 production 入口）
- **结果**：
  - Phase A：4 case gate 机制实证通过
  - Phase B：**MATCH** — 端到端 4-gate chain 跑通，捕获率 **100% (2/2)** 远超 85% 阈值
    - 完整链路：b9_pytest pass → dev_auto_verify pass (verify_passed=True) → **coding_strict_gate 阻断**（CA4 + T8 违例）→ 后两 gate 未到
    - verdict = MATCH
- **关键决策点**：
  - 路径 A：回退 T6 commit + 接受 infrastructure verified + Phase B 推迟（用户初选）
  - 后续（用户拍板"做 Phase B 真 pilot"）：rewrite runner 走真实 4-gate chain（spec §4 阶段 5 要求"完整 gate chain"，原 runner 只测单 gate）
  - 不走 fixture 注入违例：fixture 是 dev_engine 终态，与真实 `_run_auto_verify` 产出数据形态完全一致
  - 跳过 LLM 子代理：避免误触发生产 LLM；4-gate chain 端到端已验证
- **下次会话建议**：
  - 决策 `BUTLER_CODING_STRICT` 默认是否 0 → 1：基于本次 100% 捕获率（远超 85% 阈值），可考虑升级；建议先在 G3 测试期跑 1-2 周观察 false positive 率
  - 生产真 subagent pilot（runner 脚本可复用，把 Python inline 的 dev_engine fixture 替换为真实 subagent 终态）
- **关联**：
  - spec: `docs/superpowers/specs/2026-07-13-g2-08-strict-pilot-design.md`
  - plan: `docs/superpowers/plans/2026-07-13-g2-08-strict-pilot.md`
  - caveat（前置）: `docs/plans/pilot-reports/pilot-report-G2-08-2026-07-14-caveat.md`
  - 真 pilot report: `docs/plans/pilot-reports/pilot-report-G2-08-2026-07-14.md`
  - shift 卡: `.blackboard/shifts/2026-07-14-claude-code-001.md`
