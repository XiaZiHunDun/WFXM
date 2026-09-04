# v5 真 LLM run_command over-trigger 决策（A10/C10）

> **Decision date**: 2026-09-04
> **Decision owner**: claude-code (with user ratification)
> **Status**: 待 owner 拍板 — 3 选项协议
> **关联**: `v5-real-llm-degradation-fixes-2026-09.md` §5 P2；录音 baseline `recordings/A10.json` + `recordings/C10.json`

---

## TL;DR

**真 LLM 录音暴露**：A10 和 C10 都触发 run_command 走 approval，而 fixture 期望不需 approval。

**实际命令（PRD §3 推测 `git log` 与现实不符，纠正如下）：**

- **A10**: 模型用 `find . -maxdepth 3 -name package.json`（试图找包结构以理解测试 runner 上下文）
- **C10**: 模型用 `find . -maxdepth 2 -iname readme* -type f`（试图找 README 路径）

**fixture 期望**：用 `read_file` 直接读目标文件，不走 run_command。

**评估焦点**：本质不是 "fixture 偏松 vs policy 偏严"，而是**模型错选工具语义**。`find . -name <pattern>` 不带 `-exec` / `-delete` / `-fprint` 等写参数确实是 read-only，但 fixture 不希望走 run_command 这条路。

## 输入证据

| 来源 | 类型 | 结果 |
|---|---|---|
| 录音 `recordings/A10.json` | 模型 turn 1 | toolCalls=6（含 find 命令），reply="[待审批] Confirm run_command on find . -maxdepth 3 -name package.json?" |
| 录音 `recordings/C10.json` | 模型 turn 1 | toolCalls=2，reply="[待审批] Confirm run_command on find . -maxdepth 2 -iname readme* -type f?" |
| fixture `A10` | 期望 | plan: `[read_file("packages/runtime/src/run-engine.test.ts"), text(...)]`，finalDecision=Respond |
| fixture `C10` | 期望 | plan: `[read_file("README.md"), text(...)]`，finalDecision=Respond |
| policy `packages/domain/src/governance/types.ts:155-193` | read-only 白名单 | 9 always-readonly (cat/head/wc/grep/rg/ls/pwd/date/echo) + git log/diff/status/show + pnpm typecheck/test；**`find` 不在列** |
| policy `d226f33f` | recent commit | 已实现 read-only bypass for owner subject |

## 分析

### 三方责任分摊

| 方 | 在此 case 的角色 | 评价 |
|---|---|---|
| **fixture (期望)** | 表达设计意图："读文件用 read_file" | 合理 — v5 设计意图是 read_file 直接走，不绕 run_command |
| **policy-gate (现状)** | 守住 run_command 入口 | 合理 — `find` 默认 false 触发 approval 是保守安全姿势 |
| **真 LLM 行为** | 错选工具：应用 find 而不是 read_file | **真正问题源** |

### "find 命令本身" 安全评估

`find . -maxdepth N -name pattern` 在不附加 `-exec` / `-delete` / `-fprint` / `-ok` 等参数时确实是 read-only。但：

- 加 `-exec rm {} \;` 可执行任意命令 → 风险高
- 白名单若扩 `find` 整体，需扫所有 sub-flag 防漏
- 模型若误带 `-fprint /tmp/x` 写文件 → approval 被 bypass → 真安全洞

**结论**：保守白名单不扩 `find`，但模型不该走到这条路径。

## 3 选项

### 选项 1 — **fixture 偏松**（推荐 = 立场 A）

**立场**：read-only `find` 不需要 approval。扩白名单包含 `find`。

**理由**：
- `find . -name pattern` 语义上 read-only（不写文件、不发请求）
- fixture 期望不触发 approval 与 policy 期望一致 → fixture 偏松
- 用户已经习惯 `find` 是探索工具，类似 `ls`/`grep`
- 实施简单：1 行扩 `ALWAYS_READONLY` set

**风险**：
- 模型若加 `-exec` / `-delete` → 被 bypass → 安全洞
- 缓解：扩白名单同时检查 argv 全集含 `-exec`/`-delete`/`-fprint`/`-ok` 时拒绝 bypass

### 选项 2 — **policy 偏严**（立场 B）

**立场**：read-only 概念本身太宽。任何含 flag 的 read-only 命令应走 approval。

**理由**：
- 模型可能误带 flag；白名单的细粒度难维护
- approval 不打断用户流程（owner subject 1-tap "确认"）
- fixture 期望对齐 policy = approval 即 default；fixture 需更新显式 `requireApproval: false`

**风险**：
- 用户体验回归：`pnpm test` / `git log` 频繁走 approval → 羊群效应（参见 d226f33f 提交原因）
- 实质撤销 P1 修复

### 选项 3 — **模型错选工具**（立场 C）

**立场**：真问题是模型选错工具（应用 read_file 而非 find via run_command），不是 policy 或 fixture 的张力。

**理由**：
- A10 input = "加 unit test 覆盖 conflict 路径"，模型反应应先 read_file 看现有测试 → fixture 表达的意图是"v5 已有 ActiveMainRunConflict 测试，先 read 再判断是否补"
- C10 input = "Read README"，明确要 read_file，模型却用 find 找 README 路径
- fixture 期望 read_file 路径是合理 UX 指引
- 这不是 fixture-vs-policy 冲突，而是 prompt 不够收敛

**风险**：
- 改 prompt 影响所有场景，不能单独验证这一 case 改善
- 需要新增 evaluation scenario 跟踪模型 tool selection 趋势

## 推荐

**立场 C**（选项 3）— 因果链正确：模型错选工具是因，approval over-trigger 是果。

**理由**：
- 选项 1（扩 find 白名单）治标不治本，模型下个版本可能用别的工具
- 选项 2（policy 偏严）撤销 d226f33f 已 ship 的 UX 修复
- 选项 3 改 prompt 直接对症：plan role 加 "先用 read_file 探索路径，避免 run_command 找文件"

**P3 落地动作**（接 PRD P3 decoder retry 序列）：
1. PRD §3 描述修正：`A10`/`C10` 不是 `git log`，是 `find` 命令
2. PRD P2 标 ✅（decision 落地）
3. PRD 新增 P2.5：plan role prompt 加 read_file-first 提示（仅选项 3 路径）
4. 重跑 35 录音验证 A10/C10 决策回到 Respond（不需 approval）
5. 评估模型行为变化：toolCalls 数 / latency / "thinking" 是否收敛

## 待 owner 决策

```markdown
# 选项 1: 扩 read-only 白名单（含 `find`）
# 选项 2: 收紧 policy（任何 run_command 都走 approval；fixture 显式 opt-out）
# 选项 3: 改 prompt 引导 read_file 优先（推荐）
```

Owner 拍板后：(a) PRD §6 更新决策记录；(b) 按选定选项开子任务；(c) 重跑录音验证。