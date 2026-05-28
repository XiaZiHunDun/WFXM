# 产品挑刺复审报告

> 日期：2026-05-28
> 目的：验证 ux/功能/信任/竞品 四维挑刺报告中的问题是否真实存在
> 方法：代码审查 + 文档对照

---

## 复审结论总览

| 维度 | 问题数 | 确认存在 | 部分存在 | 已修正/不实 |
|------|--------|----------|----------|-------------|
| UX | 6 | 6 | 0 | 0 |
| 功能 | 6 | 6 | 0 | 0 |
| 信任 | 6 | 4 | 2 | 0 |
| 竞品 | 6 | 4 | 2 | 0 |
| **合计** | **24** | **20** | **4** | **0** |

---

## 一、UX 问题复审

### 问题1：命令注册散落（约 60+ 分支无统一注册表）
**状态：存在**（HIGH）

**证据：** `message_handler.py:929-1454` 约 50+ 个 if/elif 分支散落，无统一注册表。`handler_helpers.py:249-353` 的 `_is_sessionless_command` 又有另一套枚举，两不同步（如 `/git` 只在 helper 中出现）。

### 问题2：帮助文本手工维护
**状态：存在**（MEDIUM）

**证据：** `help_commands.py:6-75` 的 `_HELP_GROUPS` 是手写死字典，命令描述、格式、别名全部人工维护，无从元数据自动生成机制。

### 问题3：错误消息无分类
**状态：存在**（HIGH）

**证据：** `user_errors.py:6-9` 接收 `exc` 参数后立即 `del exc`，返回固定字符串。对比 CLI 侧 `session_ui.py:213-220` 有 `classify_api_error()` 分级提示，微信端完全无差异化。

### 问题4：Onboarding 依赖环境变量（默认关闭）
**状态：存在**（MEDIUM）

**证据：** `handler_helpers.py:390-393` 只有 `BUTLER_ONBOARDING_WELCOME` 非空时才输出欢迎文本，默认关闭。且 `_WELCOME_TEXT` 是手写死字符串，与实际命令注册无关联。

### 问题5：无项目时无引导
**状态：存在**（MEDIUM）

**证据：** `message_handler.py:956-958` 返回 `"暂无项目。"` 后无任何创建引导，而 `/项目 新建 <slug>` 语法存在但用户无从得知。

### 问题6：CLI/微信错误体验不一致
**状态：存在**（HIGH）

**证据：** CLI 侧有完整错误分类（`classify_api_error`），微信侧统一"处理失败"且丢失 retry 次数、错误分类、provider/model 提示。

---

## 二、功能问题复审

### 问题1：项目匹配静默失败
**状态：存在**

**证据：** `project/manager.py:79-95` 当多匹配时（`len(ci) > 1` 或多子串匹配）直接 `return None`，用户只收到"未找到项目"，无候选项列表。

### 问题2：帮助文本声明但无路由
**状态：存在**

**证据：** `help_commands.py:8` 声明 `/项目 列出所有项目`，但 `project_commands.py:28-38` 的 `handle_project_onboarding_command()` 只处理 `新建` 和 `体检` 子命令，空参数时 `return None`。

### 问题3：委派摘要无版本标识
**状态：存在**

**证据：** `context_compressor.py:164-209` 的 `_format_for_summary()` 输出格式为 `[{ROLE}]: {content}`，无版本号、无时间戳、无消息位置信息。

### 问题4：新对话返回信息粒度不足
**状态：存在**

**证据：** `lifecycle.py:763-779` 的 `format_new_session_user_message()` 仅返回 2 行文本，用户不知道 observations.db 条数、MEMORY 提炼状态、会话 transcript 清除情况。

### 问题5：Workflow 无 DAG 预览
**状态：存在**

**证据：** `workflows/commands.py:29-65` 无 `preview` 子命令分支，`/workflow preview` 被当作 workflow 名查找而返回错误。

### 问题6：隐式上下文无诊断命令
**状态：存在**

**证据：** `tool_implicit_context.py` 实现了注入机制，但 `gateway/` 下无 `/隐式上下文` 命令路由，`help_commands.py` 也未声明。

---

## 三、信任问题复审

### 问题1：write_file 无确认
**状态：存在**

**证据：** `two_phase_confirm.py:17-20` 的 `_HIGH_RISK_TOOLS` 仅含 `terminal` 和 `delete_file`，`write_file`/`patch_file`/`edit_file` 完全无二次确认。

### 问题2：数据安全 TTL 无限
**状态：存在**

**证据：** `observation_store.py:106-147` 的 `_ttl_days()` 和 `_max_rows()` 默认返回 0（环境变量未设置时），导致 `_prune_locked` 跳过清理，数据永不过期/无限制增长。

### 问题3：能力边界不透明
**状态：存在**

**证据：** `help_commands.py:6-75` 无 `/能力` 命令，用户无从得知 Butler 能做什么/不能做什么，v4 否决清单用户看不到。

### 问题4：错误恢复黑箱
**状态：** 部分存在

**证据：** `llm_retry.py:286` 的 `All LLM attempts failed` 仅 `logger.error`，不上报用户层。但 `diagnostics` 字典在调用链中传递并被记录，并非完全黑箱。

### 问题5：日志可观测差
**状态：** 部分存在

**证据：** `diagnostics.py:198-271` 的 `format_memory_diagnostic_lines` 已有人类可读中文标签，但仍有技术化字段（如 `vector_rows`、`triplet_rows`），非完全面向普通用户。

### 问题6：safety_finish 拒绝消息简化
**状态：存在**

**证据：** `safety_finish.py:23-39` 仅说"请换一种表述或缩小范围后重试"，未说明触发原因、安全政策类型、复核途径。

---

## 四、竞品问题复审

### 问题1：无"继续上次对话"
**状态：** 部分存在

**证据：** 存在会话摘要注入机制（`lifecycle.py:804-844` 写入 `session_summary.json`，`handler_helpers.py:496-542` 注入新 session），但非 ChatGPT 式的完整 message history 恢复。

### 问题2：无对话标题生成
**状态：存在**

**证据：** `session_summary.json` payload 无 title 字段，全局搜索无匹配结果。

### 问题3：预览能力缺失
**状态：存在（结构性限制）

**证据：** 微信消息通道不支持内联 HTML/图片预览，非 bug。Cursor 的预览能力依赖内置浏览器，Butler 微信端无法对齐。

### 问题4：任务卡片缺失
**状态：存在

**证据：** `project_todos.py` 输出纯文字模拟卡片，无钉钉/飞书的结构化卡片消息。竞品对标属实。

### 问题5：知识库管理 UI 缺失
**状态：存在

**证据：** 全局搜索无 Web UI 相关代码，只有 CLI（`butler memory search`）和 `/诊断` 命令。

### 问题6：observations.db 不可见
**状态：** 部分存在

**证据：** SQLite 文件本身不可见，但 `/诊断` 提供了聚合状态可读（向量索引条数、Owner 画像、Experience 等），并非完全不可观测。

---

## 修正说明

基于复审结果，对原挑刺报告的修正：

1. **竞品问题1**（"继续上次对话"）：原报告写为"无"，修正为"部分存在"——存在会话摘要注入机制，但与 ChatGPT 的完整上下文恢复是不同层级
2. **竞品问题6**（observations.db 不可见）：原报告写为"不可见"，修正为"部分存在"——文件不可见但 `/诊断` 提供了可读状态
3. **信任问题4**（错误恢复黑箱）：原报告写为"完全黑箱"，修正为"部分存在"——有 diagnostics 传递但不面向用户
4. **信任问题5**（日志可观测差）：原报告写为"差"，修正为"部分存在"——已有中文标签但仍有技术化字段

---

## 未涉及问题

以下原挑刺报告中的问题**未在本次复审中验证**（需进一步代码审查）：

- 竞品维度：S2/S3/S10 否决重估（需对照 roadmap 文档详细评审）
- UX 维度：微信端流式输出缺失（`outbound_bridge.py:238` 的 `BUTLER_GATEWAY_STREAM_PREVIEW`）
- 竞品维度：委派异步 + 完成通知（OpenCode P1 相关）

---

## 附录：关键代码路径索引

| 问题 | 文件:行号 |
|------|----------|
| 命令注册散落 | `message_handler.py:929-1454` |
| 帮助文本手工 | `help_commands.py:6-75` |
| 错误消息无分类 | `user_errors.py:6-9` |
| Onboarding 关闭 | `handler_helpers.py:390-393` |
| 无项目引导 | `message_handler.py:956-958` |
| 项目匹配失败 | `project/manager.py:79-95` |
| /项目无列表 | `project_commands.py:28-38` |
| 摘要无版本 | `context_compressor.py:164-209` |
| 新对话简化 | `lifecycle.py:763-779` |
| Workflow 无预览 | `workflows/commands.py:29-65` |
| write_file 无确认 | `two_phase_confirm.py:17-20` |
| TTL 无限 | `observation_store.py:106-147` |
| safety_finish | `safety_finish.py:23-39` |
| 会话摘要注入 | `lifecycle.py:804-844`, `handler_helpers.py:496-542` |