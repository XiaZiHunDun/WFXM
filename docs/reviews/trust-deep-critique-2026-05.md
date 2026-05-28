# Butler v4 信任与可靠性维度深度剖析

> 日期：2026-05-28
> 范围：信任可靠性五大维度根因分析
> 依据：代码审查 + 产品体验

---

## 一、写操作确认

### 根因分析

1. `two_phase_confirm.py` 第 17-20 行只覆盖 `terminal` 和 `delete_file`，`write_file`/`patch_file`/`edit_file` 完全无确认
2. `tool_guardrails.py` 的 `MUTATING_TOOLS` 虽然包含写操作，但 guardrails 机制是**循环检测**（重复调用/死循环），非**单次操作风险确认**
3. `permissions/rules.py` 第 529-533 行的 ask 机制只有配置了 `permissions.yaml` 才生效，且消息格式是"需 Owner"而非"请用户确认"

**用户感知现状：**

| 操作 | 有无确认 |
|------|---------|
| `delete_file` | 有（via two_phase） |
| `terminal` | 有（via two_phase） |
| `write_file` | **无** |
| `patch_file` | **无** |
| `edit_file` | **无** |

### 推荐方案

扩大 `_HIGH_RISK_TOOLS` 包含所有 `MUTATING_TOOLS`，并改造微信端增加 Y/N 交互确认。

---

## 二、能力边界透明

### 根因分析

1. `help_commands.py` 无 `/能力` 命令，无能力地图展示
2. v4 否决能力清单用户看不到（仅在 product-critique 文档中）
3. 工具被 block 时的错误消息是技术性的，未翻译为用户可操作指引

### 推荐方案

新增 `/能力` 命令按读/写/系统分类展示能力，拦截消息翻译为"发 /帮助 权限 查看如何授权"。

---

## 三、日志可观测

### 根因分析

1. `/诊断` 输出的 `format_memory_diagnostic_lines` 是记忆层技术指标，普通用户看不懂
2. LLM 调用失败时错误不进入 `/诊断` 输出，用户不知是网络/API key/模型/上下文问题
3. `logs/` 目录无 WebUI，`failure_tracker.py` 提到"请检查日志"但用户不知日志在哪

### 推荐方案

`/诊断` 增加错误分类（网络/权限/超限）和基本排查步骤，新增 `/日志` 命令展示错误摘要。

---

## 四、错误恢复

### 根因分析

1. `llm_retry.py` 第 97-294 行的 retry 逻辑（StaleApiCallError 重试 → schema recovery → 压缩上下文 → provider failover → 不可重试直接 break）对用户完全黑箱
2. `safety_finish.py` 第 23-39 行拒绝消息只说"请换一种表述"，未说明为什么被拒绝
3. `llm_retry.py` 第 286 行 `All LLM attempts failed` 后 Bot 对用户说什么取决于 `message_handler`，无统一结构化错误消息

### 推荐方案

最终失败后发送结构化消息，包含原因分类和操作建议。

---

## 五、数据安全

### 根因分析

1. `observation_store.py` 第 106-114 行 TTL 和最大行数默认值均为 0（永不过期、无限制），且未在 `.env.example` 体现
2. `session_transcript.py` 第 63-81 行 Tombstone 截断仅在 JSONL 文件中，不通知用户
3. 用户未被告知数据保留策略（位置/格式/时长/删除方法）
4. `observations.db` 的 `preview` 字段可能包含写操作的文件内容片段

### 推荐方案

数据保留声明（通过 Bot 首次响应或 `/帮助 数据`）+ 披露 observations.db 记录数。

---

## 综合优先级

| 维度 | 问题 | 优先级 |
|------|------|--------|
| 写操作确认 | `write_file`/`patch_file`/`edit_file` 无确认 | **P0** |
| 数据安全 | observations.db 默认永不过期，用户无感知 | **P0** |
| 能力边界 | `/能力` 命令缺失，拦截消息不用户化 | **P1** |
| 错误恢复 | retry 机制黑箱，最终失败消息无操作指引 | **P1** |
| 日志可观测 | `/诊断` 输出技术化，无错误分类 | **P2** |

---

## 关键代码索引

| 文件 | 行号 | 关联问题 |
|------|---------|---------|
| `butler/core/two_phase_confirm.py` | 17-20 | `_HIGH_RISK_TOOLS` 范围过窄 |
| `butler/tool_guardrails.py` | 38-48 | `MUTATING_TOOLS` 定义 |
| `butler/core/llm_retry.py` | 97-294 | retry 循环逻辑 |
| `butler/core/llm_retry.py` | 286 | `All LLM attempts failed` |
| `butler/core/safety_finish.py` | 23-39 | 安全拒绝消息 |
| `butler/permissions/rules.py` | 529-533 | ask 消息格式化 |
| `butler/memory/observation_store.py` | 106-147 | TTL/max_rows 裁剪逻辑 |
| `butler/core/session_transcript.py` | 63-81 | Tombstone 截断 |
| `butler/memory/diagnostics.py` | 198-271 | 诊断输出技术化 |
| `butler/gateway/help_commands.py` | 6-75 | 无 `/能力` 命令 |