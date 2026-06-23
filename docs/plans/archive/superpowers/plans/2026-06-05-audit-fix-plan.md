# WFXM 8 轮审计 C/H 修复实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 8 轮深度审计中的 22 C + 46 H = 68 条发现,通过 8 个 PR × 68 个 commit 完成,每个 code 类型的 C/H 必须有 RED→GREEN 测试证据,文档/配置类 C/H 豁免 RED。

**Architecture:** 每个 issue 由主线程串行派发 3 个 subagent(implementer + spec-reviewer + code-quality-reviewer),8 PR 严格串行(主线程不并发),主线程持 3 个降级开关(暂停 6 次/拆分 20 commit/baseline 红)。

**Tech Stack:** Python 3.11+ / pytest / git / Bash / Claude Code subagents(`general-purpose` 代理类型)。

**Spec 引用**: `docs/plans/archive/superpowers/specs/2026-06-05-audit-fix-plan-design.md` §8 附录列出 68 条 C/H 完整 file:line。

---

## 0. 全局协议(所有 PR phase 共享)

### 0.1 分支约定

- 主分支:`main`(本计划起点)
- 8 PR 分支(顺序创建,前 PR merge 后才开下一个):
  - `fix/r1-arch`(PR-1)
  - `fix/r2-errors`(PR-2)
  - `fix/r3-security`(PR-3)
  - `fix/r4-concurrency`(PR-4)
  - `fix/r5-resources`(PR-5)
  - `fix/r6-tests`(PR-6)
  - `fix/r7-docs`(PR-7)
  - `fix/r8-config`(PR-8)

### 0.2 Commit 格式模板

```
<type>: R{n}-{id} {中文标题} ({file_path}:{line_or_range})

审计来源: docs/reviews/project-deep-audit-2026-06-r1to8.md §R{n}-{id}

<type> ∈ {fix, refactor, docs, test, chore}
```

示例:`fix: R1-4 拆分 wechat_ilink.py god module (R1-4 拆分)`(主标题) + commit body 引用审计段。

### 0.3 Subagent Prompt 模板(3 个)

#### 模板 A:Implementer subagent

```markdown
你的任务: 修复 WFXM 审计 issue R{n}-{id}。

## 输入上下文
- 审计 ID: R{n}-{id}
- 审计段: 见 docs/reviews/project-deep-audit-2026-06-r1to8.md 中 "**R{n}-{id} [{sev}] {type}**" 段落
- 涉及文件: {file_path}:{line_or_range}(从审计 doc 精确复制)
- 类型分类: {code|doc|config}(决定是否需要 RED test)

## 工作流

### Step 1: 读审计 + 读代码
1. Read 审计 doc 完整段落
2. Read 目标文件及邻近上下文(至少前后 50 行)
3. 在邻近目录找一个最近的 test_*.py 作为测试模式参考(Read 而非 Grep)

### Step 2: (仅 code 类型)RED test
1. 在 tests/ 下创建或修改对应 test_*.py
2. 写失败测试,断言修复后应有的行为
3. Run: `cd /home/ailearn/projects/WFXM && pytest {test_file_path}::{test_name} -v`
4. Expected: FAIL(因为实现尚未修复)

### Step 3: (仅 code 类型)GREEN fix
1. 修改 {file_path} 中的目标行
2. 保持改动最小化(仅修本 issue,严禁顺手改其他)
3. Run: `pytest {test_file_path}::{test_name} -v`
4. Expected: PASS

### Step 4: (仅 code 类型)Regression check
1. Run: `cd /home/ailearn/projects/WFXM && pytest tests/ -x -q 2>&1 | tail -30`
2. Expected: 没有新红测试;baseline gate 仍绿

### Step 5: (doc/config 类型)事实验证
1. 改动 .env.example / .md / config 文件
2. 用 grep 或 Read 验证改动生效
3. 列出验证证据(命令 + 输出片段)

### Step 6: Commit
- Bash: `git add {changed_files}`
- Bash: `git commit -m "$(cat <<'EOF'
{type}: R{n}-{id} {中文标题} ({file_path}:{line})

审计来源: docs/reviews/project-deep-audit-2026-06-r1to8.md §R{n}-{id}
EOF
)"`
- 注意: 本项目全局禁用 Co-Authored-By 归属,严禁添加

### Step 7: 自审
1. Bash: `git show HEAD --stat`
2. 确认:改动仅限审计 file:line 范围
3. 确认:无顺手改 M/L 类 issue
4. 报告: commit hash + 改动文件列表 + 测试命令输出

## 严禁
- 改审计 file:line 范围外的代码
- 顺手修其他 issue(包括 M/L)
- 自创 commit 标题(必须用模板)
- 跳过 RED test(code 类型)
- 修改 baseline gate 测试
- 改审计段落本身(那是文档证据,不在本计划范围)
```

#### 模板 B:Spec-compliance reviewer subagent

```markdown
你的任务: 验证 R{n}-{id} 的修复 commit 是否真正解决审计 issue。

## 输入
- Issue ID: R{n}-{id}
- 审计原文: docs/reviews/project-deep-audit-2026-06-r1to8.md 中 "**R{n}-{id} [{sev}] {type}**" 段落
- Commit hash: {commit_hash}(主线程提供)
- 改动文件: 从 `git show {commit_hash} --stat` 读取

## 检查清单
1. **问题是否真正解决?**
   - 审计描述的具体 bug / 风险 / 缺陷
   - commit 改动是否针对该缺陷?
2. **是否改到 issue 范围外?**
   - Bash: `git show {commit_hash} --stat`
   - 改动文件是否仅在审计 file:line 范围内?
   - 若涉及文件其他段落,是否有合理依据?(重构需要时 OK)
3. **是否顺手修 M/L 类 issue?**
   - 检查 commit 内容
   - 若有,标记为"超出范围,需 revert"
4. **是否引入新问题?**
   - 新代码是否引入 log_continue / silent_pass / new bug?
   - 若有,标记为"需修复"

## 输出格式
```
[APPROVED] R{n}-{id} spec 符合
或
[REJECTED] R{n}-{id}
原因: <具体列出不符合项>
建议: <修复方向>
```

## 严禁
- 改任何代码
- 修改审计 doc
- 跑 pytest(spec review 仅看 commit 内容,不动测试)
```

#### 模板 C:Code-quality reviewer subagent

```markdown
你的任务: 验证 R{n}-{id} 修复 commit 的代码质量。

## 输入
- Commit hash: {commit_hash}
- 改动文件: 从 `git show {commit_hash} --stat` 读取
- 项目现有模式参考: 主线程提供 1-2 个邻近 file_path 作为风格参考

## 检查清单
1. **PEP 8 + 类型注解**
   - 函数签名有 type hint?
   - 命名规范(小写_下划线)?
2. **可读性**
   - 函数 < 50 行?
   - 文件改动后总行数 < 800?
3. **错误处理**
   - 是否引入新的 silent pass / log_continue?
   - 是否破坏了既有 R2 修复模式?
4. **一致性**
   - 与邻近文件的代码风格一致?
   - 是否遵循现有模式(参考主线程提供的 file_path)?
5. **测试质量(若 code 类型)**
   - 测试覆盖了 issue 描述的所有场景?
   - 测试断言是否具体且无歧义?

## 输出格式
```
[APPROVED] R{n}-{id} 质量通过
或
[REJECTED] R{n}-{id}
问题: <具体列出质量问题>
建议: <改进方向>
```

## 严禁
- 改任何代码
- 跑 pytest(质量 review 仅看 commit 内容)
- 重新设计(只检查不重写)
```

### 0.4 主线程三开关

| 开关 | 阈值 | 触发后动作 |
|------|------|----------|
| **暂停** | 同一 issue 累计 subagent > 6 次未通过 | 暂停,主线程读代码+直接 Edit |
| **拆分** | 同一 PR commit > 20 或 diff > 3000 行 | 暂停,拆 sub-PR(如 `fix/r2a-errors-core`) |
| **回滚** | `pytest` 有 baseline 红 | 暂停,定位首个引入 commit,`git revert` |

### 0.5 测试基线

每次 PR 完成后主线程必跑:
```bash
cd /home/ailearn/projects/WFXM && pytest tests/ -x -q 2>&1 | tail -30
```
Expected: 全绿 + baseline gate(`test_total_violations_not_growing`)通过。

---

## 1. Phase 1: PR-1 (R1 架构修复,12 commits)

### Task 1.0: 分支与基线

**Files:**
- Branch: `fix/r1-arch`

- [ ] **Step 1: 创建分支**

```bash
cd /home/ailearn/projects/WFXM && git checkout main && git pull origin main
git checkout -b fix/r1-arch
```

- [ ] **Step 2: 跑基线测试**

```bash
cd /home/ailearn/projects/WFXM && pytest tests/ -q 2>&1 | tail -5
```

Expected: 全绿(若 R6-11 baseline 红,记录为已知问题,在 Task 1.12 后处理)

- [ ] **Step 3: 记录 commit 起点**

```bash
git rev-parse HEAD
```

记录 hash,作为 Task 1.12 后的 diff 起点。

### Task 1.1: R1-1 layering 修复

**Files:**
- Modify: `butler/transport/llm_client.py:360, 383, 476`
- Test: `tests/transport/test_llm_client_layering.py`(新建)

- [ ] **Step 1-7: 执行全局协议 §0.3 模板 A**

使用模板 A,subagent 输入:
- 审计 ID: R1-1
- 严重度: C
- 类型: layering_violation
- 文件: `butler/transport/llm_client.py:360, 383, 476`
- 测试参考: `tests/transport/test_llm_client.py` 若存在,否则 `tests/test_*.py` 中与 transport 相关的最近一个

- [ ] **Step 8: spec review**

主线程构造模板 B prompt,dispatch spec-reviewer subagent。

- [ ] **Step 9: code quality review**

主线程构造模板 C prompt,dispatch code-quality-reviewer subagent。

- [ ] **Step 10: 标记完成**

若 Step 8 + 9 均 APPROVED,主线程在 issue tracker 中标记 R1-1 done。

### Task 1.2: R1-2 layering 修复

**Files:**
- Modify: `butler/core/agent_loop.py:143`
- Test: `tests/core/test_agent_loop_layering.py`(新建或复用)

- [ ] **Step 1-10: 同 Task 1.1 协议,subagent 输入改为:**
- 审计 ID: R1-2
- 严重度: C
- 类型: layering_violation
- 文件: `butler/core/agent_loop.py:143`

### Task 1.3: R1-3 layering 修复

**Files:**
- Modify: `butler/core/context_compressor.py:426`, `butler/core/compaction_task.py:80,130,162`, `butler/core/compaction_steer_bridge.py:33`
- Test: `tests/core/test_context_compressor_layering.py`(新建)

- [ ] **Step 1-10: 同 Task 1.1 协议,subagent 输入改为:**
- 审计 ID: R1-3
- 严重度: C
- 类型: layering_violation
- 文件: 4 个文件,subagent 需统一处理三处反向依赖

### Task 1.4: R1-4 wechat_ilink.py god module 拆分(2027 行 → 多文件)

**Files:**
- Modify: `butler/gateway/platforms/wechat_ilink.py`(2027 行,90 函数)
- Create: `butler/gateway/platforms/wechat_ilink/` 子包 + 多文件拆分
- Test: `tests/gateway/platforms/test_wechat_ilink_split.py`(回归测试确保行为不变)

- [ ] **Step 1-7: 模板 A 协议,subagent 输入:**
- 审计 ID: R1-4
- 严重度: C
- 类型: god_module
- 文件: `butler/gateway/platforms/wechat_ilink.py`
- 特殊指引: 拆分后保持 public API 不变;原文件应变成薄 re-export shim 或删除;测试文件保留全部现有测试(若有)
- 拆分建议(主线程预分析): 按 90 函数的功能域拆,如 message_router / session_mgr / retry_policy / heartbeat / diagnostics 等

- [ ] **Step 8-9: spec + code-quality review**

⚠️ **拆分开关监测点**: 本任务完成后 `git diff main...HEAD --stat` 行数应 < 500。若超过,触发主线程"暂停"介入。

- [ ] **Step 10: 验证**

```bash
cd /home/ailearn/projects/WFXM && pytest tests/gateway/ -q 2>&1 | tail -10
```

Expected: 全绿(拆分后行为不变)

### Task 1.5-1.8: R1-5/6/7/8 god_module 修复(4 个 task)

**Files(每个 task):**
- R1-5: `butler/tools/delegate_impl.py:237-645`
- R1-6: `butler/gateway/message_handler.py`
- R1-7: `butler/main.py:999-1317`
- R1-8: `butler/core/agent_loop.py:250-587`

- [ ] **每 task 重复 Task 1.1 协议 Step 1-10**

注: R1-8 与 R1-2 文件重叠(R1-2 是 :143 layering,R1-8 是 :250-587 god),subagent 需精确行范围,避免冲突。

### Task 1.9-1.10: R1-9/10 layering 修复(2 个 task)

**Files:**
- R1-9: `butler/transport/stream_probe.py:52`
- R1-10: 7 个 tools 模块反向 import gateway(需 subagent 先 grep 定位)

- [ ] **每 task 重复 Task 1.1 协议**

注: R1-10 涉及多个文件,subagent 应先用 grep 列出全部反向 import,然后逐个修复。spec review 时检查是否所有反向 import 都已处理。

### Task 1.11-1.12: R1-11/12 module_mutable 修复(2 个 task)

**Files:**
- R1-11: `butler/core/exp_cache.py:23-24, 92-129`
- R1-12: `butler/gateway/platforms/wechat_ilink.py:158, 1042, 1058, 1956`

- [ ] **每 task 重复 Task 1.1 协议**

注: R1-12 与 R1-4 共享 wechat_ilink.py,若 R1-4 已拆分,subagent 应在新子包中处理模块级可变状态。

### Task 1.13: PR-1 验证与合并

- [ ] **Step 1: 主线程检查 commit 数**

```bash
cd /home/ailearn/projects/WFXM && git rev-list --count main..fix/r1-arch
```

Expected: 12(若 0,说明 subagent 跳过了 commit,需回查)

- [ ] **Step 2: 跑全测试**

```bash
cd /home/ailearn/projects/WFXM && pytest tests/ -x -q 2>&1 | tail -20
```

Expected: 全绿 + baseline gate 通过

- [ ] **Step 3: 审计 doc grep 验证**

```bash
grep -cE "^\*\*R1-[0-9]+ \[[CH]\]" docs/reviews/project-deep-audit-2026-06-r1to8.md
```

Expected: 0(原 12,修复后应 0)

- [ ] **Step 4: 推送并创建 PR**

```bash
cd /home/ailearn/projects/WFXM && git push -u origin fix/r1-arch
gh pr create --base main --head fix/r1-arch --title "fix(r1): R1 架构 C/H 全部修复 (12 commits)" --body "$(cat <<'EOF'
## 审计来源
docs/reviews/project-deep-audit-2026-06-r1to8.md §R1 全部 12 条 C/H

## Commits → Issues 映射
- $(git log --oneline main..fix/r1-arch | head -12)

## 验证
- pytest: 全绿
- audit grep R1 [CH]: 0
EOF
)"
```

- [ ] **Step 5: 等待 review 合并**

主线程监控 PR,合并后进入 Phase 2。

---

## 2. Phase 2: PR-2 (R2 错误处理,19 commits)

### Task 2.0: 分支与基线

- [ ] **Step 1: 创建分支**(从最新 main)

```bash
cd /home/ailearn/projects/WFXM && git checkout main && git pull origin main
git checkout -b fix/r2-errors
```

- [ ] **Step 2: 跑基线**

```bash
cd /home/ailearn/projects/WFXM && pytest tests/ -q 2>&1 | tail -5
```

### Task 2.1-2.19: R2-1 至 R2-19 修复(19 个 task)

**Per-issue 文件清单(主线程按顺序派发,每 issue 一 task):**

| ID | Sev | 文件 |
|----|-----|------|
| R2-1 | C | `butler/skills/consolidator.py:96-98` |
| R2-2 | C | `butler/memory/semantic_index.py:413-414, 458-459, 473-474` |
| R2-3 | C | `butler/memory/embedding.py:251-252, 345-350` |
| R2-4 | C | `butler/orchestrator.py:208-210` |
| R2-5 | C | `butler/registry/install_scan.py:120-125` |
| R2-6 | C | `butler/mcp/manager.py:171-179` |
| R2-7 | C | `butler/session/post_session.py:357-358, 412-413` |
| R2-8 | C | `butler/skills/manager.py:107-122` |
| R2-9 | H | `butler/core/agent_loop.py:214, 227, 238, 364, 423, 552, 701, 786` |
| R2-10 | H | `butler/transport/llm_client.py:149-150, 211-212` |
| R2-11 | H | `butler/permissions/rules.py:51, 87, 405, 488, 503` |
| R2-12 | H | `butler/registry/mcp_merge.py:147-149` |
| R2-13 | H | `butler/skills/manager.py:227-228` |
| R2-14 | H | `butler/skills/similarity.py:218-221` |
| R2-15 | H | `butler/registry/skill_sources/github.py:115-126, marketplace.py:107-108, 240-247` |
| R2-16 | H | `butler/gateway/message_handler.py:912-913` |
| R2-17 | H | `butler/registry/skill_sources/marketplace.py:107-108, 250-256` |
| R2-18 | H | `butler/skills/usage.py:24-30` |
| R2-19 | H | 12+ 状态文件统一反模式(跨文件,需 subagent 先 grep) |

- [ ] **每 task 重复 Task 1.1 协议 Step 1-10**

注 1: R2 全部为 log_continue / bad_fallback / silent_pass 类,修复模式统一为"显式 raise 或返回 error"。

注 2: R2-9 涉及 17 个 `except Exception`,subagent 需统一处理;每处都写一个测试覆盖,会非常长。**两种 commit 策略主线程二选一**:
- 策略 A(默认):每 3-4 处 except 合 1 commit,共 5 commits。R2-9 在 PR-2 commit 表中算 5 个 commit slot。
- 策略 B:每个 except 1 commit,共 17 commits。R2-9 算 17 个 commit slot,**会突破 PR-2 = 19 的总数,自动触发"拆分开关"**,主线程应改派 R2-9a/9b/9c 子任务到 PR-2a。

注 3: R2-19 是"统一反模式",subagent 应先 grep 找出全部 12+ 状态文件,然后统一修复。建议拆为多个 sub-task(每文件 1 commit),共 5-7 commits,**这些 commit 计入 PR-2 总数 19 之中**(主线程可调整 R2-1 至 R2-18 的 commit 数来补偿,如某些 H 类 issue 可 1 个 task 拆 2 commit)。**主线程监测 diff 行数,触发"拆分开关"。**

### Task 2.20: PR-2 验证与合并

- [ ] **Step 1-5: 同 Task 1.13,但 commit 期望 = 19**

⚠️ **拆分开关监测点**: R2-19 是大型反模式,可能触发拆分。若 git diff main...HEAD --stat 累计 > 3000 行,主线程暂停 PR-2,拆 `fix/r2a-errors-core`(R2-1 至 R2-18)与 `fix/r2b-error-format`(R2-19),分别合并。

---

## 3. Phase 3: PR-3 (R3 安全,3 commits)

### Task 3.0: 分支与基线

- [ ] **Step 1-2: 同 Task 1.0**

### Task 3.1: R3-1 SSRF TOCTOU 修复

**Files:**
- Modify: `butler/tools/web_fetch.py:94 vs :102`
- Test: `tests/tools/test_web_fetch_ssrf.py`(新建)

- [ ] **Step 1-10: Task 1.1 协议,subagent 输入:**
- 审计 ID: R3-1
- 严重度: H
- 类型: SSRF(TOCTOU)
- 文件: `butler/tools/web_fetch.py:94 vs :102`
- 特殊指引: 修复模式为 resolve hostname → 校验 IP → 发起请求的原子化(或加锁)

### Task 3.2: R3-2 untrusted-config → RCE chain 修复

**Files:**
- Modify: `butler/hooks/loader.py:86`, `butler/tools/path_safety.py:377-415`
- Test: `tests/test_hooks_rce_chain.py`(新建)

- [ ] **Step 1-10: Task 1.1 协议,subagent 输入:**
- 审计 ID: R3-2
- 严重度: H
- 类型: RCE chain
- 文件: 2 个文件
- 特殊指引: 修复涉及 hook 加载 + 路径校验的联合,subagent 需同时改两处

### Task 3.3: R3-3 hooks bash -c 全 env 修复

**Files:**
- Modify: `butler/hooks/runner.py:522-531`
- Test: `tests/hooks/test_runner_env_isolation.py`(新建)

- [ ] **Step 1-10: Task 1.1 协议,subagent 输入:**
- 审计 ID: R3-3
- 严重度: H
- 类型: env leak
- 文件: `butler/hooks/runner.py:522-531`
- 特殊指引: 修复模式为白名单环境变量或 `env -i` 重置

### Task 3.4: PR-3 验证与合并

- [ ] **Step 1-5: 同 Task 1.13,commit 期望 = 3**

---

## 4. Phase 4: PR-4 (R4 并发,7 commits)

### Task 4.0: 分支与基线

- [ ] **Step 1-2: 同 Task 1.0**

### Task 4.1: R4-1 cache LRU 原子化

**Files:**
- Modify: `butler/core/tool_result_cache.py:24, 80-100`
- Test: `tests/core/test_tool_result_cache_concurrency.py`(新建)

- [ ] **Step 1-10: Task 1.1 协议,subagent 输入:**
- 审计 ID: R4-1
- 严重度: C
- 类型: missing_lock
- 文件: `butler/core/tool_result_cache.py:24, 80-100`

### Task 4.2: R4-2 task_store TOCTOU

**Files:**
- Modify: `butler/runtime/task_store.py:133-140`
- Test: `tests/runtime/test_task_store_concurrency.py`(新建或复用)

- [ ] **Step 1-10: Task 1.1 协议,subagent 输入:**
- 审计 ID: R4-2
- 严重度: C
- 类型: file_race
- 文件: `butler/runtime/task_store.py:133-140`

### Task 4.3: R4-3 gate 一致性

**Files:**
- Modify: `butler/human_gate.py:184-201, 313-354`
- Test: `tests/test_human_gate_concurrency.py`(新建或复用)

- [ ] **Step 1-10: Task 1.1 协议,subagent 输入:**
- 审计 ID: R4-3
- 严重度: C
- 类型: missing_lock
- 文件: `butler/human_gate.py:184-201, 313-354`

### Task 4.4-4.7: R4-4/5/6/7(4 个 H,4 个 task)

**Per-issue 文件:**
- R4-4: `butler/transport/provider_health.py:47-67, 81-92`
- R4-5: `butler/core/read_state.py:61-66, 86-113, 149-156`
- R4-6: `butler/core/session_todos.py:164-182`
- R4-7: `butler/gateway/platforms/wechat_ilink.py:158, 1042, 1058, 1956`(与 R1-12 重叠,subagent 需精确行范围,避免与 R1-12 冲突)

- [ ] **每 task 重复 Task 1.1 协议**

注: R4-7 与 R1-12 共文件,主线程派工时强调:仅修并发相关行,严禁触碰 R1-12 已修的范围。

### Task 4.8: PR-4 验证与合并

- [ ] **Step 1-5: 同 Task 1.13,commit 期望 = 7**

---

## 5. Phase 5: PR-5 (R5 资源,10 commits)

### Task 5.0: 分支与基线

- [ ] **Step 1-2: 同 Task 1.0**

### Task 5.1-5.10: R5-1 至 R5-10(10 个 task)

**Per-issue 文件:**
- R5-1: `butler/memory/prefetch_cache.py:13, 56-62`(unbounded_cache)
- R5-2: `butler/orchestrator.py:169-176`(db_leak sqlite + ChromaDB)
- R5-3: `butler/memory/facade.py:201-205`(db_leak tenant switch)
- R5-4: `butler/mcp/manager.py:48-49, 177`(unbounded_cache dead code)
- R5-5: `butler/tools/terminal_impl.py:151-190`(subprocess_leak pipe FD)
- R5-6: `butler/tools/tool_audit.py:15, 104-108`(unbounded_cache)
- R5-7: `butler/hooks/telemetry.py:15, 33`(unbounded_cache)
- R5-8: `butler/core/read_state.py:18-19, 61-66`(与 R4-5 重叠,行范围不同)
- R5-9: `butler/gateway/inbound_idempotency.py:18-20, 165-171`(retention_gap dead API)
- R5-10: `butler/memory/observer_queue.py:20, 55-60`(unbounded_cache)

- [ ] **每 task 重复 Task 1.1 协议**

注: R5-8 与 R4-5 共 read_state.py,行范围不同(18-19 vs 61-156),subagent 需精确化。

### Task 5.11: PR-5 验证与合并

- [ ] **Step 1-5: 同 Task 1.13,commit 期望 = 10**

---

## 6. Phase 6: PR-6 (R6 测试,4 commits)

### Task 6.0: 分支与基线

- [ ] **Step 1: 创建分支**

```bash
cd /home/ailearn/projects/WFXM && git checkout main && git pull origin main
git checkout -b fix/r6-tests
```

- [ ] **Step 2: 确认 R6-11 baseline 失败**

```bash
cd /home/ailearn/projects/WFXM && pytest tests/test_sprint23_tst10_6_magicmock_spec_policy.py::TestBaselineGate::test_total_violations_not_growing -v 2>&1 | tail -20
```

Expected: FAIL with "2 violations in test_sprint24_p1_3_2_approval_diagnostics.py:156,158"

### Task 6.1: R6-11 baseline gate 修复(PR-6 首项,最高优先级)

**Files:**
- Modify: `tests/test_sprint24_p1_3_2_approval_diagnostics.py:156,158`
- Test: 复用 baseline gate(本身是测试)

- [ ] **Step 1-10: Task 1.1 协议,subagent 输入:**
- 审计 ID: R6-11
- 严重度: C
- 类型: failing_test
- 文件: `tests/test_sprint24_p1_3_2_approval_diagnostics.py:156,158`
- 特殊指引: 修复使 baseline gate 重回绿,但严禁修改 baseline 测试本身的断言(那会绕过门控)

- [ ] **Step 11: 验证 baseline 重回绿**

```bash
cd /home/ailearn/projects/WFXM && pytest tests/test_sprint23_tst10_6_magicmock_spec_policy.py::TestBaselineGate::test_total_violations_not_growing -v
```

Expected: PASS

### Task 6.2-6.4: R6-1/2/3 missing_tests(3 个 task)

**Per-issue 文件:**
- R6-1: `butler/memory/corrective_recall.py`(90 LOC)
- R6-2: `butler/tools/tool_audit.py`(285 LOC)
- R6-3: `butler/gateway/platforms/wechat_format.py`(346 LOC)

- [ ] **每 task 重复 Task 1.1 协议(注:这是"补测试"类 issue,流程略不同)**

**特殊子流程(替代模板 A):**
1. 主线程 subagent 读目标文件全部内容
2. Subagent 列出文件所有 public 函数 / 类
3. Subagent 为每个 public 函数写至少 1 个单元测试
4. Subagent 跑测试,确认全绿
5. Subagent commit:`test: R6-{N} 补 {file_name} 单元测试`

注: 这是 test-only commit,type = `test`。

### Task 6.5: PR-6 验证与合并

- [ ] **Step 1-5: 同 Task 1.13,commit 期望 = 4**

⚠️ **回滚开关监测点**: PR-6 必跑全 suite,因为 R6-11 是 baseline gate,任何回归都会暴露。

---

## 7. Phase 7: PR-7 (R7 文档,8 commits)

### Task 7.0: 分支与基线

- [ ] **Step 1-2: 同 Task 1.0**

### Task 7.1: R7-1 BUTLER_ONBOARDING_WELCOME 三处矛盾修复

**Files:**
- Modify: `.env.example`(`BUTLER_ONBOARDING_WELCOME`)
- Modify: `butler/config_service.py:91`
- Modify: `butler/gateway/handler_helpers.py:334`
- Type: doc/config(免 RED test)

- [ ] **Step 1-10: Task 1.1 协议,subagent 输入:**
- 审计 ID: R7-1
- 严重度: C
- 类型: config_drift
- 文件: 3 处
- 特殊指引: 统一选定一个默认值(如 `1`),三处全部改为一致;`.env.example` 加注释说明该 env 的语义

### Task 7.2-7.8: R7-2 至 R7-8(7 个 H,7 个 task)

**Per-issue 文件:**
- R7-2: 上下文压缩 5 个 env(多处)
- R7-3: `butler/transport/provider_health.py:38`(`CIRCUIT_OPEN_SECONDS`)
- R7-4: 2 个 `BUTLER_TURN_BUDGET_*`(`butler/core/turn_token_budget.py:72,88`)
- R7-5: 4 个 `BUTLER_TOOL_PRUNE_*`(`butler/core/tool_prune_policy.py:46-54`)
- R7-6: 2 个 `BUTLER_INSTRUCTION_WALKUP_MAX_*`(`butler/core/instruction_walkup.py:17-18,85,93`)
- R7-7: `butler/gateway/completion_notify.py:35,61`
- R7-8: `butler/gateway/completion_notify.py` 字段名/单位混乱(`MAX_EACH`)

- [ ] **每 task 重复 Task 1.1 协议**

注: 全部为 config drift(doc/config 类型),免 RED test。Subagent 流程:读 .env.example + 读代码 + 选定一致值 + 改 .env.example 与代码 + commit。

### Task 7.9: PR-7 验证与合并

- [ ] **Step 1-5: 同 Task 1.13,commit 期望 = 8**

注: 验证 grep 改为:
```bash
grep -cE "^\*\*R7-[0-9]+ \[[CH]\]" docs/reviews/project-deep-audit-2026-06-r1to8.md
```
Expected: 0

---

## 8. Phase 8: PR-8 (R8 配置,5 commits)

### Task 8.0: 分支与基线

- [ ] **Step 1-2: 同 Task 1.0**

### Task 8.1: R8-3 load_dotenv import-time 修复

**Files:**
- Modify: `butler/config.py:16, 22`
- Test: `tests/test_config_load_dotenv.py`(新建)

- [ ] **Step 1-10: Task 1.1 协议,subagent 输入:**
- 审计 ID: R8-3
- 严重度: C
- 类型: dotenv_side_effect
- 文件: `butler/config.py:16, 22`
- 特殊指引: 修复模式为惰性加载(load_dotenv 在第一次 config 访问时调用,而非 import 时);需测试验证 import 不再 side-effect

### Task 8.2: R8-5 int_unsafe 修复

**Files:**
- Modify: 12+ 处 `int(os.getenv(...))`(跨文件)
- Test: `tests/test_env_int_safety.py`(新建)

- [ ] **Step 1-10: Task 1.1 协议,subagent 输入:**
- 审计 ID: R8-5
- 严重度: H
- 类型: int_unsafe
- 文件: 主线程 grep 列出全部 12+ 处
- 特殊指引: 修复模式为 `int(os.getenv("X", default))` 加 try/except 兜底;考虑提取为 `safe_int_env(name, default)` 工具函数

### Task 8.3: R8-6 dead_config 修复

**Files:**
- Modify: `docs/...`(6+ 文档化但代码 0 reader 的配置)
- Type: doc(免 RED test)

- [ ] **Step 1-10: Task 1.1 协议,subagent 输入:**
- 审计 ID: R8-6
- 严重度: H
- 类型: dead_config
- 文件: docs 主线程 grep 列出
- 特殊指引: 修复模式为删除文档中已不存在的配置;或重新启用代码 reader(后者更复杂,默认前者)

### Task 8.4: R8-7 undocumented_env 修复

**Files:**
- Modify: `.env.example`(补 7+ 漏列的 env)
- Type: doc(免 RED test)

- [ ] **Step 1-10: Task 1.1 协议,subagent 输入:**
- 审计 ID: R8-7
- 严重度: H
- 类型: undocumented_env
- 文件: `.env.example`
- 特殊指引: subagent 先 grep 全部 `os.getenv` / `os.environ` 调用,列出未被 .env.example 记录的 env,逐一补全(带注释说明)

### Task 8.5: R8-8 feature_flag_dark 修复

**Files:**
- Modify: `butler/registry/skill_service.py:172` + 文档
- Type: doc(免 RED test)

- [ ] **Step 1-10: Task 1.1 协议,subagent 输入:**
- 审计 ID: R8-8
- 严重度: H
- 类型: feature_flag_dark
- 文件: `butler/registry/skill_service.py:172`
- 特殊指引: security-relevant `BUTLER_ENV=prod` 默认值需显式文档化;`prod` 与 `dev` 的行为差异需在 .env.example 注释清楚

### Task 8.6: PR-8 验证与合并

- [ ] **Step 1-5: 同 Task 1.13,commit 期望 = 5**

---

## 9. Phase 9: 最终验证(8 PR 全 merge 后)

- [ ] **Step 1: 主分支全 C/H grep**

```bash
grep -cE "^\*\*R[1-8]-[0-9]+ \[[CH]\]" docs/reviews/project-deep-audit-2026-06-r1to8.md
```

Expected: 0

- [ ] **Step 2: 主分支全测试**

```bash
cd /home/ailearn/projects/WFXM && pytest tests/ -q 2>&1 | tail -10
```

Expected: 全绿

- [ ] **Step 3: 主分支 8 commit 流验证**

```bash
cd /home/ailearn/projects/WFXM && git log --oneline main | grep "R[1-8]-[0-9]" | wc -l
```

Expected: 68

- [ ] **Step 4: 审计 doc 状态更新**

在 audit doc 顶部加一行:
```
**状态**: 修复完成 (2026-06-05) | 68 commits 分布在 8 PR | C/H = 0
```

- [ ] **Step 5: 关闭 8 个 PR**

主线程在 GitHub 上确认 8 个 PR 全部 merged。

- [ ] **Step 6: 庆祝**

主线程向用户报告完成。

---

## 附录 A:68 issue 完整 file:line 索引(派工速查表)

| ID | Sev | File:Line |
|----|-----|-----------|
| R1-1 | C | `butler/transport/llm_client.py:360, 383, 476` |
| R1-2 | C | `butler/core/agent_loop.py:143` |
| R1-3 | C | `butler/core/context_compressor.py:426` + `compaction_task.py:80,130,162` + `compaction_steer_bridge.py:33` |
| R1-4 | C | `butler/gateway/platforms/wechat_ilink.py`(2027 行) |
| R1-5 | H | `butler/tools/delegate_impl.py:237-645` |
| R1-6 | H | `butler/gateway/message_handler.py` |
| R1-7 | H | `butler/main.py:999-1317` |
| R1-8 | H | `butler/core/agent_loop.py:250-587` |
| R1-9 | H | `butler/transport/stream_probe.py:52` |
| R1-10 | H | 7 tools → gateway 反向 import |
| R1-11 | H | `butler/core/exp_cache.py:23-24, 92-129` |
| R1-12 | H | `butler/gateway/platforms/wechat_ilink.py:158, 1042, 1058, 1956` |
| R2-1 | C | `butler/skills/consolidator.py:96-98` |
| R2-2 | C | `butler/memory/semantic_index.py:413-414, 458-459, 473-474` |
| R2-3 | C | `butler/memory/embedding.py:251-252, 345-350` |
| R2-4 | C | `butler/orchestrator.py:208-210` |
| R2-5 | C | `butler/registry/install_scan.py:120-125` |
| R2-6 | C | `butler/mcp/manager.py:171-179` |
| R2-7 | C | `butler/session/post_session.py:357-358, 412-413` |
| R2-8 | C | `butler/skills/manager.py:107-122` |
| R2-9 | H | `butler/core/agent_loop.py:214, 227, 238, 364, 423, 552, 701, 786` |
| R2-10 | H | `butler/transport/llm_client.py:149-150, 211-212` |
| R2-11 | H | `butler/permissions/rules.py:51, 87, 405, 488, 503` |
| R2-12 | H | `butler/registry/mcp_merge.py:147-149` |
| R2-13 | H | `butler/skills/manager.py:227-228` |
| R2-14 | H | `butler/skills/similarity.py:218-221` |
| R2-15 | H | `butler/registry/skill_sources/github.py:115-126, marketplace.py:107-108, 240-247` |
| R2-16 | H | `butler/gateway/message_handler.py:912-913` |
| R2-17 | H | `butler/registry/skill_sources/marketplace.py:107-108, 250-256` |
| R2-18 | H | `butler/skills/usage.py:24-30` |
| R2-19 | H | 12+ 状态文件统一反模式 |
| R3-1 | H | `butler/tools/web_fetch.py:94 vs :102` |
| R3-2 | H | `butler/hooks/loader.py:86` + `butler/tools/path_safety.py:377-415` |
| R3-3 | H | `butler/hooks/runner.py:522-531` |
| R4-1 | C | `butler/core/tool_result_cache.py:24, 80-100` |
| R4-2 | C | `butler/runtime/task_store.py:133-140` |
| R4-3 | C | `butler/human_gate.py:184-201, 313-354` |
| R4-4 | H | `butler/transport/provider_health.py:47-67, 81-92` |
| R4-5 | H | `butler/core/read_state.py:61-66, 86-113, 149-156` |
| R4-6 | H | `butler/core/session_todos.py:164-182` |
| R4-7 | H | `butler/gateway/platforms/wechat_ilink.py:158, 1042, 1058, 1956` |
| R5-1 | C | `butler/memory/prefetch_cache.py:13, 56-62` |
| R5-2 | C | `butler/orchestrator.py:169-176` |
| R5-3 | C | `butler/memory/facade.py:201-205` |
| R5-4 | C | `butler/mcp/manager.py:48-49, 177` |
| R5-5 | H | `butler/tools/terminal_impl.py:151-190` |
| R5-6 | H | `butler/tools/tool_audit.py:15, 104-108` |
| R5-7 | H | `butler/hooks/telemetry.py:15, 33` |
| R5-8 | H | `butler/core/read_state.py:18-19, 61-66` |
| R5-9 | H | `butler/gateway/inbound_idempotency.py:18-20, 165-171` |
| R5-10 | H | `butler/memory/observer_queue.py:20, 55-60` |
| R6-1 | H | `butler/memory/corrective_recall.py`(90 LOC) |
| R6-2 | H | `butler/tools/tool_audit.py`(285 LOC) |
| R6-3 | H | `butler/gateway/platforms/wechat_format.py`(346 LOC) |
| R6-11 | C | `tests/test_sprint23_tst10_6_magicmock_spec_policy.py::TestBaselineGate` |
| R7-1 | C | `BUTLER_ONBOARDING_WELCOME` 3 处 |
| R7-2 | H | 上下文压缩 5 env(多处) |
| R7-3 | H | `butler/transport/provider_health.py:38` |
| R7-4 | H | 2 个 `BUTLER_TURN_BUDGET_*` |
| R7-5 | H | 4 个 `BUTLER_TOOL_PRUNE_*` |
| R7-6 | H | 2 个 `BUTLER_INSTRUCTION_WALKUP_MAX_*` |
| R7-7 | H | `butler/gateway/completion_notify.py:35,61` |
| R7-8 | H | `butler/gateway/completion_notify.py` 字段名/单位 |
| R8-3 | C | `butler/config.py:16, 22` |
| R8-5 | H | 12+ 处 `int(os.getenv(...))` |
| R8-6 | H | 6+ dead_config 文档 |
| R8-7 | H | 7+ undocumented_env |
| R8-8 | H | `butler/registry/skill_service.py:172` |

---

## 附录 B:主线程派工 checklist(每个 issue 复用)

派工前主线程必填:

- [ ] 审计 ID:`R{n}-{id}`
- [ ] 严重度:`C` / `H`
- [ ] 类型:`code` / `doc` / `config`(决定是否 RED)
- [ ] 文件:精确 `file:line` 范围
- [ ] 测试参考:同目录最近 1-2 个 test 文件
- [ ] 依赖:本 issue 是否依赖同 PR 前序 issue 的代码?(若是,确认前序已 merge)
- [ ] 重叠预警:本 issue 文件是否被同 PR 其他 issue 共享?(若是,标注行范围)
- [ ] 派工顺序:同 PR 内按 C → H 顺序派发

派工后主线程必收:

- [ ] Implementer 返回:commit hash + 改动文件列表 + 测试输出
- [ ] Spec-reviewer 返回:`[APPROVED]` 或 `[REJECTED]` + 原因
- [ ] Code-quality-reviewer 返回:`[APPROVED]` 或 `[REJECTED]` + 原因
- [ ] 若任一 REJECTED,重派 implementer(累计 ≤ 6 次)

派工后主线程必查(防 subagent 漂移):

- [ ] `git show HEAD --stat` 改动仅限审计 file:line
- [ ] 无顺手修 M/L
- [ ] 无新增 log_continue / silent_pass
- [ ] commit message 符合模板

---

**Plan 完成。** 接下来执行选项见 writing-plans skill 的"Execution Handoff"段。
