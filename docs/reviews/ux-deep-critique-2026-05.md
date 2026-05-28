# Butler UX 深度批判报告

> 日期：2026-05-28
> 范围：用户体验维度专项分析
> 基于：product-critique-2026-05.md 及核心代码审查

---

## 一、入口认知门槛

### 1.1 问题场景

**微信用户视角**：用户打开微信，看到 Bot 名称是 "Butler"，发消息后得到回复。但"多项目 AI 协助系统"这个定位，用户完全没有感知。

对比：用户知道"得到"是学习工具，"Notion"是笔记工具。但 Butler 的管家身份从未被传达。

**CLI 视角**：`butler chat` 直接进入黑屏等待，无引导性 welcome flow。

### 1.2 根因分析

1. **定位泄露在代码而非产品表达**：`ButlerOrchestrator`、`gateway_loop_role` 等命名在技术文档里清晰，但用户看到的是冷冰冰的回复消息。

2. **欢迎文本未差异化**：
   - `_WELCOME_TEXT`（handler_helpers.py 第 377-387 行）写了 10 行命令罗列，第一句是"🤖 Hi，我是你的 Butler 管家！"——管家是身份，但用户不知道管家能干什么。
   - 核心问题：Welcome Text 罗列功能清单，而不是描述使用场景。

3. **微信 Bot 资料页空白**：用户点击 Bot 头像，看到默认介绍页，无产品定位说明。

4. **命令即入口的结构性问题**：所有功能通过 `/命令` 触发，但新用户根本不知道存在命令系统。ChatGPT 的方式是"你什么都可以问"，Butler 的方式是"你得先知道有什么命令"。

### 1.3 改进方案

**方案 A（低成本）**：改进 `_WELCOME_TEXT`，区分首次用户和回归用户：

```
首次用户看到的：
🤖 我是你的项目管家
我来帮你管理多个项目的开发工作——写代码、跑测试、查文档、记决策

常用操作：
  · 直接描述任务：「帮我看看这个 bug」「写个登录功能」
  · /项目 — 查看你在管哪些项目
  · /帮助 — 查看所有命令

回归用户看到的：
📂 当前项目：XXX（有项目时）
💡 Tip：直接说「切到YYY项目」即可切换，无需记命令
```

**方案 B（中等成本）**：在 Bot 资料页增加产品定位说明。

**方案 C（高成本）**：设计情境式引导，前 3 次对话结束时给出上下文提示。

### 1.4 实现复杂度

| 方案 | 复杂度 | 优先级 |
|------|--------|--------|
| A - 改进 Welcome Text | 低 | P0 |
| B - 完善 Bot 资料页 | 中 | P1 |
| C - 情境式引导 | 高 | P2 |

---

## 二、命令体系碎片化

### 2.1 问题场景

当前命令按 `_HELP_GROUPS`（help_commands.py 第 6-75 行）分为 8 组：项目、模型、对话、记忆、权限、开发、日常、管理。

**实际问题**：

1. **帮助入口不一致**：`/帮助` 列出 8 个分组，但每组没有描述，用户不知道"开发"和"管理"区别在哪。

2. **命令发现路径缺失**：用户不知道可用 `/项目 新建`、`/项目 体检` 等子命令。

3. **碎片化示例**：
   ```
   /项目           — 列表（无操作引导）
   /项目 新建      — 新建（但用户不知道可以新建）
   /项目 体检      — 体检（但用户不知道可以体检）
   /项目概况       — 仪表盘（完全独立于 /项目）
   ```

4. **同义命令混乱**：`/配置` 和 `/config` 是同一命令，但用户无法从帮助文本推断。

### 2.2 根因分析

1. **命令注册散落各处**：`message_handler.py` 第 929-1453 行的 `_handle_command` 包含约 60+ 个命令分支，但没有统一的命令元数据注册表。

2. **帮助文本手工维护**：`/_HELP_GROUPS` 是手写字典，而非从命令元数据生成。

3. **命令层级未体现**：`/项目 新建 <slug> [模板]` 是一级命令 + 二级参数的语义，但帮助文本里没有体现层级关系。

### 2.3 改进方案

**方案 A（低成本）**：重新组织帮助分组，按用户意图而非技术领域分组：

```
当前分组（按技术领域）：
项目 | 模型 | 对话 | 记忆 | 权限 | 开发 | 日常 | 管理

建议分组（按用户意图）：
🏠 日常操作：/新对话 | /继续 | /待办 | /备忘 | /提醒
📂 项目管理：/项目 | /切换 | /项目概况 | /项目待办
🔍 代码工作：/git | /测试 | /构建 | /诊断
💡 深度功能：/workflow | /技能 | /详细 | /计划
⚙️  系统设置：/配置 | /模型 | /权限 | /帮助
```

**方案 B（中等成本）**：引入命令元数据注册机制，help 文本从注册表自动生成。

**方案 C（高成本）**：实现自然语言命令解析器，模糊匹配用户意图。

---

## 三、错误消息过于技术化

### 3.1 问题场景

当前 `format_gateway_user_error`（user_errors.py 第 6-9 行）只有一行：

```python
return "处理失败，请稍后重试。若持续出现请发 /health 或查看网关日志。"
```

**实际问题**：

1. **所有错误同一张脸**：无论失败原因是 LLM 超时、工具执行失败、权限不足还是流控限制，用户看到的都是同一句话。

2. **用户无操作路径**：错误消息说"请发 /health"，但用户不知道 `/health` 能帮助诊断什么问题。

### 3.2 根因分析

1. **错误分类缺失**：`AgentLoop.run()` 可能抛出多种异常，但异常统一走到 `format_gateway_user_error`。

2. **CLI 和微信错误体验不一致**：CLI 有 `classify_api_error`（session_ui.py 第 216 行）做错误分类，但微信端只有统一的"处理失败"。

### 3.3 改进方案

**方案 A（低成本）**：扩展 `user_errors.py`，按错误类型返回不同消息：

```python
def format_gateway_user_error(exc: BaseException | None = None) -> str:
    if exc is None:
        return "处理失败，请稍后重试。若问题持续请发 /诊断 查看。"

    exc_type = type(exc).__name__

    if "Timeout" in exc_type or "timeout" in str(exc).lower():
        return "⏰ 处理超时（LLM 响应慢），可能是网络问题或模型负载高。建议：稍等片刻后重试，或降低任务复杂度。"
    if "rate_limit" in str(exc).lower() or "RateLimit" in exc_type:
        return "⚡ 请求被限流（模型服务繁忙）。建议：等待 30 秒后再试，或切换到备用模型（/模型 查看）。"
    if "Auth" in exc_type or "auth" in str(exc).lower():
        return "认证失败，请检查 API 密钥配置（/配置 get openai）是否有效。"
    if "context" in str(exc).lower() and "length" in str(exc).lower():
        return "📏 对话上下文过长（超出模型限制）。建议：发送 /新对话 清空上下文，或要求「简要总结」降低长度。"

    return "处理失败，请稍后重试。\n若问题持续：\n  1. 发 /诊断 查看系统状态\n  2. 发 /新对话 重置会话\n  3. 联系管理员查看日志"
```

**方案 B（中等成本）**：建立四层错误分类（ToolError、LLMError、PermissionError、SessionError）。

---

## 四、反馈延迟无预期管理

### 4.1 问题场景

**微信用户视角**：发送消息后，Bot 没有立即响应，用户不知道 Bot 是否收到了消息。等待 30 秒后得到回复，也可能立即得到。

**实际现状分析**：

1. **WeChat 端**：`GatewayOutboundBridge`（outbound_bridge.py）实现了 typing 刷新（4s 间隔）、ack 提示（30s）、task_milestone 通知。但这些机制依赖 `BUTLER_GATEWAY_TYPING_ENABLED=1` 环境变量，默认是否开启未知。

2. **CLI 端**：`ChatSessionUI`（session_ui.py 第 142-155 行）实现了 Rich 状态显示、WaitSpinner、工具调用可视化。

3. **问题核心**：两边都有进度展示机制，但**展示时机不明确**、**内容不具体**（只说"正在思考"不说"正在搜索代码"）。

### 4.2 根因分析

1. **状态分类过于简单**："思考中"是一个状态，但 LLM 可能在做意图识别、工具选择、代码生成、摘要压缩等完全不同的事情。

2. **委派任务（delegate_task）完全黑箱**：用户发送"帮我修这个 bug"，然后得到一个最终报告，中间的 30 秒用户不知道在做什么。

3. **超时提示不友好**：没有分级提示（5s：已收到；15s：正在处理；30s：任务较复杂）。

### 4.3 改进方案

**方案 A（低成本）**：增强"正在输入"阶段的消息内容：

```
阶段 1（0-5s）："已收到，正在理解..."
阶段 2（5-15s）："正在规划操作步骤..."
阶段 3（15-30s）："正在执行 [tool_name]..."
阶段 4（>30s）："任务较复杂，预计还需要一些时间..."
```

**方案 B（中等成本）**：为委派任务增加中间进度推送：

```
🔄 已开始委派任务...
  角色：编码助手
  目标：[task preview]
  预计完成时间：约 1-2 分钟
  完成前会推送最终报告，请稍候。
```

---

## 五、First-Time Experience 引导流程

### 5.1 问题场景

**当前欢迎流程分析**（`_maybe_welcome_prefix`，handler_helpers.py 第 390-409 行）：

1. 条件触发：`BUTLER_ONBOARDING_WELCOME` 环境变量非空才显示欢迎文本
2. Session 级别去重：每个 session 只出现一次
3. 欢迎文本内容：`_WELCOME_TEXT` 列出 10 行命令清单

**实际问题**：

1. **欢迎文本功能清单化**：列出命令而非使用场景。
2. **无场景化引导**：新用户不知道第一步应该做什么。
3. **首次使用和回归用户没有区分**。
4. **无项目时体验断崖**：发`/项目`看到"暂无项目"，但没有引导如何创建第一个项目。

### 5.2 根因分析

1. **Onboarding 条件依赖环境变量**：默认关闭，大多数部署不会设置。
2. **引导流程无状态机**：没有"引导状态"概念（未完成 onboarding → 进行中 → 已完成）。

### 5.3 改进方案

**方案 A（低成本）**：改进 `_WELCOME_TEXT`，添加场景化描述；无项目时追加创建引导：

```python
# 在 project_commands.py 中
if not projects:
    return (
        "暂无项目。\n\n"
        "创建你的第一个项目：\n"
        "  /项目 新建 my-project\n\n"
        "示例：「/项目 新建 WFXM」创建一个名为 WFXM 的项目"
    )
```

**方案 B（中等成本）**：实现引导状态机，按阶段推送不同消息。

---

## 六、微信与 CLI 体验一致性

### 6.1 问题描述

| 维度 | CLI | 微信 |
|------|-----|------|
| 流式输出 | StreamRenderer 支持流式 | 无流式，只有最终结果 |
| 工具调用可视化 | 实时打印 tool start/complete | 无可见反馈 |
| 错误分类 | classify_api_error | 统一"处理失败" |
| 进度状态 | Rich console status + spinner | typing 刷新（4s 间隔） |

### 6.2 根因分析

1. **StreamRenderer 只在 CLI 存在**（cli/stream.py），微信端没有对应的流式渲染机制。
2. **两端的 error 翻译机制不一致**：CLI 有 `classify_api_error`，微信端只有 `format_gateway_user_error`。

---

## 七、优先级与落地建议

### 7.1 综合优先级

| # | 问题 | 优先级 | 工作量 |
|---|------|--------|--------|
| 1 | 错误消息用户化（无分类） | P0 | 低 |
| 2 | 命令帮助分组重设计 | P0 | 低 |
| 3 | Welcome 文本改进 | P0 | 低 |
| 4 | 无项目时正向引导 | P0 | 低 |
| 5 | 委派任务进度推送 | P1 | 中 |
| 6 | 多级状态提示（0-5-15-30s） | P1 | 低 |
| 7 | Onboarding 状态机 | P2 | 中 |
| 8 | 命令元数据注册表 | P2 | 中 |
| 9 | 微信端流式输出 | P2 | 高 |
| 10 | 交互式 onboarding wizard | P3 | 高 |

### 7.2 快速落地路线图

**Week 1（可立即上线）**：
1. 改进 `format_gateway_user_error`，增加 4-5 种错误类型的分支
2. 重新设计 `_WELCOME_TEXT`，添加场景化描述而非命令清单
3. 在 `/项目` 返回空时，追加创建项目的引导消息
4. 确保 typing/ack 功能默认开启

**Week 2-3（需要测试）**：
1. 实现 Onboarding 状态机（方案 B）
2. 为委派任务增加进度推送
3. 重新组织帮助文本的分组（按用户意图）

**Week 4+（需要架构改动）**：
1. 命令元数据注册表
2. 微信端流式输出
3. 交互式 onboarding wizard

### 7.3 关键文件索引

| 文件 | 作用 | 相关改进 |
|------|------|----------|
| `butler/gateway/handler_helpers.py` | Welcome 文本和 session 管理 | `_WELCOME_TEXT`、`_maybe_welcome_prefix` |
| `butler/gateway/help_commands.py` | 命令帮助文本 | `_HELP_GROUPS`、`format_help_text` |
| `butler/gateway/user_errors.py` | 用户可见错误消息 | `format_gateway_user_error` |
| `butler/gateway/outbound_bridge.py` | 微信端进度通知 | typing/ack/milestone 机制 |
| `butler/gateway/message_handler.py` | 命令分发核心 | `_handle_command` 60+ 命令分支 |
| `butler/cli/session_ui.py` | CLI 端 UI 和错误分类 | `on_llm_start`/`on_tool_start` 等 callbacks |
| `butler/cli/spinner.py` | CLI 旋转等待动画 | `WaitSpinner` |

---

## 附录：代码审查补充发现

### A.1 命令注册分散问题

当前 60+ 个命令的注册散落在 `message_handler.py` 的 `_handle_command`、`dev_commands.py` 的 `handle_dev_command`、`runtime_commands.py`、`memory_commands.py`、`sessions_commands.py`、`project_commands.py` 等。没有统一的元数据管理。

### A.2 错误处理不一致

`message_handler.py` 第 909 行捕获异常后存入 health 但未传递给 `format_gateway_user_error`（user_errors.py 第 8 行当前忽略 exc 参数）。这意味着所有错误消息无法根据异常类型差异化。

### A.3 Onboarding 依赖环境变量

`_maybe_welcome_prefix` 第 392 行依赖 `BUTLER_ONBOARDING_WELCOME` 环境变量，默认关闭。建议改为默认开启。

### A.4 Stream Preview 功能未启用

`outbound_bridge.py` 第 238 行 `BUTLER_GATEWAY_STREAM_PREVIEW` 默认为 False，需要确认这个功能的预期用途。