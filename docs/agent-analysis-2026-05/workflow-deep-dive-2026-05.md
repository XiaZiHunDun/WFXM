# Butler Workflow 深挖报告

## 一句话结论

Workflow 线最关键的判断是：OpenCode 值得学运行时状态机，ECC 值得学治理与目录，Superpowers 值得学流程 discipline；Butler 不需要换架构，只需要把这三类模式按 Butler 自己的边界吸收进现有 orchestrator、prompt、workflow 和文档体系。

## Butler 当前基线

### 已有能力

- `task_orchestrator.py` + `workflows/runner.py`  
  已具备 DAG、多 Agent、并行执行、`requires_approval`、rescue、until，以及 workflow 层 replan 钩子

- `permissions.py` + `permission_approvals.py`  
  已具备 allow/ask/deny、`workflow_steps` allowlist、一次/始终允许、pending 缓存

- `delegate_task` 链 + `delegate_subagent_permissions.py`  
  已具备子代理工具过滤、`child_session_key`，以及 delegate 链路上的 category、cache-safe context、depth 限制

- `runtime/task_store.py` + `async_delegate.py` + `delegate_registry.py`  
  已具备后台委派、任务记录、微信完成推送、父会话 interrupt 传播

- `human_gate.py` + `workflows/runner.py`  
  已具备 workflow 步骤确认、pause state、微信确认后再发 `/workflow` 续跑

- `plan_mode.py` + `agent_profiles.py`  
  已具备规划/执行分离、只读规划、verification guidance、review PASS/FAIL

## 三类参考来源

### OpenCode

- 角色：运行时权限与子 session 状态机
- 关键机制：ruleset merge、ask/once/always/reject、`task_id=child session`、background task、`task_status`
- 对 Butler 的意义：最像运行时可直接对照的上游

### ECC

- 角色：能力目录与治理方法论
- 关键机制：catalog、install-plan、agent-sort、stocktake、comply、least-agency、release gate
- 对 Butler 的意义：更适合映射到文档/模板/CLI，不适合进 core runtime

### Superpowers

- 角色：流程 discipline 与子代理协作方法
- 关键机制：brainstorming、writing-plans、implement/spec/quality review、verification-before-completion
- 对 Butler 的意义：更适合映射到 prompt/workflow 规范

## 主题映射

### 权限 / 审批

- 参考模式：OpenCode `ask/always/reject`
- Butler 当前子集：`permissions.yaml + /批准一次 + /始终允许`
- 差距：pending 批量 resolve/cancel 还不如 OpenCode 完整

### 子代理 / 委派

- 参考模式：OpenCode child session + background job
- Butler 当前子集：`delegate_task + child_session_key + async_delegate + task_store`
- 差距：递归 cancel 和状态查询仍较轻

### 规划 / 执行分离

- 参考模式：Superpowers brainstorming / plan gate
- Butler 当前子集：`plan_mode + /执行`
- 差距：plan 质量规则还可以更硬

### 审查 / 验证

- 参考模式：Superpowers `spec review -> quality review -> verification`
- Butler 当前子集：review role + `dev-qa-loop` + `VERIFICATION_GUIDANCE`
- 差距：spec 合规和代码质量还可以进一步拆层

### 能力目录

- 参考模式：ECC catalog / install-plan / agent-sort
- Butler 当前子集：`skills_list / skill_view / capabilities-index / registry verify`
- 差距：缺更明确的 DAILY/LIBRARY 裁剪流

### 治理 / 审计

- 参考模式：ECC least-agency / comply / stocktake
- Butler 当前子集：permissions + security_audit + prompt_eval + 文档 L0-L5
- 差距：行为合规抽检还可以更系统

## 优先级判断

### P1

1. pending approval 语义补强  
   把 always 后自动放行匹配 pending、reject/取消时统一清空同 session pending 做成明确语义。

2. 父约束向子 loop 传递  
   把 plan/read-only/deny 类约束更系统地派生到 delegate 子代理，而不是只靠工具过滤。

3. verification iron law  
   把“未跑验证不可声称完成”写进 dev/review prompt 与 workflow QA 门槛，并用 prompt_eval 回归。

4. review 双阶段化  
   把 spec 合规检查与 code quality 检查拆成两层，而不是一个 review 混查。

### P2

5. 任务状态机增强  
   补更多 task state、层级 cancel 图、必要时提供 agent 可见的 delegate status 子集。

6. 能力目录裁剪流程  
   把 ECC 的 DAILY/LIBRARY、dry-run plan、stocktake 思路映射到 capabilities 文档与 registry CLI。

## 不建议引入

- OpenCode Effect/SQLite/HTTP serve 全栈
- OpenCode workflow 自动续跑
- ECC 全量安装器、232 skills、hooks 作为主治理层
- Superpowers SessionStart 全量注入与 skill-first 硬规则
- Superpowers 三子代理链默认化

## 最终判断

Workflow 线应坚持 Butler 自建 orchestrator，不引入外部 workflow 平台；真正值得做的是：

1. 补状态机
2. 补验收门槛
3. 补能力目录治理

运行时吸收 OpenCode，治理吸收 ECC，流程 discipline 吸收 Superpowers，这三条线彼此独立，也最符合 v4 边界。
