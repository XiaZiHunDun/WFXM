# Butler 下一步分析报告

## 总判断

接下来最稳妥的路线不是启动新的大重构，而是先做三类小而硬的补强：

1. Memory 补隐私写入边界
2. Workflow 修权限语义一致性
3. Gateway 补 doctor 与真实配置的审计口径

总体排序原则是：**先风险，再一致性，再运维可见性**。

## 三条线结论压缩

### Memory

- 当前结论：现有骨架已经够用，最大短板是结构化 observation 与写入边界
- 最值得先动的问题：`<private>` 内容仍可能走进持久化链路
- 排序判断：先补写入边界，再谈 prefetch/index-first/summary 检索化

### Gateway

- 当前结论：主干成熟，最大短板是默认安全 posture 与 doctor 审计口径
- 最值得先动的问题：入口默认更宽松，且 doctor 与真实 allowlist 配置并不完全一致
- 排序判断：第一波先修审计口径；默认 posture 收紧放到第二波单独决策

### Workflow

- 当前结论：主干成熟，最大短板是 permission/pending 状态机与流程 discipline 还不够硬
- 最值得先动的问题：`workflow_steps` 工具名语义不一致
- 排序判断：先修 canonical 一致性，再推进 pending 级联与 verification hard gate

## 候选动作排序

### 第一梯队

1. Memory private 写入过滤  
   在 `sync_turn_memory` 与 `post_session` 两条 memory 落盘路径统一应用 private-tag 过滤  
   判断：这是三条线里最接近真实风险缺口的一项

2. Workflow 工具名 canonical 对齐  
   统一 `get_workflow_step_tool_allowlist()` 与 `evaluate_workflow_step_permission()` 的工具名语义  
   判断：这是小 diff、真 bug、验证面清楚

3. Gateway doctor 口径对齐  
   让 `security_audit.py` 识别 `WECHAT_ALLOWED_USERS`，并补 DM/group posture warn  
   判断：它不改运行时逻辑，但能显著减少运维误报与盲区；默认 posture 是否收紧留到第二波

### 第二梯队

4. Workflow pending 级联语义  
5. Gateway pairing 子集  
6. Memory index-first prefetch

这些都值得做，但都比第一波三项更偏产品化打磨，不适合作为第一刀。

## 第一波详细说明

### Memory

- 文件：`butler/session_lifecycle.py`
- 动作：对 `sync_turn_memory()` 入库文本做 private-tag 过滤，必要时跳过写入
- 目的：避免 `<private>` 内容进入 conversation experience

- 文件：`butler/post_session.py`
- 动作：对 post-session 提取出的 memory update 做同样过滤
- 目的：避免 profile/project memory 收到 private 内容

- 文件：`tests/test_session_lifecycle.py` 等
- 动作：补 private 内容不落盘的回归测试
- 目的：锁定行为，避免以后回退

### Workflow

- 文件：`butler/permissions.py`
- 动作：统一 workflow step allowlist 的 canonical tool name 逻辑
- 目的：修复 spawn 与 runtime permission 语义不一致

- 文件：`tests/test_p2_workflow_permissions.py`
- 动作：补 alias/canonical 行为一致性的测试
- 目的：确保这是一次纯一致性修复

### Gateway

- 文件：`butler/ops/security_audit.py`
- 动作：识别 `WECHAT_ALLOWED_USERS`，并补 DM/group posture 审计项
- 目的：让 doctor 与真实配置读取逻辑对齐

- 文件：`tests/test_security_audit.py`
- 动作：补 allowlist / DM policy 相关审计测试
- 目的：锁定 doctor 输出与配置口径

## 第二波再推进

### Memory

- session summary 读回 prefetch
- index-first prefetch

### Workflow

- pending approval 级联语义
- verification iron law

### Gateway

- 默认安全 posture 决策
- busy / pending UX
- pairing 子集

## 当前明确不做

- OpenCode Effect/SQLite/HTTP serve 全栈
- OpenCode / Dify 式自动续跑 workflow
- OpenClaw 全通道 plugin-sdk / WS 控制面
- Hermes Runner / AIAgent 整体回迁
- ECC 全量安装器 / hooks 主治理层 / 232 skills 默认化
- Superpowers SessionStart 全量注入与三子代理默认链

## 最终结论

如果目标是“先出一版稳妥的下一步方案，而不是立刻进入大规模施工”，那么最合理的答案就是：

- 先补真实边界
- 再修真实 bug
- 再补运维可见性

三条线分别对应 Memory、Workflow、Gateway。
