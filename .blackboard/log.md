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

## 2026-08-04-claude-code-001 · claude-code

窄域 schema 修复：`.claude/settings.json` 三个 hook entry（PreToolUse / PostToolUse / Stop）补 `matcher: ""` 与 `hooks: [{type:"command", command:...}]`，三条 `Expected array, but received undefined` 警告消失；guard 脚本自身不动；未 commit（工作区另有非本班改动）。
下次会话：建议用 sentinel 法实测一次 hook 触发，并就本班 commit 边界（仅黑板变更 vs 一并收拢旧改动）做决断。

## 2026-08-08-claude-code-001 · claude-code

生成 WFXM 最新项目状态报告：确认 Butler v4 为 Python 主线、butler-v5 为未跟踪 TypeScript 原型，并记录当前 WIP、测试结果、文档漂移和收口风险。
验证：v4 WIP 相关测试 703 passed、v5 typecheck 通过；v5 lint、docs broken-links 与完整 fast gate 分别存在已记录问题，未提交代码。

## 2026-08-12-claude-code-013 · claude-code
R9 marker commit — 触发 GitHub Actions 跑 butler-v5-gate 新 job（commit 0db36aad）。Owner 推 main 后观察 Actions tab 验证 5-gate 全绿。

## 2026-08-19-cursor-033 · cursor
R8.x.10 capability execution guard：子代理只投放已授权工具，未授权 tool_call 拒绝并审计；顺带修了 `delegate()` 的 `{tool}` 载荷被 worker 滤成 `[]` 的问题。21 相关测试 + format/lint/typecheck 绿。未 commit。
下次：conversationId discovery seam，或落地 `read_file`/`run_command`。

## 2026-08-19-cursor-034 · cursor
R8.x.11 client conversationId：入站可选 id + 校验；e2e 改为先开 WS 再 POST。live e2e OK（~6.5s）。format/lint/typecheck + 18 相关测试绿。
下次：push，或 reserved tools / WS subscribe token。

## 2026-08-19-cursor-035 · cursor
R8.x.12 沙箱 `read_file`/`run_command`：工作区根内读文件；argv 白名单且无 shell。71 相关测试 + lint/typecheck 绿。
下次：重启 gateway；多轮记忆 / WS subscribe token / v4 数据保留拍板。

## 2026-08-19-cursor-036 · cursor
R8.x.13 多轮记忆：稳定 `c-{project}-{user}` 流 + extractive 压缩注入 butler loop。45 相关测试绿。
下次：重启 gateway；WS subscribe token 或 v4 `~/.butler/` 保留拍板。

## 2026-08-19-cursor-037 · cursor
R8.x.14 LLM 摘要记忆：超预算旧轮次先模型摘要，失败退回抽取。30 相关测试绿。
下次：重启 gateway；WS subscribe token 或 v4 数据保留拍板。

## 2026-08-19-cursor-038 · cursor
R8.x.15 v5 自接 iLink：getupdates → inbound → sendmessage；12 测试绿。默认关闭。
下次：在 live env 开 `BUTLER_V5_ILINK_ENABLED=1` 后重启 gateway。

## 2026-08-20-cursor-039 · cursor
真微信回复确认。R8.x.16 allowlist/群丢弃/媒体占位/sync_buf/`wechat-login`。19 测试绿。
下次：提交推送；然后 WS subscribe token 或 `~/.butler/` 保留拍板。

## 2026-08-20-cursor-040 · cursor
R8.x.17 `POST /v1/ws/subscribe` 签发 token；WS 支持 `?token=`。27 相关测试绿。
下次：owner 拍板 `~/.butler/` 保留；其余为可选债。

## 2026-08-20-cursor-041 · cursor
D1：`~/.butler/` 观察到 2026-09-18 再删；现在不动磁盘。
下次：可选债清账。

## 2026-08-20-cursor-042 · cursor
R8.x.18：生产 event_store 走 Docker Postgres。
下次：提交推送。

## 2026-08-20-cursor-043 · cursor
可选债清账：做入站媒体；不做无名单扩容与嵌套 architecture 门禁。
下次：R8.x.19。

## 2026-08-20-cursor-044 · cursor
R8.x.19 入站 CDN 媒体。
下次：提交推送。

## 2026-08-20-cursor-045 · cursor
四项跟进裁决：立项 ASR/出站/窄白名单；architecture 门禁不立项。
下次：R8.x.22。

## 2026-08-20-cursor-046 · cursor
立项 ASR/出站/窄白名单；R8.x.22 语音转写落地（voice_item.text + DashScope wav/mp3；silk 不解）。30 相关测试绿。
下次：R8.x.21 出站发图。

## 2026-08-20-cursor-048 · cursor
R8.x.21 已推送；R8.x.20 `run_command` 具名扩容（rg/grep/python3/pnpm/node）。
下次：日历 D1（2026-09-18 后再删 ~/.butler/）。
