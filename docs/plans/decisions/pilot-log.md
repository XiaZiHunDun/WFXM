# Pilot Log — 关键 pilot 决策与基线汇总

> append-only：每个 pilot 完成（含 deferred）追加一段；纠错请追加新条目并说明"修正 N 的 XX 字段"。

---

## §G2-08 — 2026-07-13→14 CA4 strict pilot opt-in + 首次基础设施实证

- **范围**：G2-08 从 ⏸️ 搁置 → ✅ pilot opt-in（infrastructure verified）+ Phase B 真 sample **deferred**
- **决策**：全套 6 阶段中执行 5 阶段（文档同步 + 默认协调 + opt-in + Phase A + 退出）；阶段 5（Phase B 真 pilot）因 sample task 未触发 gate 链，回退走 caveat 路径
- **交付**：
  - 7 commit（`b1f1173e` spec + `68d0625d` plan + `7215a5a1` 默认协调 + `d554730b` opt-in 脚本 + `57067269` Phase A smoke + `d7a42913`/`ce397817` pilot runner + `23fe0f57` 4 文档口径 + `505e81b2` pilot 回退 + `b281fab9` caveat + 4 文档 deferred 同步）
  - 11/11 测试矩阵全过：3 pytest（env_unset/env_set/default_false）+ 4 bash opt-in（on/off/status/audit）+ 4 bash Phase A（gate 4 case）
  - pilot runner 脚本 bug 修复（set -uo pipefail 下空 grep 兜底）
- **结果**：
  - Phase A：4 case gate 机制实证通过（含 strict=1+dev+deep+violated → 阻断 True/CODING_STRICT_GATE）
  - Phase B：**deferred** — `ch001-reproduce` 不在 `butler.tools.delegate_impl` task registry，未触发 gate 链；runner 脚本已修 bug，下次会话复用
- **关键决策点（用户拍板）**：
  - 路径 A：回退 T6 commit + 接受 infrastructure verified + Phase B 推迟（**用户选择**）
  - 不走 fixture 注入（spec §4 阶段 5 要求真实任务）
  - 不强行找任务（需下次会话专门立项辨识哪个 task 能产出 `coding_knowledge.violated`）
- **下次会话建议**：
  - 在 `butler.tools.delegate_impl` 现有 task map 中 grep 真实 dev 任务，先 strict=0 dry-run 验 stdout 含 `violated` 字段，再 strict=1 重跑
  - runner 脚本已修空 grep bug，可直接复用 `scripts/butler-coding-strict-pilot.sh`
  - 真 pilot 出 ≥ 85% 捕获率 ≥ 2 sample 后，再决策是否把 `BUTLER_CODING_STRICT` 默认从 0 升 1
- **关联**：
  - spec: `docs/superpowers/specs/2026-07-13-g2-08-strict-pilot-design.md`
  - plan: `docs/superpowers/plans/2026-07-13-g2-08-strict-pilot.md`
  - caveat: `docs/plans/pilot-reports/pilot-report-G2-08-2026-07-14-caveat.md`
  - shift 卡: `.blackboard/shifts/2026-07-14-claude-code-001.md`
