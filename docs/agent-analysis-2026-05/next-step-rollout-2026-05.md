# 下一步实施顺序

## 推荐结论

- 先做 **memory 隐私写入链路补齐**，因为这是三条线里最像真实风险缺口的一项：当前 `<private>...</private>` 已有过滤工具，但写入 `butler/session_lifecycle.py` 与 `butler/post_session.py` 的持久化路径还没统一接上。
- 第二步做 **workflow 工具名 canonical 对齐**，这是一个小但真实的权限一致性 bug：`butler/permissions.py` 里 `get_workflow_step_tool_allowlist()` 和 `evaluate_workflow_step_permission()` 目前存在两套工具名语义。
- 第三步做 **gateway doctor 与真实配置对齐**，让 `butler/ops/security_audit.py` 正确认 `WECHAT_ALLOWED_USERS`，并补上微信 DM/group 暴露面的 warn，避免运维误报。

## 第一波实施

### 1. Memory: 补齐 private-tag 写入过滤

- 在 `butler/session_lifecycle.py` 的 `sync_turn_memory()` 入库前统一调用 private-tag 过滤。
- 在 `butler/post_session.py` 的记忆提取落盘前做同样处理，`fully_private` 时直接跳过写入。
- 若需要复用，轻量整理 `butler/memory/private_tags.py` 的 helper，避免两处复制逻辑。
- 验证重点：`<private>` 内容不进入 experience/profile/project memory。

### 2. Workflow: 修正 workflow_steps 工具名一致性

- 在 `butler/permissions.py` 中，让 `evaluate_workflow_step_permission()` 与 `get_workflow_step_tool_allowlist()` 一样走 canonical tool name。
- 保证 workflow spawn 时能看到的工具，运行时 permission check 也按同一名字判定。
- 这是最适合做成单独小 PR 的一致性修复，改动小、回归面清楚。

### 3. Gateway: 对齐 doctor 与真实入口配置

- 在 `butler/ops/security_audit.py` 中把 `WECHAT_ALLOWED_USERS` 纳入 owner/allowlist 判定。
- 追加微信入口 posture 的静态检查：`WECHAT_DM_POLICY=open`、allowlist 模式但名单为空、群策略暴露面等。
- 可选同步 `scripts/lib/butler-gateway-preflight.sh` 的口径，保持 preflight 与 doctor 一致。

## 第二波再考虑

- workflow 侧继续做 `pending approval` 的级联语义补强，围绕 `butler/permission_approvals.py`、`butler/human_gate.py`、`butler/workflows/runner.py`。
- gateway 侧再评估 pairing 子集与 busy/pending UX，不在第一波直接动入口协议。
- memory 侧再考虑 session summary 读回 prefetch 与 index-first prefetch，这些收益明确，但优先级低于隐私写入缺口。

## 需要补的验证

- Memory：`tests/test_session_lifecycle.py` 和相关 post-session 测试，覆盖 private-tag 不落盘。
- Workflow：`tests/test_p2_workflow_permissions.py`，覆盖 alias/canonical 工具名在 workflow step 白名单下的一致行为。
- Gateway：`tests/test_security_audit.py`，覆盖 `WECHAT_ALLOWED_USERS` 与 DM/group policy 的 doctor 输出。

## 为什么按这个顺序

- **先风险，再一致性，再运维可见性**：memory 先堵真正可能写入敏感内容的口子；workflow 再修真实权限判定 bug；gateway doctor 最后补齐告警口径。
- 三项都符合当前边界，不引入新 runtime、不改产品交互模型，也不会碰已明确否决的自动续跑、多客户端控制面或外部框架迁移。
