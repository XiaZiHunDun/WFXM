# WFXM 黑板班次摘要流

> append-only：每个班次结束追加一段 1-3 行摘要。
> 不要修改历史条目；纠错请追加新条目并说明"修正 N 的 XX 字段"。

---
## 2026-07-13-claude-code-001 · claude-code

黑板体系首张班次卡：spec + 实施计划提交；验证手工写卡流程跑通。
下一班：Phase 2/3（写第一张卡 + validator + CLI）。

## 2026-07-13-cursor-001 · cursor

模拟 Cursor 班次：调整 log.md 格式；测试异构 Agent 流程。

## 2026-07-13-codex-001 · codex

模拟 Codex 班次：读 README 后改 .gitkeep；验证异构 Agent schema 一致性。

## 2026-07-13-claude-code-002 · claude-code

Phase 5 验收：Cursor/Codex 异构演练通过；fast gate 绿；44 测试 / 91% 覆盖；
docs/README.md 导航就位；20/20 任务收口。下一阶段接 Stop hook hard gate。

## 2026-07-13-claude-code-003 · claude-code

P1 #4 content vs dev 委派边界硬化：从 brainstorming 8 问到 subagent-driven 8 task
完整跑完。10 commit / 27 单测 / 4-case smoke ALL PASS / 守门 26 passed。
抓出 3 个 spec 假设错（hook framework 已存在、.butler/ gitignore、smoke bash bug）；
已写入 feedback memory。下次会话读 state + 本卡即可接活。

## 2026-07-14-claude-code-001 · claude-code

G2-08 CA4 strict pilot opt-in + 基础设施实证：从 ⏸️ 搁置 → ✅ pilot opt-in。
brainstorming 5 问 → writing-plans 8 task → subagent-driven 完整跑 6 阶段。
8 commit + 1 revert + 1 修复；11/11 测试矩阵全过（3 pytest + 4 bash opt-in + 4 bash Phase A）。
Phase B 真 sample deferred — `ch001-reproduce` 不在 `delegate_impl` task registry；
用户拍板走"回退 T6 + 接受基础设施实证"路径。pilot runner 已修空 grep bug，可下次复用。
详见 pilot-log §G2-08 + caveat `pilot-report-G2-08-2026-07-14-caveat.md`。

## 2026-07-14-claude-code-002 · claude-code

G2-08 Phase B 真 pilot — 端到端 4-gate chain 实证（verdict MATCH, 捕获率 100% 2/2）。
Rewrite pilot runner 从 `python3 -m butler.tools.delegate_impl` 错路径 → 真实
`apply_delegate_success_gates` 4-gate 链；dev_engine fixture 与 `_run_auto_verify`
真实产出数据形态一致。修了 runner script 的 for 循环死循环（IFS 切词 bug）。
4 文档口径从 deferred 升级为 MATCH；pilot-log §G2-08 段更新；黑板 G2-08 状态升级。
下次会话：决策 BUTLER_CODING_STRICT 默认是否升级（0 → 1）。

## 2026-07-14-claude-code-003 · claude-code

G2-08 BUTLER_CODING_STRICT 默认升级决策：**DEFER** 至 G3 1-2 周观察窗口。
基于 Phase B MATCH 100% 但 2/2 sample 不足估计 production false positive 率；
改 `"0" → "1"` 推迟至 ≥3 任务类型 + 0 false positive + ≥85% capture rate 三条件满足。
写 `docs/plans/decisions/butler-coding-strict-default-decision-2026-07-14.md`（新建）；
5 文档口径同步（config/reference + v4-dev-engine-theory + gap register §0/§2/§6 + post-consolidation-roadmap D3-10/§9 + pilot-log）。
3/3 测试无回归（直接 Python 验，pytest dotenv 缺包未跑）；pilot runner 跑通；opt-in off 复位。
下次会话：累计 G3 观察窗口真 subagent pilot。

## 2026-07-14-claude-code-004 · claude-code

G3 首批 multi-category 累计。修 runner 两个 bug：
Python `|||` 被 `tr` 当字符类拆分 → 改 JSON 透传 + Python 二次解析（CA4+T8 fixture 还原 2/2）；
缺 EXIT/INT/TERM trap → 加 `cleanup_strict` + 3 信号 trap 防 strict 残留 on。
跑 3 cats × 2 cases + smoke：**3/3 MATCH 100% + 0 false positive**（quick 1/1、deep 2/2、lingwen-drill 2/2）；smoke rc=0；
报告 `docs/plans/pilot-reports/pilot-report-G3-2026-07-14-001.md`；
决策文档追加 "G3 progress" 段（仍注明 fixture-driven + 同属 dev role + 升级未触发）；
pilot-log §G2-08 追加 G3 首批行；shift 004 + 黑板收口。
strict off 复位。下次会话：构造绕过 circular import 的 test harness 拿真 subagent 实证（content 类）。

## 2026-07-16-claude-code-001 · claude-code

Agent Loop 主要流程优化（P0-P2）完成。P0：智能工具选择集成 + 工具执行优化（缓存/去重/监控）；
P1：预回合经验注入 + 对话结束经验写入；P2：语义感知上下文压缩（关键词提取 + 语义保护）。
验证：工具缓存 call_count=1、经验读写正常、语义保护 middle从8→0。
下次会话：按计划接后续优化或 G3 真 subagent pilot。
