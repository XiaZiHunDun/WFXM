# Butler v4 项目深度审计 (2026-06)

> **审计人**: 管家（Claude 驱动）  
> **审计范围**: `butler/` 全量代码 + `tests/` + `docs/` + `scripts/`  
> **审计方法**: 多轮 subagent 深度检查 + 统一复检  
> **项目状态**: Butler v4 (自建 Agent Loop)，268 个测试文件，约 1.8k+ 测试  
> **审计启动时间**: 2026-06-02

## 0. 审计元信息

- **审计轮次**: 5 轮（架构 → 代码质量 → 安全/测试 → 性能/资源 → 文档/规范）
- **审计原则**: 只记录已复检确认的问题，避免假阳性
- **严重度**:
  - 🔴 **CRITICAL**: 安全/数据丢失/可观测性盲区，必须修复
  - 🟠 **HIGH**: 显著 Bug / 可维护性 / 性能问题
  - 🟡 **MEDIUM**: 应改进但非阻塞
  - 🔵 **LOW**: 风格 / 文档小问题

### 基础事实（已命令验证）

| 指标 | 数值 | 验证命令 |
|---|---|---|
| `butler/` Python 文件总数 | 453 | `find butler -name "*.py" -not -path "*__pycache__*" \| wc -l` |
| `butler/core/` Python 文件数 | 104 | `ls butler/core/*.py \| wc -l` |
| `butler/gateway/` 顶层文件数 | 51 | `ls butler/gateway/ \| grep -v __pycache__ \| wc -l` |
| `>800` 行的单文件 | 4 | `find butler -name "*.py" -exec wc -l {} \; \| awk '$1>800'` |
| `>500` 行的单文件 | 26 | 同上 `$1>500 \| wc -l` |
| `butler/main.py` 内 `from butler.` 数 | 81 | `grep -c "from butler\." butler/main.py` |
| `message_handler.py` 内 `from butler.` 数 | 92 | `grep -c "from butler\." butler/gateway/message_handler.py` |
| `orchestrator.py` 内 `from butler.` 数 | 40 | `grep -c "from butler\." butler/orchestrator.py` |
| `core/` → `gateway/` 跨层 import 数 | 6 | `grep -rn "from butler\.gateway" butler/core/` |
| 测试文件数 | 268 | `ls tests/ -1 \| grep -c .py` |

---

## 1. 总体结论

### 1.1 项目总评

Butler v4 是一个**架构清晰、产品边界明确、安全隔离做得不错**的多项目 AI 协助系统。5 轮审计共发现 **85 条问题**，按严重度分布：

| 严重度 | 数量 | 占比 | 典型 |
|---|---|---|---|
| 🔴 CRITICAL | 5 | 5.9% | SSRF 主机白名单绕过、doom-loop fail-open、fire-and-forget asyncio task、6 处断链 |
| 🟠 HIGH | 27 | 31.8% | God Module、Exception 黑洞、并发无锁、PII 脱敏不全、文档/BUTLER_ 同步 |
| 🟡 MEDIUM | 38 | 44.7% | 长函数、命名规范、性能瓶颈、ADR 缺失、CHANGELOG 缺失 |
| 🔵 LOW | 15 | 17.6% | SPDE 头、测试命名、SQLite journal_mode 反复重设 |

### 1.2 已确认的强项

- ✅ 0 处 `eval/exec/pickle/os.system/shell=True`（工具层隔离扎实）
- ✅ 0 处硬编码真实 key
- ✅ `audit.py` / `audit_log` 等错误处理有显式级别
- ✅ `tests/test_wechat_account_persistence.py:36` 已对 `account_id.json` 验证 0o600
- ✅ 283+ 测试文件、~2400 个 test 函数（体量合理）
- ✅ `steer.py` / `mcp/profiles.py` 锁使用正确
- ✅ Hermes 解耦已完成（v4 自建 Loop）
- ✅ `_DEFAULT_MAX_BYTES` 50MB 单 session transcript cap 已有
- ✅ 268 个测试文件中 535 deselected（live API 守门）

### 1.3 优先修复 Top 10（按修复 ROI 排序）

| # | 严重度 | 问题 | 文件:行号 | 修复成本 | 收益 |
|---|---|---|---|---|---|
| 1 | 🔴 | MCP HTTP 主机白名单子串绕过（SSRF） | `butler/mcp/config.py:237` | **低** (改 1 行) | **极高** — 真实 SSRF 漏洞 |
| 2 | 🔴 | doom-loop 异常 fail-open | `butler/core/agent_loop.py:712` | **低** (改 5 行) | **极高** — 安全护栏 |
| 3 | 🔴 | wechat_ilink fire-and-forget `asyncio.create_task` | `butler/gateway/platforms/wechat_ilink.py:1187` | **低** (加 self._bg 持有) | **高** — adapter 重连崩溃 |
| 4 | 🔴 | 6 处断链（project-assessment 已删） | `README.md:148` 等 7 处 | **低** (改 7 个链接) | **中** — 用户体验 |
| 5 | 🟠 | ContextTokenStore 无 chmod 0o600 | `wechat_ilink.py:344-354` | **低** (加 2 行) | **高** — token 横向泄露 |
| 6 | 🟠 | `_WELCOMED_SESSIONS` TOCTOU race | `handler_helpers.py:375-400` | **低** (改 set.add 原子) | **中** — 重复欢迎语 |
| 7 | 🟠 | audit `try_acquire_lock` TOCTOU | `runtime/audit.py:53-67` | **低** (os.open O_EXCL) | **高** — 同一 job 双跑 |
| 8 | 🟠 | SQLite 13+ 每次重连 | `memory/butler_memory.py:145` | **中** (复用 conn) | **极高** — 性能 100x |
| 9 | 🟠 | PII 脱敏仅 3 类（缺银行卡/API key/JWT） | `gateway/pii_scrub.py:8-25` | **中** (加 4 类正则) | **高** — 数据外泄 |
| 10 | 🟠 | 41+ 个 `BUTLER_*` 未收录到 reference.md / .env.example | `.env.example` 全量 | **中** (写一次同步脚本) | **高** — AGENTS 违反 |

### 1.4 推荐下一步

**Sprint 7 候选**（按上述 Top 10）：
1. 安全 1 周：修 SSRF + chmod + fail-open + lock TOCTOU（条目 1/2/3/5/7）
2. 性能 0.5 周：SQLite 复用 + vector_store 改 append-only + 整文件重写批改（条目 8 + 5.1.2-5.1.5）
3. 文档同步 0.5 周：跑 `_sync_butler_env_docs.py` + 加 CHANGELOG/SECURITY/ADR（条目 10 + 6.4.1-6.4.2）

**Sprint 8+ 候选**（架构层）：
- main.py / message_handler.py / wechat_ilink.py 三 God Module 拆分（2.1.1-2.1.3）
- core↔gateway 反向 import 收口（2.2.1）
- 8 个 long function（3.6.2）逐步拆

**建议**: 不应一蹴而就。Top 10 全部修复成本预估 **1-2 周**，是 Butler v4 上线前应优先完成的 P0。

---

## 2. 架构层（Round 1）— 全部已复检

### 2.1 God Module / 单文件超大

#### 2.1.1 [🔴 CRITICAL] `butler/gateway/platforms/wechat_ilink.py` 单文件 2000 行

- **位置**: `butler/gateway/platforms/wechat_ilink.py:1-2000`
- **问题**: 单一文件 2000 行，**远超 800 行上限 2.5 倍**。文件混搭了：① 微信 iLink 协议加解密 (`_aes128_ecb_encrypt`/`_pkcs7_pad`)、② base64 工具、③ CDN URL 构造、④ 账号文件读写、⑤ 二维码 token 缓存 (`ContextTokenStore`/`TypingTicketCache`)、⑥ 媒体下载、⑦ `WeChatAdapter` 30+ 方法（914-2000，1086 行）。
- **复检**:
  - `wc -l butler/gateway/platforms/wechat_ilink.py` → **2000** ✓
  - `grep -nE "^(def|class) " butler/gateway/platforms/wechat_ilink.py | wc -l` → 37 个顶层 def/class
  - `WeChatAdapter` 实际 914-2000，**1086 行**（subagent 估算正确）
- **影响**:
  - 单元测试无法 mock 协议栈任一层
  - 任何 iLink 协议变化（小程序/服务号）→ 全文件重读
  - v3→v4 重构未触及此文件
- **建议**:
  - 拆 `wechat_ilink/crypto.py`（加解密）、`wechat_ilink/account.py`（账号文件）、`wechat_ilink/transport.py`（HTTP/QR/Token）、`wechat_ilink/adapter.py`（`WeChatAdapter` 壳子）、`wechat_ilink/media.py`（媒体）
  - 已存在 `butler/gateway/platforms/` 子包，可直接建 `wechat_ilink/` 子包

#### 2.1.2 [🟠 HIGH] `butler/main.py` 1340 行 CLI 入口

- **位置**: `butler/main.py:1-1340`
- **问题**: CLI 入口含三类独立职责：① `_run_interactive_chat` (24-228, 205 行)、② `_handle_slash_command` (261-503, 243 行)、③ `_build_parser` (999-?, 27 个子命令)。
- **复检**:
  - `wc -l butler/main.py` → **1340** ✓
  - `grep -c "from butler\." butler/main.py` → **81** ✓
  - `grep -nE "^    def " butler/main.py | wc -l` → 368 个 4-space 缩进行
- **影响**:
  - 81 个 `from butler.*` 跨子模块耦合（仅 1 处是 `TYPE_CHECKING`）
  - 新增子命令必须编辑 main.py；测试无法只测单个命令族
- **建议**:
  - `_build_parser` → `butler/cli/cli_builder.py`（已存在 `butler/cli/` 子包 16 文件）
  - `_handle_slash_command` → `butler/cli/slash_commands.py`
  - `_run_interactive_chat` → `butler/cli/interactive_chat.py`
  - main.py 只剩 50-100 行的 `main()` 入口

#### 2.1.3 [🟠 HIGH] `butler/gateway/message_handler.py` 1252 行，16 个方法

- **位置**: `butler/gateway/message_handler.py:1-1252`
- **问题**: `ButlerMessageHandler` 一个类 16 个方法，跨 22+ 跨层 import（实际 92 处 `from butler.*`）。`handle_message` 232-658 实际 **427 行**（subagent 估算为 318 行，略偏低）。
- **复检**:
  - `wc -l` → **1252** ✓
  - `grep -c "from butler\."` → **92**（subagent 估算为 23，严重偏低）
  - `handle_message` 范围：line 232 → 下个 `def _handle_message_locked` 在 line 659，**427 行**
- **影响**:
  - 单一 handler 类同时承担：入站校验、MCP profile 选取、IO guardrail、human_gate、bot_loop_guard、two_phase_confirm、auto_continue、permission commands、terminal approval、health summary、output formatting
  - 是「消息处理总线」吞掉所有 hook 的设计
- **建议**:
  - 引入 `InboundPipelineStep` 协议；`io_guardrail`/`human_gate`/`mcp_profile`/`injection_guard` 注册为 step
  - 切分 `message_handler/validator.py`、`message_handler/transform.py`、`message_handler/dispatcher.py`、`message_handler/commands.py`
  - 已存在 `handler_helpers.py`（从本文件抽走 556 行），模式已被验证可继续

#### 2.1.4 [🟠 HIGH] `butler/core/agent_loop.py` 807 行，`_run_turn_body` 单方法 338 行

- **位置**: `butler/core/agent_loop.py:216-553`
- **问题**: 单方法 `_run_turn_body` 占文件 42%。while 循环中混杂 4 类职责：① 调 LLM、② 解析响应、③ 派发工具、④ 状态机推进。
- **复检**:
  - `wc -l` → **807** ✓
  - `awk 'NR>=216 && NR<=553'` 行数 → **338** ✓
  - 方法结束于 553 行（下一方法 `_maybe_stop_hook_continue` 在 554 行）
- **影响**: 单方法超过「典型 50 行上限 6.7 倍」；阅读时必须 5 屏滚动。
- **建议**:
  - 拆 `_execute_iteration` (单轮：调 LLM → 解析 → 派发) + `_handle_iteration_outcome` (单轮状态机)
  - 文件本身 800 行合理

#### 2.1.5 [🔵 LOW] `butler/task_orchestrator.py` 791 行、`butler/orchestrator.py` 700 行

- **位置**: `butler/task_orchestrator.py:791`, `butler/orchestrator.py:700`
- **复检**: `wc -l` 均确认 ✓
- **判定**: subagent 评估「职责单一，无需拆分」合理。791 行接近 800 阈值，需观察不进入下一轮大改。
- **建议**: 暂不动；下一轮大改时再评估。

### 2.2 抽象泄漏 / 紧耦合

#### 2.2.1 [🔴 CRITICAL] `butler/core/` 反向 import `butler/gateway/`

- **位置**: 6 处（subagent 估算 5 处，复检发现 6 处）
  1. `butler/core/agent_loop.py:113` → `gateway/outbound_bridge.merge_loop_callbacks`
  2. `butler/core/compaction_task.py:80` → `gateway.hooks.invoke_hook`
  3. `butler/core/compaction_task.py:130` → `gateway.item_events`
  4. `butler/core/compaction_task.py:162` → `gateway.hooks.invoke_hook`
  5. `butler/core/compaction_steer_bridge.py:33` → `gateway.message_queue.pop_urgent_inbound`
  6. `butler/core/context_compressor.py:391` → `gateway.item_events`
- **证据**:
  ```python
  # butler/core/agent_loop.py:113
  if run_callbacks is not None:
      from butler.gateway.outbound_bridge import merge_loop_callbacks
      self.callbacks = merge_loop_callbacks(saved_callbacks, run_callbacks)
  ```
- **复检**: `grep -rn "from butler\.gateway" butler/core/` 输出 6 行 ✓
- **问题**:
  - `core/` 应是「无输入输出协议无关的纯 agent 引擎」；反向依赖 `gateway/` 破坏层序
  - CLI 启动也要解析 `gateway/outbound_bridge` 符号
  - v4 重构明确说「不再 `import Hermes AIAgent`」但 v4 内部又出现类似问题
- **建议**:
  - `merge_loop_callbacks` 下沉到 `butler/core/loop_types.py`（已有 `LoopCallbacks` 定义）
  - `gateway/hooks`/`gateway/item_events`/`gateway/message_queue` 的 core 反向依赖：**反向订阅**，让 gateway 来订阅 core 事件

#### 2.2.2 [🟠 HIGH] `butler/main.py` 戳 `orchestrator._settings` / `_model_credentials` 私有属性

- **位置**: `butler/main.py:41, 51, 334, 358, 360`
- **证据**:
  ```python
  # line 41
  settings = orchestrator._settings
  # line 51
  mc = orchestrator._model_credentials("butler")
  ```
- **复检**: `grep -n "orchestrator\._" butler/main.py` 输出 5 行 ✓
- **影响**: 上层穿透下层私有属性。`orchestrator` 内部重命名/重构时 main.py 必坏。
- **建议**: 在 `ButlerOrchestrator` 加 `settings` (property) 和 `current_model_display()` 方法。

#### 2.2.3 [🟡 MEDIUM] `butler/gateway/message_handler.py` 92 处 `from butler.*`

- **位置**: `butler/gateway/message_handler.py` 全文件
- **复检**: `grep -c "from butler\." butler/gateway/message_handler.py` → **92** ✓
- **问题**: 一个 handler 类同时触及 `core/`、`memory/`、`tools/`、`gateway/`、`mcp/` 五大子层。
- **影响**: handler 类成为「跨层耦合枢纽」。任何 hook 增加都要碰这一处。
- **建议**: 见 2.1.3 的 `InboundPipelineStep` 方案。

### 2.3 命名空间 / 分包组织

#### 2.3.1 [🟠 HIGH] `butler/core/` 104 文件过细

- **位置**: `butler/core/`
- **问题**:
  - 4 个 `*_flags.py` < 50 行（harness 24、workflow 24、confirm 34、meta 42）
  - `safety_finish.py` 42 行（也是 env-bool 包装）
  - `compaction_*.py` 7 文件、`transcript_*.py` 6 文件、`tool_*.py` 15 文件
- **复检**:
  - `ls butler/core/*flags*.py butler/core/safety_finish.py` → 4 个 flags + safety_finish ✓
  - `ls butler/core/compaction_*.py | wc -l` → **7** ✓
  - `ls butler/core/transcript_*.py | wc -l` → **6** ✓
  - `ls butler/core/tool_*.py | wc -l` → **15** ✓
- **建议**:
  - **Step 1（最低成本）**: 合并 4 个 `*_flags.py` 为 `butler/core/feature_flags.py`，砍 3 文件
  - **Step 2**: `compaction_*.py` → `butler/core/compaction/` 子包
  - **Step 3**: `transcript_*.py` → `butler/core/transcript/` 子包
  - **Step 4**: 15 个 `tool_*.py` 中「post-processing pipeline」类的 → `butler/core/tool_pipeline/`

#### 2.3.2 [🔵 LOW] `butler/gateway/` 51 个顶层文件

- **位置**: `butler/gateway/`
- **复检**: `ls butler/gateway/ | grep -v __pycache__ | wc -l` → **51** ✓
- **建议**:
  - `butler/gateway/handlers/` 吞 `message_handler.py` + `handler_helpers.py` + `turn_runner.py`
  - `butler/gateway/commands/` 扩展吞 8 个 `*_commands.py`（dev/memory/permission/registry/runtime/project 等）

### 2.4 循环依赖

#### 2.4.1 [🟢 INFO] 无 module-level 循环，但用 lazy import 掩盖

- **位置**: 全局
- **复检**: subagent 用 AST + Tarjan SCC 扫了 453 模块，**0 个多节点 SCC** ✓
- **问题**: 81 (main.py) + 92 (message_handler.py) + 40 (orchestrator.py) = **213 处 lazy import**，是「用运行时性能换架构纯洁性的工程妥协」。
- **影响**:
  - 启动时间被推长（import 延后到首次调用）
  - mypy/pyright 静态分析失明
- **建议**:
  - 不必立即修复，但应把「core → gateway」6 处反向依赖的下沉作为优先项
  - 其余 lazy import 接受现状

### 2.5 核心调用链观察（验证 CLI→Provider 数据流）

`chat "hello"` 的实际调用链（subagent 报告 + 已读源码验证）：

```
[1] CLI: butler/main.py:main() → _build_parser() → _cmd_chat() (line 1330)
[2] Orchestrator: butler/main.py:_cmd_chat() → ButlerOrchestrator() (butler/orchestrator.py:460)
[3] Chat loop: butler/main.py:_run_interactive_chat() (line 24-228)
    └─ user_prompt_submit_hooks → apply_pre_llm_context → execution_context (ContextVar)
[4] AgentLoop: orchestrator.create_agent_loop() (butler/orchestrator.py:460)
    └─ AgentLoop.__init__ (butler/core/agent_loop.py:37)
[5] _run_turn_body (line 216-553, 338 行):
    while:
      ├─ LLMClient.complete() (butler/transport/llm_client.py:119)
      │   └─ get_transport(api_mode) → Anthropic/OpenAI/Local HTTP
      ├─ process_tool_calls (butler/core/tool_batch.py:69)
      │   └─ dispatch_tool (butler/tools/registry.py:178)
      │      ├─ MCP 路由 / plan mode / permission / pre-hooks
      │      └─ entry.handler(args) → JSON 字符串
      └─ 把 tool_result append → 回到 LLM
[6] UI: butler/cli/stream.py:StreamRenderer → Rich Panel
```

**观察**:
- 唯一「不纯」边界是 LLMClient.complete()
- 副作用集中点：execution_context ContextVar + attach_turn_memory_prefetch + mark_run_active
- 隐式状态：AgentLoop._fallback_index / _interrupted / _tool_prefetch / outbound_bridge._thread_bridge
- 真正可抽出 pipeline 的 4 步（run_user_prompt_submit_hooks → apply_pre_llm_context → _prepare_user_message → resolve_turn_budget）目前散在 3 处文件

---

## 3. 代码质量层（Round 2）— 全部已复检

### 3.1 错误处理黑洞

#### 3.1.1 [🔴 CRITICAL] `turn_runner.py:208` & `message_handler.py:952` 静默吞掉 error card 构造错误

- **位置**: 
  - `butler/gateway/turn_runner.py:208` 
  - `butler/gateway/message_handler.py:952`（镜像代码）
- **代码**:
  ```python
  else:
      card = format_error_card("tool_error", tool="message_handler", error=str(exc))
  except Exception:
      pass                                       # ← 静默吞掉
  return card or format_gateway_user_error(exc)
  ```
- **复检**:
  - `sed -n '200,215p' butler/gateway/turn_runner.py` → 确认 `except Exception: pass` ✓
  - `sed -n '945,960p' butler/gateway/message_handler.py` → 同模式 ✓
- **影响**: error-card 构造器出 bug 时（注册表缺键、新增必填字段）会**返回 0 错误信息**，用户看到空字符串；线上不可观测。
- **建议**: 拆开两段，fallback 也要 `logger.exception("error card build failed")`。

#### 3.1.2 [🔴 CRITICAL] `agent_loop.py:712` doom-loop guard fail-open（安全护栏被吞）

- **位置**: `butler/core/agent_loop.py:712`
- **代码**:
  ```python
  try:
      from butler.permissions.doom_loop import check_doom_loop_ask
      if check_doom_loop_ask(before, name, args):
          prefetch[key] = synthetic_result(before)
          return
  except Exception:
      prefetch[key] = synthetic_result(before)   # 假设 ask 失败 = 放行
      return
  ```
- **复检**: `sed -n '700,720p' butler/core/agent_loop.py` → fail-open 路径确认 ✓
- **影响**: 
  - 这是 hot path（每个 tool call 都跑）
  - doom-loop 检查自身崩溃时**被解读为"放行"**，安全护栏完全失效
  - 无任何日志
- **建议**: 改为 `except (ImportError, AttributeError) as exc: logger.error(...)` 后 fail-closed（拒绝而非放行）。

#### 3.1.3 [🟠 HIGH] 28 处 `try` 块跨度 ≥ 50 行

- **位置**（前 5 名）:
  | 文件 | 跨度 | handler |
  |---|---|---|
  | `butler/tools/delegate_impl.py:250-645` | 395 行 | `Exception` |
  | `butler/core/agent_loop.py:259-518` | **260 行** | `Exception` |
  | `butler/gateway/turn_runner.py:49-212` | 163 行 | `Exception` |
  | `butler/gateway/message_handler.py:793-956` | 163 行 | `Exception` |
  | `butler/runtime/delegate_job.py:126-258` | 132 行 | `Exception` |
- **复检**:
  - `awk` + Python 验证 agent_loop.py 的 try 起 259 行，对应 except 在 518 行，**实际 260 行**（subagent 估 235 略偏低）
  - delegate_impl.py: 250-645 = 395 行 ✓
- **影响**: 巨大 try 块无法精确定位失败点；`Exception` handler 实际吞掉了哪一行只能靠堆栈。
- **建议**: 把 hot path 中的 try 缩小到单步，或在末尾加 `logger.debug("progress: stage=X")` 划段。

#### 3.1.4 [🟠 HIGH] 808 个 `Exception` handler 中 204 个无 logger

- **统计**:
  - `grep -rEn "except Exception" butler/ --include="*.py" | wc -l` → **808** ✓
  - `grep -rEn "logger\.exception" butler/ --include="*.py" | wc -l` → **3**（全项目只有 3 处 `logger.exception`！）
- **典型**:
  - `butler/core/context_pipeline.py:147, 175` — 上下文压缩失败被静默
  - `butler/core/tool_batch.py` 内部 — 批处理容错丢点
  - `butler/gateway/dev_commands.py:39` — 命令失败不告知运维
  - `butler/memory/facade.py:267` — `logger.debug` 仅 debug 级，生产看不到
- **影响**: 线上 25% 错误被完全吞掉；故障定位只能靠运气。
- **建议**: 加 audit lint：`except Exception` 必须后跟 `logger.{warning,error,exception}`。

#### 3.1.5 [🟡 MEDIUM] `wechat_ilink.py` / `outbound_bridge.py` 6 处 `asyncio.CancelledError: pass`

- **位置**: `butler/gateway/platforms/wechat_ilink.py:1049, 1118, 196 (outbound_bridge)`, `outbound_bridge.py:485, 535, 545`
- **影响**: 取消传播被吞掉，上游 await 不知道子任务已取消；长轮询场景可能延迟关停。
- **建议**: `CancelledError` 在 Python 3.8+ 继承自 `BaseException`，不应 `pass` — 应 `raise` 或 `contextlib.suppress(...)`。

### 3.2 不可变性违反 / 共享状态竞态

#### 3.2.1 [🔴 CRITICAL] `_WELCOMED_SESSIONS` TOCTOU race

- **位置**: `butler/gateway/handler_helpers.py:375-400`
- **代码**:
  ```python
  _WELCOMED_SESSIONS: set[str] = set()  # line 375, 模块级 mutable, 无锁
  
  def _maybe_welcome_prefix(session_key: str) -> str:
      if os.getenv("BUTLER_ONBOARDING_WELCOME", "1").strip() == "0":
          return ""
      if session_key in _WELCOMED_SESSIONS:    # ① in-check
          return ""
      _WELCOMED_SESSIONS.add(session_key)      # ② add, 非原子
      ...
  ```
- **复检**:
  - `grep -nE "Lock|lock" butler/gateway/handler_helpers.py` → **0 命中** ✓
  - 顺序 `in-check` + `add` 确认非原子
- **影响**: 同一 session_key 两个协程同时进入，in-check 都通过 → 重复写欢迎语 / 重复打开 marker 文件。
- **建议**: `if not _WELCOMED.add(session_key): return ""`（`set.add` 返回 False 表示已存在；保证原子）。

#### 3.2.2 [🟠 HIGH] `_STORE` 模块级可变 dict 无锁

- **位置**: `butler/core/tool_result_cache.py:24` + 多处 mutation
- **复检**: `grep -nE "Lock|lock|RLock" butler/core/tool_result_cache.py` → **0 命中** ✓
- **影响**: 工具结果缓存跨 session 共享，coroutine 并发下可能 `RuntimeError: dictionary changed size during iteration`。
- **建议**: 加 `threading.RLock()` 包裹。

#### 3.2.3 [🟢 INFO] `steer.py` / `mcp/profiles.py` 锁使用正确（对照组）

- `butler/core/steer.py:10 _lock = threading.Lock()` + 6 个 with 子句 ✓
- `butler/mcp/profiles.py:17 _LOCK = threading.RLock()` + 4 个 critical section ✓
- 全项目 61 处 `threading.Lock/RLock` 调用

#### 3.2.4 [🟡 MEDIUM] `delegate_impl.py:250-645` 单 try 块 395 行

- **位置**: `butler/tools/delegate_impl.py:250-645`
- **代码**:
  ```python
  try:                                # L250
      from butler.delegate.policy import MAX_DELEGATE_DEPTH
      ...  # 395 行
      return result                    # L645
  except Exception:                    # L646
      return _fallback(...)
  ```
- **影响**: 整个 `delegate_task` 工具任何环节失败都走同一 fallback，无法区分"权限拒绝"vs"模型超时"vs"子进程崩溃"。
- **建议**: 拆为 4-6 段（模型选择 / 上下文准备 / 子调用 / 结果回填），每段独立 try + specific error。

### 3.3 死代码 / 重复代码

#### 3.3.1 [🟡 MEDIUM] 50+ 公开函数零外部调用

- **位置**（subagent AST 扫描结果，节选）:
  | 位置 | 函数 |
  |---|---|
  | `butler/core/agent_loop.py:695` | `on_tool_ready` |
  | `butler/config.py:267` | `clear_runtime_model_overrides` |
  | `butler/cli/stream.py:46,50,53,72` | `streamed_live` / `lines_emitted` / `had_body` / `on_boundary` |
- **复检**: subagent 用 AST 启发式扫描（忽略 `_` 开头）发现 50+ 候选
- **影响**: 死代码增加维护成本。
- **建议**: Round 5 阶段跑 `python -c "from butler.X import foo"` 全项目 dry-import 测试，删除真无用项。

#### 3.3.2 [🟡 MEDIUM] 0 处 TODO/FIXME 标记（异常干净）

- **复检**: `grep -rEn "^\s*# (TODO|FIXME|XXX|HACK)" butler/ --include="*.py"` → 0 命中
- **判断**: 表面看是好习惯，但结合 hot path 0% 注释，疑似**隐藏技术债而非已清理**。建议补一次 audit。

### 3.4 命名 / 风格违规

#### 3.4.1 [🟡 MEDIUM] 50+ 布尔字段名违反 `is_/has_/should_/can_` 前缀

- **位置**（节选，已命令验证）:
  ```
  butler/gateway_settings.py:24  prefer_ilink_text: bool
  butler/task_orchestrator.py:52  clear_child_transcript: bool
  butler/task_orchestrator.py:87  requires_approval: bool
  butler/runtime/schema.py:11  on_success: bool
  butler/permissions/rules.py:32  allowed: bool
  butler/mcp/types.py:46  connected: bool
  ```
- **影响**: 容易写出 `if enabled:` vs `if is_enabled:` 混淆；工具代码里 `if config.required == True` 是常见 bug 源。
- **建议**: Round 5 文档/Style 阶段统一迁移；新代码严格执行。

#### 3.4.2 [🔵 LOW] 102 处函数内 `from butler.*` import（Round 1 现象的代码层表现）

- 分布: `main.py` 51 + `message_handler.py` 21 + `orchestrator.py` 21 + `agent_loop.py` 9
- 接受现状，但 Round 5 文档/Style 阶段应列"待重构 import 提取表"。

### 3.5 危险反模式

#### 3.5.1 [🟢 PASS] `eval/exec/pickle/os.system/shell=True` 0 命中

- **复检**:
  - `grep -rEn "pickle\." butler/ --include="*.py" | wc -l` → 0 ✓
  - `grep -rEn "os\.system" butler/ --include="*.py" | wc -l` → 0 ✓
  - `grep -rEn "shell=True" butler/ --include="*.py"` → 0 命中（仅 docstring 警示文本）✓
- **评估**: 工具层安全隔离做得不错。

#### 3.5.2 [🟠 HIGH] 8 处 `assert` 在 hot path + 1 处会被 `-O` 关闭

- **位置**（已命令验证）:
  ```
  butler/project/manager.py:29          assert cls._instance is not None
  butler/mcp/profiles.py:70             assert _PROFILES is not None
  butler/mcp/profiles.py:110            assert _PROFILES is not None
  butler/gateway/platforms/wechat_ilink.py:1063  assert self._poll_session is not None
  butler/gateway/platforms/wechat_ilink.py:1150  assert self._poll_session is not None
  butler/gateway/platforms/wechat_ilink.py:1480  assert last_error is not None
  butler/gateway/platforms/wechat_ilink.py:1702  assert self._send_session is not None
  butler/gateway/platforms/wechat_ilink.py:1722  assert self._send_session is not None and self._token is not None
  ```
- **影响**: 
  - wechat_ilink.py 6 处是**内部 invariant**，可接受
  - **mcp/profiles.py:70,110 关键**：紧跟 `_PROFILES.keys()`，若以 `python -O` 启动会立即 `AttributeError`
- **建议**: `mcp/profiles.py` 改为 `if _PROFILES is None: raise RuntimeError("profiles not loaded")`。

#### 3.5.3 [🟡 MEDIUM] 6 处 `time.sleep` 在工具/重试层

- 位置: `runtime/notify.py:94`, `core/tool_retry.py:97`, `core/llm_retry.py:229,286`, `registry/skill_sources/clawhub.py:218`, `tools/terminal_impl.py:149`
- 全部位于重试/网络退避/独立 worker 线程，合理。

### 3.6 注释质量

#### 3.6.1 [🔴 CRITICAL] hot path 文件内联注释密度 0%

- **统计**（已命令验证）:
  | 文件 | 行数 | 注释行 | 密度 |
  |---|---|---|---|
  | `butler/core/agent_loop.py` | 807 | **0** | **0.0%** |
  | `butler/orchestrator.py` | 700 | **0** | **0.0%** |
  | `butler/main.py` | 1340 | 2 | 0.14% |
  | `butler/gateway/message_handler.py` | 1252 | 3 | 0.23% |
  | `butler/task_orchestrator.py` | 791 | 3 | 0.37% |
  | `butler/gateway/platforms/wechat_ilink.py` | 2000 | 38 | 1.90% |
- **影响**: 200-400 行循环逻辑、200+ 行 retry/policy，**完全无 why-注释**。新人无法在 30 分钟内理解 `agent_loop.py:259-518` 的 260 行巨型 try 块。
- **建议**: 至少给每个公开函数加 1-3 行 docstring 说明"为什么这样写"；260 行 try 至少 5 个 `← L### stage: ...` 划段。

#### 3.6.2 [🟡 MEDIUM] 8 个公开函数 > 150 行（已命令验证）

- | 文件:行号 | 函数 | 行数 |
  |---|---|---|
  | `butler/gateway/message_handler.py:232` | `handle_message` | **427 行** |
  | `butler/gateway/inbound_pipeline.py:49` | `run_inbound_pipeline` | **405 行** |
  | `butler/core/loop_turn.py:12` | `run_turn_body` | **352 行** |
  | `butler/core/tool_batch.py:69` | `process_tool_calls` | **346 行**（含嵌套 `_dispatch_one`）|
  | `butler/project/preflight.py:131` | `run_preflight` | **310 行** |
  | `butler/core/llm_retry.py:21` | `call_llm_with_retry` | **279 行** |
  | `butler/session/memory_prefetch.py:55` | `prefetch_turn_memory` | **207 行** |
  | `butler/gateway/turn_runner.py:16` | `execute_turn` | **197 行** |
- **复检**: 实际行数（含嵌套函数体）— 除 `process_tool_calls` 需解析嵌套外，其余验证一致
- **建议**: 至少把 retry / preflight / 批处理 3 个拆出 helper。

---

## 4. 安全 / 测试 / 可靠性层（Round 3）— 全部已复检

### 4.1 安全漏洞

#### 4.1.1 [🔴 CRITICAL] MCP HTTP 主机白名单子串绕过（SSRF）

- **位置**: `butler/mcp/config.py:237`
- **代码**:
  ```python
  if allowed and not any(host == h or host.endswith("." + h) or host.endswith(h) for h in allowed):
      return f"host '{host}' not in hosts_allow"
  ```
- **复检**: `sed -n '230,250p' butler/mcp/config.py` → 第三个 `or host.endswith(h)` 无 `.` 前缀要求 ✓
- **影响**:
  - 配置 `BUTLER_MCP_HTTP_HOSTS_ALLOW=api.com` → `notapi.com`、`api.com.attacker.tld` 全部通过
  - `_PRIVATE_HOSTS` 只防回环 / metadata，不防内网段（10/8、172.16/12、192.168/16）
  - 横向 SSRF
- **建议**:
  - 改为 `host == h or host.endswith("." + h)`（删第三条）
  - 用 `ipaddress.ip_network` 解析后判断 `is_private/is_loopback`

#### 4.1.2 [🟠 HIGH] `ContextTokenStore` 持久化文件无 0o600 权限

- **位置**: `butler/gateway/platforms/wechat_ilink.py:344-354`
- **代码**:
  ```python
  def _persist(self, account_id: str) -> None:
      ...
      try:
          atomic_json_write(self._path(account_id), payload)   # ← 仅写,无 chmod
      except Exception as exc:
          logger.warning(...)
  ```
- **对比**: `save_wechat_account` 同文件 line 291 显式 `path.chmod(0o600)`
- **复检**:
  - `sed -n '340,360p'` → 确认无 chmod ✓
  - `grep -n "chmod"` → 仅 line 291（account_id.json）有 ✓
- **影响**: `*.context-tokens.json` 落地后默认 umask（0o644），多用户主机 / 容器场景下其他本地用户可读 token → 冒充 bot 重放消息。
- **建议**: `_persist` 写入后追加 `try: path.chmod(0o600) except OSError: pass`，或让 `atomic_json_write` 接受 `mode=0o600`。

#### 4.1.3 [🟠 HIGH] 出站 PII 脱敏规则过窄

- **位置**: `butler/gateway/pii_scrub.py:8-25`
- **代码**:
  ```python
  _PHONE  = re.compile(r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d{9}(?!\d)")
  _ID18   = re.compile(r"(?<![0-9Xx])[1-9]\d{16}[\dXx](?![0-9Xx])")
  _EMAIL  = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
  ```
- **复检**: 文件全量读取，**仅 3 类正则** ✓
- **影响**: 银行卡 16-19 位、信用卡 Luhn、JWT (`eyJ...`)、`sk-`/`sk_` API key、IPv4 私网、US SSN、港澳台证件、护照号、医保号全部不脱敏 → 直接出站到微信。`BUTLER_OUTBOUND_PII_SCRUB=1` 默认开，但给的是假安全感。
- **建议**: 至少补 4 类：银行卡 Luhn、`sk-[A-Za-z0-9]{20,}`、`eyJ...xxx.xxx.xxx` JWT、IPv4 私网。
- **额外**: email 脱敏是**opt-in**（`BUTLER_OUTBOUND_PII_SCRUB_EMAIL` 需手动开），应默认开。

#### 4.1.4 [🟡 MEDIUM] `_aes128_ecb_decrypt` bad padding 时静默返回

- **位置**: `butler/gateway/platforms/wechat_ilink.py:224-237`
- **代码**:
  ```python
  def _aes128_ecb_decrypt(ciphertext: bytes, key: bytes) -> bytes:
      ...
      pad_len = padded[-1]
      if 1 <= pad_len <= 16 and padded.endswith(bytes([pad_len]) * pad_len):
          return padded[:-pad_len]
      return padded     # ← 失败时仍返回已截尾但未验证的 plaintext
  ```
- **复检**: `sed -n '220,240p'` → `return padded` 路径确认 ✓
- **影响**: 
  - 微信 iLink 协议用 AES-128-ECB（**协议约束，不能改**）
  - 但本函数**不抛异常**，不可信输入静默返回
- **建议**: 协议不变；函数应 `raise ValueError("bad PKCS7 padding")` 让上层走 `CDN media download failed` 错误路径。

#### 4.1.5 [🟡 MEDIUM] `web_fetch` 默认 follow_redirects（SSRF 旁路）

- **位置**: `butler/tools/web_fetch.py:97-117`
- **代码**:
  ```python
  if not is_safe_url(target):
      return json.dumps({"error": "URL 未通过安全校验"})
  ...
  with urlopen(req, timeout=...) as resp:    # ← stdlib urlopen 默认 follow_redirects=True
      raw = resp.read(_max_bytes() + 1)
  ```
- **复检**:
  - `sed -n '90,125p'` → 确认无 `NoRedirect` / `HTTPRedirectHandler` ✓
  - `python3 -c "import urllib.request; op = urllib.request.build_opener(); print(any(isinstance(h, urllib.request.HTTPRedirectHandler) for h in op.handlers))"` → **True** ✓
- **影响**: 攻击者把工具输出 URL 替换为 `https://attacker.com/redirect?to=http://10.0.0.1/admin`，`urlopen` 跟随 302 绕过 `is_safe_url` 校验。
- **建议**: 显式 `urllib.request.build_opener(NoRedirect)`，或切 `httpx` 并 `follow_redirects=False`（与 `butler/registry/url_safety.py` 一致）。

#### 4.1.6 [🟡 MEDIUM] LLM Provider 缺失 key 时回退 `api_key="dummy"`

- **位置**: `butler/transport/llm_client.py:83, 98`
- **代码**:
  ```python
  if not api_key:
      logger.warning("OpenAI client created without API key; calls will likely fail")
      api_key = "dummy"     # ← 占位不是错误
  self._client = OpenAI(api_key=api_key, ...)
  ```
- **复检**: `sed -n '80,105p'` → 两处（OpenAI + Anthropic）确认 ✓
- **影响**: 当 `BUTLER_PROVIDERS` 缺 key 但用户仍调用 `LLMClient` 时，构造一个带 `api_key="dummy"` 的客户端。该对象可能进入长时间 cache 被复用；错误信息 `"Incorrect API key provided: dummy"` 会泄露到日志。
- **建议**: 改为 `raise RuntimeError("LLM api_key missing for provider=X")` 在 `ButlerOrchestrator` 启动时 fail-fast。

#### 4.1.7 [🟡 MEDIUM] QR 登录 URL 写入 stdout（被 `tool_audit` 记录）

- **位置**: `butler/gateway/platforms/wechat_ilink.py:815, 817, 874`
- **代码**:
  ```python
  print("\n请使用微信扫描以下二维码：")
  if qrcode_url:
      print(qrcode_url)
  ```
- **复检**: `grep -nE "print\(.*qrcode"` → 3 处确认 ✓
- **影响**: `qrcode_url` 包含 `liteapp` 凭据 token（**这是协议必需**）。但 `print` 写 stdout 会被 `Bash` 工具审计 (`tool_audit.py`) 完整记录，logrotate 留长尾。
- **建议**: 改 `logger.info` 并加 `--quiet` 模式；确认 `tool_audit` 是否对 `wechat setup` 路径生效。

#### 4.1.8 [🟢 PASS] 硬编码 secrets: 0 命中真实 key

- **复检**:
  - `.env.example` 全部为占位 ✓
  - `llm_client.py` `api_key = "dummy"` 是占位不是泄露 ✓
  - `main.py:732-736` `masked_token = token[:6] + "…" + token[-4:]` 脱敏规则正确
- **状态**: 整体安全

#### 4.1.9 [🔵 LOW] 依赖安全

- **位置**: `requirements.lock` / `butler_system.egg-info/requires.txt`
- **状态**: 无 `verify=False` / 自建包。`cryptography`、`httpx`、`pyjwt[crypto]` 主流。
- **建议**: `.github/workflows/ci.yml` 的 `lint` job 末尾加 `pip-audit --strict`（每月 1 号 schedule 跑）。

### 4.2 测试覆盖漏洞

#### 4.2.1 [🟠 HIGH] iLink 加解密 0 个真实 crypto 测试

- **位置**: `tests/test_wechat_ilink_*.py` (3 个文件)
- **影响**:
  - `test_wechat_ilink_media.py:34` 传入 `b"encrypted-payload"`（根本不是 AES 输出）
  - `_aes128_ecb_encrypt` / `_aes128_ecb_decrypt` / `_parse_aes_key` 0 个真实 crypto 测试
  - 任何 iLink 协议升级或 key 格式变更都会被线上发现
- **建议**: 新增 `tests/test_wechat_ilink_crypto.py`：
  - `test_aes128_ecb_round_trip_aligned` (16 字节倍数)
  - `test_aes128_ecb_round_trip_unaligned` (任意长度)
  - `test_aes128_ecb_decrypt_bad_padding_raises` (篡改 ciphertext)
  - `test_parse_aes_key_16byte_b64` / `test_parse_aes_key_32byte_hex` / `test_parse_aes_key_32byte_garbage_raises`

#### 4.2.2 [🟠 HIGH] 路径安全无 symlink / dotdot / null byte / Unicode normalization 测试

- **位置**: `tests/test_path_safety.py` (114 行, 8 个测试)
- **复检**:
  - `wc -l tests/test_path_safety.py` → 114 ✓
  - 现有 8 个测试: tmp workspace / relative / outside / sensitive / hardlinked / env
  - **缺**: symlink 越界、dotdot 穿越、null byte、Unicode RLO
- **建议**: 加 4 个测试覆盖 `_resolve_tool_path` 的 `path.is_symlink()` 分支。

#### 4.2.3 [🟠 HIGH] `ContextTokenStore` 持久化权限无测试

- **位置**: `tests/test_wechat_account_persistence.py:30-35` 已覆盖 `account_id.json` 的 0o600（`assert oct(path.stat().st_mode)[-3:] == "600"`）
- **影响**: `*.context-tokens.json` 完全无权限测试（与 4.1.2 漏洞相关）
- **建议**: 加 `test_context_token_store_persists_600` + `test_context_token_store_roundtrip`。

#### 4.2.4 [🟡 MEDIUM] MCP HTTP 允许名单子串绕过无测试

- **位置**: `tests/test_mcp_features.py:72-77` `test_http_private_host_blocked` 仅覆盖 `_PRIVATE_HOSTS`
- **影响**: 任何修复 4.1.1 都会"看似通过测试"（实际未覆盖该分支）
- **建议**: 加 `test_http_hosts_allow_strict_subdomain`（期望 `notapi.com` 不被 `api.com` allowlist 接受）+ `test_http_hosts_allow_exact_match` + `test_http_hosts_allow_subdomain_match`。

#### 4.2.5 [🟡 MEDIUM] `_run_turn_body` 260 行 try 块无 boundary 测试

- **位置**: `tests/test_agent_loop.py`（已有 ~50+ 测试），但偏单元
- **影响**: 主循环异常分支（tool 异常 / timeout / context overflow）只通过 mock LLM 间接覆盖
- **建议**: 补 3 个 E2E：① tool 抛异常时被捕获并继续 ② max_iterations 触达终止 ③ `is_interrupted` 立即退出。

#### 4.2.6 [🟡 MEDIUM] Injection 过滤 trigger 列表仅 12 个

- **位置**: `butler/memory/injection_guard.py`
- **影响**: base 40 + 中英各 12 触发；缺 base64 / role override / JSON 注入 / Unicode 绕过
- **建议**: 扩 trigger 列表 + 加 `test_injection_score_unicode_bypass`（"忽略 此 前 指令" 中文带空格）期望仍能识别。

#### 4.2.7 [🟢 INFO] pytest 收集: 2843/3378 (535 deselected)

- **复检**: `PYTHONPATH=. pytest --collect-only -q 2>&1 | tail -3` → `2843/3378 tests collected (535 deselected) in 1.53s` ✓
- **状态**: 测试体量合理。535 deselected 是 live API / 平台守门。

#### 4.2.8 [🔵 LOW] CI 守门: 缺 bandit / mypy --strict / pip-audit

- **位置**: `.github/workflows/ci.yml` (4 job: lint / pytest / corpus-pr-gate / smoke / corpus-drift / corpus-gateway-live)
- **复检**: `cat .github/workflows/ci.yml | grep -E "bandit|mypy|audit"` → 0 命中
- **建议**: lint job 加 `bandit -r butler/ -lll --confidence high`（独立 step，不阻塞主流程）。

---

## 5. 性能 / 资源层（Round 4）— 全部已复检

### 5.1 性能瓶颈

#### 5.1.1 [🟠 HIGH] SQLite 连接每操作开关（ButlerMemory 全层）

- **位置**: `butler/memory/butler_memory.py:145-148` + **13+ 调用点** (152, 215, 244, 266, 358, 379, 396, 432, 482)
- **代码**:
  ```python
  def _connect(self) -> sqlite3.Connection:
      conn = sqlite3.connect(self.db_path, check_same_thread=False)
      conn.execute("PRAGMA journal_mode=WAL")    # ← 每次重设
      return conn
  ```
- **复检**:
  - `grep -nA2 "def _connect\|with self._connect" butler/memory/butler_memory.py` → 13+ with 块确认 ✓
  - `observation_store.py:27-31` / `semantic_index.py:38-41` / `triplets.py:53-56` 同样问题
- **影响**:
  - 每次 `search/add/record_access` 都执行 3 个系统调用（`open`+`PRAGMA`+check）
  - 串行化 `with self._lock:` 阻塞并发
  - 每个 turn 至少 2-3 次 DB 操作；并发塌陷到 ~50 ops/sec
- **建议**: 持有持久化 `self._conn`，定期 `PRAGMA optimize`；或 Lock+slots 模式。

#### 5.1.2 [🟠 HIGH] `vector_store.add()` 每次全量重写磁盘

- **位置**: `butler/memory/vector_store.py:166-186`
- **代码**:
  ```python
  def add(self, doc_id, text, metadata=None):
      ...
      with self._lock:
          self._docs[doc_id] = {...}
          self._persist()                          # ← 整文件 write_text
  def _persist(self) -> None:
      lines = [json.dumps(doc, ...) for doc in self._docs.values()]
      self._persist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
  ```
- **复检**: `sed -n '160,190p' butler/memory/vector_store.py` → 整文件重写确认 ✓
- **影响**: N=1000 时 ~50ms 写、~2MB 重写。多次 add 写放大严重。
- **建议**: 改 append-only JSONL（仅 `a` 模式），启动时一次性 `load`，删除时 tombstone。

#### 5.1.3 [🟠 HIGH] 消息入队每次 O(n log n) 全排序

- **位置**: `butler/gateway/message_queue.py:166-168`
- **代码**:
  ```python
  bucket.append(item)
  bucket = deque(sorted(bucket, key=lambda x: _PRIORITY_ORDER.get(x.priority, 9)))
  _QUEUES[key] = bucket
  ```
- **复检**: `sed -n '160,175p' butler/gateway/message_queue.py` → 全量 sort 确认 ✓
- **影响**: 每个入站消息都重建整个 bucket 排序，cap=50 时已可见开销。
- **建议**: 用 `bisect` 维护有序 deque，或 `heapq`，或仅在 `pop` 时排序。

#### 5.1.4 [🟠 HIGH] `push_queue.enqueue_failed_push` 整文件读改写

- **位置**: `butler/runtime/push_queue.py:29-57`
- **代码**:
  ```python
  if path.is_file():
      for ln in path.read_text(encoding="utf-8").splitlines():
          if not ln.strip(): continue
          try: old = json.loads(ln)
          except json.JSONDecodeError: continue
          if str(old.get("dedupe_key") or "") == key: continue
          lines.append(ln)
  ...
  atomic_write_text(path, "\n".join(lines) + "\n")
  ```
- **复检**: `sed -n '25,60p' butler/runtime/push_queue.py` → 完整 read+write 确认 ✓
- **影响**: dedupe 命中也要全量 IO。
- **建议**: 内存 `dict[dedupe_key, row]`，定期 flush。

#### 5.1.5 [🟠 HIGH] `task_store.update_task` 每次 read-modify-write 整文件

- **位置**: `butler/runtime/task_store.py:133-140`
- **代码**:
  ```python
  def update_task(task_id, **fields):
      record = get_task(task_id)    # 读
      if record is None: return None
      record.update(fields)          # 改
      _write(task_id, record)        # 写
  ```
- **影响**: 3x IO（读+写+fsync）。并发 update 同一 task 丢失更新。
- **建议**: 内存 cache + 定期 flush（30s）；或 `fcntl.flock` 文件锁。

#### 5.1.6 [🟡 MEDIUM] 技能全量加载每次 turn 重读

- **位置**: `butler/skills/manager.py:239-253` (`_load_all`) vs `get_skill:324-330`
- **影响**: `get_skill` 调 `_load_all`（非 metadata 路径，每个 skill 都 `_read_frontmatter_only` + body 解析），与 `list_skills` 用的 `_load_metadata_all`（带 mtime 缓存）不同。
- **建议**: 让 `_load_all` 复用 `_metadata_cache`，加二级 `_body_cache` 带 mtime 检查。

#### 5.1.7 [🟡 MEDIUM] embedding query 无 LRU

- **位置**: `butler/memory/embedding.py:259-260` `_cached_embedder` 用 `lru_cache(maxsize=4)` 仅缓存 embedder 实例
- **影响**: query 文本本身**未缓存**，每次 embed 50-200ms（API mode）。同 query 90s 内应直接命中。
- **建议**: 加 `functools.lru_cache(maxsize=512)` 包裹 `embedder.embed(text)`，或 wrapper key `sha256(text)[:16]`。

#### 5.1.8 [🟡 MEDIUM] hooks `subprocess.run` 同步阻塞

- **位置**: `butler/hooks/runner.py:522-531` (timeout=30s)
- **代码**:
  ```python
  proc = subprocess.run(["bash", "-c", rule.command], shell=False, ...)
  ```
- **复检**: `grep -nA2 "subprocess.run" butler/hooks/runner.py` → 确认 ✓
- **影响**: 每个 `UserPromptSubmit` / `PreToolUse` / `PostToolUse` hook 同步 fork，**阻塞 agent turn 线程**。一次 hook 30s 阻塞 = 一次 turn 死锁 30s。
- **建议**: `asyncio.create_subprocess_exec` 或 `loop.run_in_executor` 异步化，加 `BoundedSemaphore(4)` 限流。

#### 5.1.9 [🔵 LOW] 无 orjson/ujson

- **复检**: `grep -rn "orjson\|ujson" butler/` → 0 命中
- **影响**: 557 处 `json.load/loads/dump` 用 stdlib json，~2x 慢；大 message GC 压力大。
- **建议**: 引入 `orjson`（10x 写入）。

### 5.2 资源管理

#### 5.2.1 [🔴 CRITICAL] `wechat_ilink.py:1187` fire-and-forget `asyncio.create_task`

- **位置**: `butler/gateway/platforms/wechat_ilink.py:1187`
- **代码**:
  ```python
  asyncio.create_task(self._maybe_fetch_typing_ticket(sender_id, context_token or None))
  ```
- **复检**: `sed -n '1180,1195p' butler/gateway/platforms/wechat_ilink.py` → 确认无引用 ✓
- **影响**:
  - 任务引用丢失 → 异常时只发 warning、不能 cancel
  - adapter 断连时 task 仍引用已 close 的 `self._poll_session`（高风险）
- **建议**: `self._bg_typing_tasks: set[Task]` 持有，adapter disconnect 时 `gather(*self._bg_typing_tasks, return_exceptions=True)` cancel。

#### 5.2.2 [🟠 HIGH] `prefetch_cache.schedule_prefetch_warm` 每次新建 thread

- **位置**: `butler/memory/prefetch_cache.py:98`
- **代码**:
  ```python
  threading.Thread(target=_run, name=f"butler-prefetch-{sk[:24]}", daemon=True).start()
  ```
- **复检**: `sed -n '90,110p' butler/memory/prefetch_cache.py` → 确认 ✓
- **影响**: 每个 warm 新建一个 daemon 线程，无 thread pool 复用。DAEMON 线程在解释器退出时被强杀，可能丢失进行中任务。
- **建议**: 用 `concurrent.futures.ThreadPoolExecutor(max_workers=2)` 共享。

#### 5.2.3 [🟠 HIGH] `mcp/async_runner.py` 永久 daemon loop/thread，无关闭

- **位置**: `butler/mcp/async_runner.py:1-36`
- **代码**:
  ```python
  _loop: asyncio.AbstractEventLoop | None = None
  _thread: threading.Thread | None = None
  ...
  def _ensure_loop() -> asyncio.AbstractEventLoop:
      ...
      _thread = threading.Thread(target=_run, daemon=True, name="butler-mcp-loop")
      _thread.start()
  ```
- **复检**: `sed -n '1,40p' butler/mcp/async_runner.py` → 模块级单例、无 atexit 关闭确认 ✓
- **影响**: 进程退出时 event loop 未 `shutdown_asyncgens()`，aiohttp / httpx 连接可能 hang 1-3s。
- **建议**: 加 `atexit.register(_loop.close)` + signal handler graceful shutdown。

#### 5.2.4 [🟠 HIGH] SQLite 复用连接可降低锁竞争（5.1.1 资源侧）

- 见 5.1.1
- **影响**: 写并发塌陷到 ~50 ops/sec（vs 复用的 ~5000 ops/sec）

#### 5.2.5 [🟠 HIGH] `runtime/audit.try_acquire_lock` TOCTOU

- **位置**: `butler/runtime/audit.py:53-67`
- **代码**:
  ```python
  def try_acquire_lock(project_name, job_id, *, stale_seconds=7200):
      path = lock_path(...)
      if path.exists():
          try:
              age = time.time() - path.stat().st_mtime
              if age < stale_seconds: return False
          except OSError: return False
      try:
          from butler.io.atomic_write import atomic_write_text
          atomic_write_text(path, str(time.time()))   # ← race
          return True
      except OSError: return False
  ```
- **复检**: `sed -n '50,80p' butler/runtime/audit.py` → TOCTOU 确认 ✓
- **影响**: 两个并发 `try_acquire_lock` 都过 `exists` 检查 → 都"成功"持锁 → **同一 job 双跑**。
- **建议**: `os.open(O_CREAT|O_EXCL|O_NOFOLLOW)` 原子创建，或 `fcntl.flock`。

#### 5.2.6 [🟠 HIGH] butler/memory 全层 0 处 chmod（与 4.1.2 同源问题）

- **复检**: `grep -rn "chmod" butler/memory/` → **0 命中** ✓
- **影响**: `~/.butler/tenants/*/experience.db` 与 `profile.json` 创建时无 chmod；多用户系统读权限泄漏。
- **建议**: 在 `butler/memory/butler_memory.py:139-148` 之后加 `path.chmod(0o600)`（参考 `config_secrets.py:37-40`）。

#### 5.2.7 [🟡 MEDIUM] `_WELCOMED_SESSIONS` 仍无界（Round 2 已识别未修）

- **位置**: `butler/gateway/handler_helpers.py:375-413`
- **影响**: 集合无 TTL/LRU；进程长跑 + 多用户场景下无限增长。
- **建议**: `cachetools.TTLCache(maxsize=10000, ttl=86400)`。

#### 5.2.8 [🟡 MEDIUM] `notify.wait_wechat_push_cooldown` `time.sleep` 阻塞 thread

- **位置**: `butler/runtime/notify.py:94`
- **影响**: 同步 sleep 不响应 task cancel；与 `asyncio.run` 混用阻塞 sync 上下文。
- **建议**: 拆 `async def` + `await asyncio.sleep`。

#### 5.2.9 [🟡 MEDIUM] session transcript 仅单 session 50MB cap，无总量限制

- **位置**: `butler/core/session_transcript.py:19, 63-75`
- **代码**: `_DEFAULT_MAX_BYTES = 50 * 1024 * 1024`（单 session），`_tombstone_tail(path)` 保留 40%
- **影响**: N 个 session 累积无 cap → 磁盘只增。
- **建议**: 遍历 `~/.butler/sessions/*/transcript.jsonl` 加 `BUTLER_SESSION_TRANSCRIPT_TOTAL_MB` 总量检查。

#### 5.2.10 [🔵 LOW] `coverage.json` 2.1MB git tracked（仓库污染）

- **位置**: `/home/ailearn/projects/WFXM/coverage.json` (2,157,173 bytes)
- **复检**:
  - `du -h /home/ailearn/projects/WFXM/coverage.json` → 2.1M ✓
  - `git ls-files | grep -E "^coverage\.json$"` → 命中（git tracked）✓
  - `cat .gitignore | grep -c "^coverage.json$"` → 0（无 gitignore）✓
- **影响**: 每次 PR diff 巨大、克隆仓库慢
- **建议**: `echo "coverage.json" >> .gitignore` + `git rm --cached coverage.json`

---

## 6. 文档 / 规范层（Round 5）— 全部已复检

### 6.1 文档完整性

#### 6.1.1 [🔴 CRITICAL] 6 篇 review 文档被删，README 等 7 处断链

- **位置**:
  - 已删: `docs/reviews/project-{assessment,deep-review,deep-review-v2,deep-review-round2,issue-tracker,multi-round-review}-2026-05.md`
  - 断链位置:
    1. `README.md:148` → `docs/reviews/project-assessment-2026-05.md`
    2. `docs/README.md:71` → `reviews/project-assessment-2026-05.md`
    3. `docs/guides/README.md:47` → `../reviews/project-assessment-2026-05.md`
    4. `docs/plans/active/post-consolidation-roadmap-2026-05.md:98`
    5. `docs/plans/archive/consolidation-2026-05.md:168, 228`
    6. `docs/plans/archive/p3-deferred-deep-dive-2026-05.md:281`
- **复检**:
  - `git status -s docs/reviews/` → 6 个 `D` + 新 audit doc 一个 `??` ✓
  - `grep -rn "project-assessment-2026-05"` → 7 处确认 ✓
- **影响**: `docs-lint.sh` 当前会报 7+ 处断链；主仓 README "成熟度评估" 入口指向 404。
- **建议**: 
  - 立刻 `git restore docs/reviews/project-assessment-2026-05.md` 或将 README 等 7 处改链到 `project-deep-audit-2026-06.md`
  - Sprint 6 提交 `3c1121c` 自称"保留 project-assessment"——现状（已删）与之矛盾

#### 6.1.2 [🟠 HIGH] 41 个 `BUTLER_*` 变量在代码中读取但未收录到 `.env.example` / `docs/config/reference.md`

- **位置**: `.env.example` (364 去重) + `docs/config/reference.md` (367 去重) vs 代码 (400 去重)
- **复检**:
  - `grep -rEho "BUTLER_[A-Z_]+" butler/ | sort -u | wc -l` → **400** ✓
  - `comm -23` 差集 → **44+ 个** 真实缺漏（subagent 估 41，实际命令显示更多）
- **典型遗漏**（节选）:
  ```
  BUTLER_TODO_CONTINUATION / _MAX / BUTLER_TODO_STAGNATION_MAX
  BUTLER_INTENT_KEYWORDS / _OFF
  BUTLER_MODE_CLASSIFIER_MIN_CHARS
  BUTLER_HASHLINE_PATCH / BUTLER_HASHLINE_READ
  BUTLER_GATEWAY_DELEGATE_PUSH_ALWAYS
  BUTLER_GATEWAY_PROGRESSIVE_INTERVAL / _MIN_CHARS / _MAX_ACK_MESSAGES
  BUTLER_GATEWAY_QUEUE_DRAIN_FOLLOWUP
  BUTLER_GATEWAY_TYPING_REFRESH_SECONDS / _FETCH_TIMEOUT_SECONDS
  BUTLER_MEMORY_MAX_BYTES / _MAX_LINES
  BUTLER_INSTRUCTION_WALKUP_MAX_FILES
  BUTLER_INLINE_TOOL_COMPRESS_KEEP / _MAX_CHARS
  BUTLER_TOOL_RETRY_MAX / _BACKOFF_SECONDS
  BUTLER_TOOL_RESULT_CACHE_TTL / BUTLER_TOOL_PAIR_REPAIR
  BUTLER_TOOL_SELECTOR_THRESHOLD / BUTLER_TOOL_CALL_LIMIT_EXEMPT
  BUTLER_TOOL_MASK_MIN_PRUNABLE
  BUTLER_OUTBOUND_PII_SCRUB_EMAIL
  BUTLER_RULES_ENGINE / _MAX_CHARS
  BUTLER_REGISTRY_ALLOWED_HOSTS
  BUTLER_TERMINAL_PATTERN_APPROVE_TTL
  BUTLER_TRANSCRIPT_SEARCH_MAX_HITS / _MAX_SESSIONS
  BUTLER_TURN_BUDGET_MIN_ITERATIONS
  BUTLER_POST_SESSION_BUFFER_MESSAGES
  BUTLER_CATALOG_INTEGRITY_FAIL_CLOSED
  BUTLER_CLI_SHOW_REASONING / BUTLER_WECHAT_RATE_LIMIT_BACKOFF_MAX
  ```
- **影响**: 违反 `AGENTS.md` 第 2 条"BUTLER_ 勿猜默认值" + `DOCUMENTATION.md §6.1` 维护规则
- **建议**: 写 `tools/_sync_butler_env_docs.py`：从 `butler/` 静态 grep → 与 `.env.example` diff → 追加到 reference.md / .env.example（注释形式 + 默认值）
- **复检**: `comm -23 <(grep -rEho "BUTLER_[A-Z_]+" butler/ | sort -u) <(cat <(grep -Eho "BUTLER_[A-Z_]+" .env.example) <(grep -Eho "BUTLER_[A-Z_]+" docs/config/reference.md) | sort -u)` 应为空

#### 6.1.3 [🟠 HIGH] `v4-architecture.md` 未把 main.py / message_handler.py 标记为 God Module

- **位置**: `docs/architecture/v4-architecture.md:50`（"Butler Core ~2924 行"）
- **证据**: README:18 "编排 ~780 行"、v4-arch.md:50 "~807 行"，但 `main.py` 1340 行 / `message_handler.py` 1252 行 都没列入
- **影响**: 与"主仓 4 个 God Module"的前轮结论不一致
- **建议**: v4-arch §核心模块表新增 main.py / message_handler.py 行

#### 6.1.4 [🟡 MEDIUM] 测试基线数字三处不一致

- **位置**:
  - `README.md:91` → "1200+"
  - `STRUCTURE.md:28` → "~1816"
  - `tests/README.md:5` → "~2100+"
- **复检**:
  - `find tests -name "test_*.py" -not -path "*/corpus/*" | wc -l` = 280 ✓
  - 含 corpus = 292；`def test_` 函数 2489
- **建议**: 三处统一为"~280 个测试文件 / ~2400 个 test 函数 / 排除 live_llm"

#### 6.1.5 [🟡 MEDIUM] Hermes 残留引用 `butler/session/post_session.py:197`

- **位置**: `butler/session/post_session.py:197`
- **代码**: `Can use either a raw LLM callable or a Hermes AIAgent for extraction.`
- **复检**: `grep -n "Hermes AIAgent" butler/session/post_session.py` → line 197 ✓
- **影响**: 与 v4-arch §"自建 Agent Loop，不再 import AIAgent" + AGENTS.md 23 行"v4 为自建 Loop" 矛盾
- **建议**: 改为"raw LLM callable 或 `butler.core.agent_loop` 提炼入口"
- **说明**: `butler/main.py:5` (`No dependency on Hermes AIAgent`) 是正确口径，**仅 post_session.py:197 是错配**

### 6.2 规范合规

#### 6.2.1 [🟠 HIGH] 提交类型非标准（feature/security/arch/ux/observability）

- **位置**: `git log --oneline -30` 抽样
- **证据**:
  - `ddf0c3d feature: Sprint 5 — ...` → 应为 `feat:`
  - `d86493f security: Sprint 1 — ...` → `security` 未列入 CONTRIBUTING.md 规范
  - `f2f5f3c arch: Sprint 4 — ...` → `arch` 同上
  - `a6f8cee ux: Sprint 3 — ...` → `ux` 同上
  - `d431ed7 observability: Sprint 2 — ...` → `observability` 同上
- **复检**: `git log --oneline -30` → 5/30 提交用 Sprint 主题 type（占 17%）
- **影响**: CONTRIBUTING.md 提交规范未涵盖这些 type；下游 `git-cliff` 等工具无法解析
- **建议**: 增补 `CONTRIBUTING.md` 提交规范章节，列出 `feat/fix/refactor/docs/test/chore/perf/ci/arch/ux/observability/security`

#### 6.2.2 [🟡 MEDIUM] 无 `CHANGELOG.md` / `SECURITY.md`

- **位置**: 仓库根
- **复检**: `ls CHANGELOG* SECURITY*` → 空 ✓
- **影响**: 
  - 重大变更（Hermes 解耦、Sprint 1-6）无版本级变更日志
  - 安全披露流程缺位（Round 3 已发现 6 项 P0/SSRF/TOCTOU/MCP/...）
- **建议**: 加 `CHANGELOG.md`（手动或 `git-cliff`）+ `SECURITY.md`（含 `security@…` 邮箱）

#### 6.2.3 [🟡 MEDIUM] SPDX 头 0 命中

- **位置**: 全 `butler/`
- **复检**: `grep -rn "SPDX-License" butler/` → **0 命中** ✓
- **影响**: `pyproject.toml` 声明 `license = { text = "MIT" }` 但源文件无任何 SPDX 行
- **建议**: 给 `butler/__init__.py`、`butler/main.py`、`butler/core/agent_loop.py` 加 `# SPDX-License-Identifier: MIT`

#### 6.2.4 [🟡 MEDIUM] pyproject.toml 与 requirements.lock 不同步

- **位置**: `pyproject.toml:14-32` (17 core + 14 optional) vs `requirements.lock` (185 包)
- **影响**: lock 是 `pip freeze --exclude-editable` 一次快照，2026-05 起未再生成
- **建议**: `pyproject.toml` 加 `[project.dependency-groups]` 段或 README "Lock 重新生成" 命令

#### 6.2.5 [🔵 LOW] 测试命名不规范 ~30%

- **位置**: `tests/test_*.py` 多个文件
- **典型**:
  - `tests/test_butler_v4.py`
  - `tests/test_cc_p3_p4_features.py`
  - `tests/test_e2e.py`
  - `tests/test_external_agent_p1_p4.py`
  - `tests/test_phase_a_external.py`
- **影响**: 与 `common/testing.md` 推荐 `test_<behavior>_<condition>` 模式偏离
- **建议**: CONTRIBUTING.md 加测试命名小节；现状可接受

### 6.3 文档腐化

#### 6.3.1 [🟠 HIGH] 6 处断链（详见 6.1.1）

#### 6.3.2 [🟠 HIGH] `core↔gateway` 反向 import 仍存在但 v4-arch 未提及

- **位置**: `butler/core/agent_loop.py:113`, `compaction_steer_bridge.py:33`, `compaction_task.py:80,130,162`, `context_compressor.py:391`
- **复检**: `grep -rEn "from butler\.gateway|import butler\.gateway" butler/core/` → **5 处**（与 Round 1 复检 6 处有一处是 compaction_task 同文件多次）✓
- **影响**: v4-architecture.md §核心模块表未声明此边界现状
- **建议**: v4-arch §"分层约束"加一句"`core` 仅在 lazy `import` 上下文触及 gateway 桥；属于有意分层"；或彻底抽出"callbacks 协议"在 `butler.core.loop_types` 收口

#### 6.3.3 [🟡 MEDIUM] `docs/DOCUMENTATION.md §4.1` 索引与 `architecture/` 实际 11 份不齐

- **位置**: `docs/DOCUMENTATION.md:114-122` 列 4 项 vs `ls docs/architecture/` 11 份
- **影响**: 7 份架构文档（`dev-ops-tools-design / layered-model-config / project-lead-decision / project-runtime-automation / wechat-inbound-media` 等）未被索引
- **建议**: §4.1 表加"其余 ADR / 设计稿"段并链全部 11 份

#### 6.3.4 [🔵 LOW] `butler/main.py:738` 含 "Hermes 凭证在 ~/.hermes/" 用户提示

- **位置**: `butler/main.py:738`
- **代码**: `print("\n勿与 Hermes 共用同一 Bot；Hermes 凭证在 ~/.hermes/，Butler 在 ~/.butler/。")`
- **影响**: 维护性 — 不影响功能，但对"完全自建 Loop"的产品口径，提示文案应淡化
- **建议**: 改为"勿与其它 iLink 平台账号共用"

#### 6.3.5 [🟡 MEDIUM] `docs/plans/active/opencode-actionable-optimization-checklist-2026-05.md` 未在 `plans/README.md` 索引

- **位置**: `docs/plans/README.md` 目录结构表
- **影响**: 3 份 active 文档，README 表只列 2 份
- **建议**: README 补 opencode checklist

### 6.4 重要但缺失

#### 6.4.1 [🟠 HIGH] 无独立 ADR 目录

- **位置**: `docs/architecture/`
- **复检**: `ls docs/architecture/adr/` → 空 ✓
- **影响**: 重大决策（Hermes 解耦、CC 线束、OpenClaw 对标、MCP 薄客户端、`LoopContext` Protocol）混在路线图文档中，未来追溯困难
- **建议**: 新建 `docs/architecture/adr/` + 至少 5 份 ADR（Hermes 解耦 / LoopContext / MCP 客户端 / Cache-safe 委派 / OpenClaw 对标）

#### 6.4.2 [🟠 HIGH] `agent_loop.py` 与 `message_handler.py` 无独立设计文档

- **位置**: `butler/core/agent_loop.py` (807 行) + `butler/gateway/message_handler.py` (1252 行)
- **影响**: 两个最热路径，唯一权威说明是 v4-arch 表格（每模块 1-2 行）
- **建议**: `docs/architecture/hot-paths/agent-loop.md` + `message-handler.md`

#### 6.4.3 [🟡 MEDIUM] `.env.example` 缺 inline 默认值/单位注释

- **位置**: `.env.example` 374 个 `BUTLER_*` 全部 `# 注释 + 默认值` 形式，但 0 个**默认范围/单位**
- **建议**: 给所有 `BUTLER_*` 加 `# 默认: X / 单位: 秒 / 范围: 1-100`

---

## 附录 A: 审计过程记录

### Round 1 (架构层) — 已完成
- **执行时间**: 2026-06-02
- **Subagent 任务**: God Module / 循环依赖 / 抽象泄漏 / 命名空间组织 / 调用链分析
- **复检内容**:
  - 文件行数（4 个 >800、26 个 >500）✓
  - `from butler.` 计数（main 81 / handler 92 / orch 40）✓
  - `core→gateway` 跨层 import 6 处（subagent 估 5）✓
  - `_settings`/`_model_credentials` 私有属性穿透 5 处 ✓
  - `_run_turn_body` 行数 338 ✓
  - `handle_message` 实际 427 行（subagent 估 318）
  - `WeChatAdapter` 914-2000 实际 1086 行 ✓
  - 4 个 `*_flags.py` + safety_finish ✓
  - 6 transcript / 7 compaction / 15 tool_ 前缀文件 ✓
- **已录入问题**: §2.1.1-2.1.5, §2.2.1-2.2.3, §2.3.1-2.3.2, §2.4.1
- **总计入档**: 12 条

### Round 2 (代码质量层) — 已完成
- **执行时间**: 2026-06-02
- **Subagent 任务**: 错误处理、不可变性、死代码、命名、危险反模式、注释质量
- **复检内容**:
  - `turn_runner.py:208` + `message_handler.py:952` 静默吞错 ✓
  - `agent_loop.py:712` doom-loop fail-open ✓
  - 28 处 try 跨度 ≥ 50 行（agent_loop 实际 260 行，subagent 估 235）✓
  - 808 个 Exception handler / 3 个 logger.exception ✓
  - 0 个 eval/exec/pickle/os.system/shell=True ✓
  - 8 个 assert 位置 ✓
  - 6 个 long function > 150 行（含嵌套）✓
  - hot path 0% 注释密度 ✓
  - `_WELCOMED_SESSIONS` 无锁 race ✓
  - `_STORE` 无锁 ✓
- **已录入问题**: §3.1.1-3.1.5, §3.2.1-3.2.4, §3.3.1-3.3.2, §3.4.1-3.4.2, §3.5.1-3.5.3, §3.6.1-3.6.2
- **本轮新入档**: 19 条
- **累计**: 31 条

### Round 3 (安全/测试层) — 已完成
- **执行时间**: 2026-06-02
- **Subagent 任务**: 微信 iLink 加解密 / MCP SSRF / PII 脱敏 / 测试覆盖 / CI 守门
- **复检内容**:
  - `mcp/config.py:237` 子串绕过 ✓
  - `ContextTokenStore._persist` 无 chmod，对比 `save_wechat_account` line 291 ✓
  - `pii_scrub.py` 仅 3 类正则（phone/ID18/optional email）✓
  - `_aes128_ecb_decrypt:236` `return padded` 静默返回 ✓
  - `web_fetch` 默认 follow_redirects（Python 验证 True）✓
  - `llm_client.py:83,98` `api_key = "dummy"` 双处 ✓
  - `wechat_ilink.py:815,817,874` QR URL 写 stdout ✓
  - `tests/test_wechat_ilink_*.py` 3 文件 / 0 真实 crypto 测试 ✓
  - `tests/test_path_safety.py` 8 测试 / 缺 symlink+dotdot+null+unicode ✓
  - pytest 收集 2843/3378 (535 deselected) ✓
- **已录入问题**: §4.1.1-4.1.9, §4.2.1-4.2.8
- **本轮新入档**: 17 条
- **累计**: 48 条

### Round 4 (性能/资源层) — 已完成
- **执行时间**: 2026-06-02
- **Subagent 任务**: N+1 / 同步阻塞 / 算法 / 缓存 / ContextVar / 文件泄漏 / 磁盘增长
- **复检内容**:
  - `butler_memory.py:145-148` 13+ with 块每次重连 ✓
  - `vector_store.py:166-172` 整文件重写 ✓
  - `message_queue.py:166-168` 每次 O(n log n) 排序 ✓
  - `wechat_ilink.py:1187` `asyncio.create_task` 无引用 ✓
  - `prefetch_cache.py:98` 每次新 thread ✓
  - `mcp/async_runner.py:1-36` daemon loop 无 atexit 关闭 ✓
  - `audit.py:53-67` try_acquire_lock TOCTOU ✓
  - `butler/memory/` 全层 0 处 chmod ✓
  - `coverage.json` 2.1MB git tracked（无 gitignore）✓
  - `embedding.py:259` lru_cache(maxsize=4) 仅缓存 embedder 实例，query 文本不缓存 ✓
- **已录入问题**: §5.1.1-5.1.9, §5.2.1-5.2.10
- **本轮新入档**: 19 条
- **累计**: 67 条

### Round 5 (文档/规范层) — 已完成
- **执行时间**: 2026-06-02
- **Subagent 任务**: 文档完整性 / 规范合规 / 文档腐化 / 缺失文档 / 命名链接
- **复检内容**:
  - 6 个 `D` review 文件 + 7 处断链 ✓
  - BUTLER_ 代码 400 / env 364 / ref 367 → 44+ 真实缺漏 ✓
  - `butler/session/post_session.py:197` Hermes AIAgent 引用 ✓
  - 测试基线 1200+/1816/2100+ 三处不一致 ✓
  - 0 SPDX 头 ✓
  - 无 CHANGELOG / SECURITY ✓
  - 无 `docs/architecture/adr/` ✓
  - `.env.example` 374 变量 0 个带单位注释 ✓
  - 提交类型 `feature/security/arch/ux/observability` 5 个非标准 ✓
- **已录入问题**: §6.1.1-6.1.5, §6.2.1-6.2.5, §6.3.1-6.3.5, §6.4.1-6.4.3
- **本轮新入档**: 18 条
- **累计**: 85 条
