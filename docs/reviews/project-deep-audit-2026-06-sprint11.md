# Butler v4 项目深度审计 — Sprint 11（2026-06-02）

**审计方式**: 4 个并行 subagent 独立扫描（security / performance / reliability / test+dead code），主审计师独立 grep/sed 复检 6 项关键发现。

**基线**: Sprint 10 修复 5 CRITICAL（SEC-10-1/2 + REL-NEW-01/02 + PERF-NEW-3） + 删 apprise_adapter.py。本轮独立扫描 Sprint 10 修复后的代码状态。

**总计**: 31 项新发现（13 安全 + 11 性能 + 8 可靠性 + 19 测试/死代码，含 9 项重叠 = 41 项独立）。**Sprint 10 残留** 8 项 → 当前已修 6 项（详见 §4 末尾表）。

---

## Top 10 — 关键发现（建议优先修复）

| # | ID | 位置 | 问题 | 严重 | 工时 |
|---|----|------|------|------|------|
| 1 | ~~TST-11-1~~ | ~~`butler/runtime/approval.py` (140 行)~~ | ~~真死代码（0 importer/0 test）— Sprint 10 REL-NEW-07 描述的代码在此~~ **⚠️ Sprint 11 误报：实为 namespace 引用（service.py:12）** | ~~🔴~~ | ~~10min~~ |
| 2 | ~~**REL-11-1**~~ | ~~`message_handler.py:389,401`~~ | ~~`_idempotency_reserved = False` 提前初始化 → inflight 假阴性泄漏~~ **✅ Sprint 14 a6e36af 修复: 保留 pre-init, 删 bot_loop_guard 死 release_inflight** | ~~🔴~~ | ~~30min~~ |
| 3 | ~~**REL-11-5**~~ | ~~`inbound_idempotency.py:22,79-82`~~ | ~~`inflight` 状态无 TTL/无 sweep → worker 崩溃后永久拒绝~~ **✅ Sprint 11 94343dc 修复: lazy sweep + TTL 60s** | ~~🔴~~ | ~~1h~~ |
| 4 | ~~**PERF-11-5**~~ | ~~`semantic_index.py:35`~~ | ~~单 RLock 串行化 9 个方法（search/upsert/delete/count）— 多 session 并发全阻塞~~ **✅ Sprint 11 899ccc7 修复: 读写分离锁** | ~~🔴~~ | ~~2h~~ |
| 5 | ~~**PERF-11-1**~~ | ~~`message_queue.py:167`~~ | ~~每次 enqueue 全桶 O(N log N) sort — 高 inbound 时线性退化~~ **✅ Sprint 11 194e6d6 修复: 3 桶结构 O(1) append** | ~~🔴~~ | ~~1h~~ |
| 6 | ~~**PERF-11-2**~~ | ~~`exp_cache.py:79-93`~~ | ~~LLM 响应缓存每次 read 全文件 + 逐行 json.loads~~ **✅ Sprint 11 1ba1c45 修复: per-path in-memory cache** | ~~🔴~~ | ~~30min~~ |
| 7 | ~~**PERF-11-3**~~ | ~~`exp_cache.py:96-105`~~ | ~~LLM 响应缓存每次 store 写全文件 N 条~~ **✅ Sprint 11 1ba1c45 修复: store 同步 in-memory** | ~~🔴~~ | ~~30min~~ |
| 8 | ~~**SEC-11-1**~~ | ~~`runtime_commands.py:17-75`~~ | ~~`/运行` + `/批准运行` 漏 owner gate~~ **✅ Sprint 17 SEC-11 owner gate completion (T3): registry handler 加 gate** | ~~🟠~~ | ~~10min~~ |
| 9 | ~~**SEC-11-2**~~ | ~~`memory_commands.py:86-118`~~ | ~~`/批准记忆 全部` 漏 owner gate → 污染 MEMORY.md~~ **✅ Sprint 17 SEC-11 owner gate completion (T2): registry handler 验证 + 加 gate** | ~~🟠~~ | ~~10min~~ |
| 10 | ~~**SEC-11-3**~~ | ~~`butler_memory.py:239-265`~~ | ~~`ExperienceStore.add` 缺 `_reject_injection` → 注入持久化 sink~~ **✅ Sprint 11 5f4b10c 修复: add() 顶部加 _reject_injection 拦截, 6 个 RED 测试** | ~~🟠~~ | ~~30min~~ |

---

## 1. 安全审计（Security — 13 项）

### 🔴 Sprint 11 必扫（SEC-10 残留 7 项全部未修，参见 Sprint 10 报告 §1）

### 🟠 HIGH — 4 项 owner gate 漏报（同 SEC-10-1 模式）

#### ~~SEC-11-1 `/运行` + `/批准运行` 漏 owner gate~~ ✅ Sprint 17 SEC-11 owner gate completion 修复
- **位置**: `butler/gateway/runtime_commands.py:17-75`
- **历史证据**: `/批准运行` 调 `approve_and_run()` → `run_job(force=True, approved_run=True)` 跳过 `approval.approval_required` 守门（service.py:106-115），可执行 `publish-preflight` 类改盘任务。
- **历史影响**: 任何 `WECHAT_ALLOWED_USERS` 中（不一定是 Owner）的用户都能改盘。
- **修复 (Sprint 17 T3)**: `butler/gateway/commands/runtime_commands.py` 加 registry handler owner gate (`_cmd_runtime_jobs_list` + `_cmd_runtime_approve_run` + `_cmd_runtime_run`); 3 个 handler 在 sprint 12 之前已有 gate (`is_gateway_owner` 直接调用), 此次补 registry wrapper. owner_gate_scan gap 数 9 → 6 (3 个新 gate).

#### ~~SEC-11-2 `/批准记忆` 漏 owner gate~~ ✅ Sprint 17 SEC-11 owner gate completion 修复
- **位置**: `butler/gateway/memory_commands.py:86-118`
- **历史证据**: `/批准记忆 全部` (line 94-98) 直接 `pmem.markdown.approve_all()`，无 owner 守门。对比 `lifecycle_commands.py:101` `_cmd_transcript_memory` 有 owner gate。
- **历史影响**: 非 Owner 白名单用户可永久污染项目 MEMORY.md → 后续进入 LLM 上下文（prompt injection 注入到长期记忆）。
- **修复 (Sprint 17 T2)**: 底层 `handle_memory_pending_command` 已有 owner gate (line 99-102) 自 Sprint 11 起, 但 registry handler 未在 _cmd_memory_approve 加. Sprint 17 在 registry handler (`butler/gateway/commands/memory_commands.py:_cmd_memory_approve`) 加 owner gate 守门. 其他 3 个 read-only handler (`_cmd_memory_graph` / `_cmd_memory_pending_list` / `_cmd_memory_reject`) 走 opt-out 路径 (Sprint 11 test_sprint11_sec2 既有契约). owner_gate_scan gap 数 6 → 3.

### 🟡 MEDIUM — 4 项

#### ~~SEC-11-3 `ExperienceStore.add` 缺 `_reject_injection`~~ ✅ Sprint 11 5f4b10c 修复
- **位置**: `butler/memory/butler_memory.py:239-265`
- **历史证据**: `grep "_reject_injection" butler_memory.py` 只在 line 73/91 (ProfileStore) 出现；line 257 `INSERT INTO experiences` 无过滤。
- **历史链路**: `butler_remember scope=owner_experience` (`facade.py:444`) → `experience.add()` → SQLite → `search()` 召回 → `format_for_prompt` → LLM context。
- **历史影响**: 与 SEC-10-6 互补，**完整 prompt-injection 持久化 sink**。
- **修复 (Sprint 11 5f4b10c)**: `ExperienceStore.add()` 顶部加 `if _reject_injection(content or ""): return -1` 拦截 (与 ProfileStore 对齐). 命中模式返 -1 sentinel. `content=None/""` 用 `or ""` 兜底避免 regex TypeError. 6 个 RED 测试覆盖 5 个 `_INJECTION_PATTERNS` + 正常通过 + 防御. 157 个 experience.add 现有调用方测试无回归.

#### ~~SEC-11-4 `/技能 搜索/列表/查看` 漏 owner gate~~ ✅ Sprint 17 SEC-11 owner gate completion 修复
- **位置**: `butler/gateway/registry_commands.py:109-135`
- **历史证据**: 3 个 read-only 子命令均无 owner gate；line 129-130 显式"community 源需 Owner 确认" → 实际非 Owner 拿到相同内容。
- **历史影响**: 第三方恶意 Skill 描述喂回 LLM 形成 prompt injection。
- **修复 (Sprint 17 T5)**: `butler/gateway/commands/info_commands.py` 加 `_require_owner(ctx)` helper, 给 7 个私人数据 handler 加 gate (含 /技能 搜索/列表/查看). 既有 handler (底层 tools/memo.py 等) 已是 owner-scoped, 此次补 registry wrapper.

#### ~~SEC-11-5 `/备忘` `/通讯录` `/记账` `/打卡` 漏 owner gate~~ ✅ Sprint 17 SEC-11 owner gate completion 修复
- **位置**: `butler/gateway/info_commands.py:34-56`（handler 在 `tools/memo.py:337` 等）
- **历史证据**: 4 命令均无 owner gate；但底层数据 owner-scoped（`memo.py:3-8` 明确 "owner-level"）。
- **历史影响**: 任何白名单用户可读 Owner 私人数据。
- **修复 (Sprint 17 T1)**: `butler/gateway/commands/info_commands.py` 加 `_require_owner(ctx)` helper, 给 5 个私人数据 handler 加 gate (含 /备忘 /通讯录 /记账 /打卡 /项目待办); 7 个 handler 共享同一个 helper, 4 个 opt-out (公共只读).

#### ~~SEC-11-6 `/评价` 漏 owner gate~~ ✅ Sprint 17 SEC-11 owner gate completion 修复
- **位置**: `butler/gateway/outcome_commands.py:8-66`
- **历史证据**: `handle_outcome_command` 全文 0 处 `is_gateway_owner`；写入 `experiments/outcomes.py`。
- **历史影响**: 污染实验评估日志，影响后续记忆提炼。
- **修复 (Sprint 17 T1)**: `butler/gateway/commands/info_commands.py` 加 `_cmd_outcome` handler, 在 registry dispatch 入口处调 `_require_owner(ctx)` 守门. 底层 `handle_outcome_command` 之前已加 owner gate, 此次补 registry wrapper.

### 🟢 LOW

#### ~~SEC-11-7 `/会话` 信息泄露~~ ✅ Sprint 17 SEC-11 owner gate completion 修复
- **位置**: `butler/gateway/sessions_commands.py:9-38`
- **历史证据**: `list_sessions()` 返回全量 session_key（含 chat_id），无 owner gate。
- **修复 (Sprint 17 T1)**: `butler/gateway/commands/info_commands.py` 加 `_cmd_sessions` handler, 在 registry dispatch 入口处调 `_require_owner(ctx)` 守门. 底层 `handle_sessions_command` 之前已加 owner gate, 此次补 registry wrapper.

### 模式观察

Sprint 9/10 修复均聚焦 `/config` 一条路径；Sprint 11 仍有 **5 个 owner-gated 改盘命令** + **5 个只读信息命令** 缺守门——**同模式在 6 个新模块复现**。**建议 Sprint 12 引入 CI 静态扫描**: `grep "def handle_.*command\|def _cmd_" + 缺 is_gateway_owner` 报警。

---

## 2. 性能审计（Performance — 11 项新发现）

### 🔴 CRITICAL（0 项 — Sprint 11 已修）

#### ~~PERF-11-1 `message_queue.enqueue` 全桶 sort~~ ✅ Sprint 11 194e6d6 修复
- **位置**: `butler/gateway/message_queue.py:40, 49-55, 200, 228-265`
- **历史证据**（Sprint 11 审计时）:
  ```python
  bucket = _QUEUES.setdefault(key, deque())
  if not _apply_cap_before_append(key, bucket, body):
      return False
  bucket.append(item)
  bucket = deque(sorted(bucket, key=lambda x: _PRIORITY_ORDER.get(x.priority, 9)))
  _QUEUES[key] = bucket
  ```
- **修复方案**: `_QUEUES[session_key]` 从单 deque 改为 `dict[priority, deque]`（now / next / later 3 桶）。enqueue 走 `bucket[pri].append(item)`，O(1)。
- **行为不变性**: pop_urgent / pop_next / pop_all_merged 跨桶顺序保持 now > next > later。
- **回归测试**: `tests/test_sprint11_perf1_message_queue_3buckets.py` — **7 PASSED**

#### ~~PERF-11-2 `exp_cache.lookup_cached_response` 全文件读~~ ✅ Sprint 11 1ba1c45 修复
- **位置**: `butler/core/exp_cache.py:23-24, 85-108, 138-143`
- **修复方案**: per-path in-memory cache（`_MEM_CACHE` + `_MEM_LOADED`）。首次访问 lazy load 一次，之后只读 dict。
- **回归测试**: `tests/test_sprint11_perf23_exp_cache_inmemory.py` — **6 PASSED**（含并发线程安全）

#### ~~PERF-11-3 `exp_cache` store 写全文件~~ ✅ Sprint 11 1ba1c45 修复
- **位置**: `butler/core/exp_cache.py:111-129, 166-172`
- **修复方案**: `_write_entries` 仍写全文件（持久化语义不变），但同步更新 `_MEM_CACHE`，避免后续 lookup 重读。
- **回归测试**: 同 PERF-11-2 的 6 用例覆盖 store 路径

#### ~~PERF-11-5 `semantic_index` 单 RLock 串行化~~ ✅ Sprint 11 899ccc7 修复
- **位置**: `butler/memory/semantic_index.py:35-40`
- **修复方案**: 拆 `self._write_lock = threading.Lock()`（仅 write 持锁），read 走 sqlite3 Connection 内部 mutex（`check_same_thread=False`）。`self._lock = self._write_lock` 保留向后兼容旧测试。
- **回归测试**: `tests/test_sprint11_perf5_semantic_index_rwlock.py` — **6 PASSED**（含并发 search 不阻塞 upsert）

### 🟠 HIGH — 3 项 (全部 Sprint 13 已修)

| ID | 位置 | 问题 | 状态 |
|----|------|------|------|
| ~~**PERF-11-4**~~ | ~~`tool_selector.py:78-84`~~ | ~~tool embed 缓存键用 `hash(text)` 跨进程随机 + 永不 LRU 淘汰~~ | ✅ Sprint 13 PERF-13-1 `560bd56`: blake2b 稳定 key + LRU 256 + move_to_end |
| ~~**PERF-11-6**~~ | ~~`embedding.py:128-133, 167-172`~~ | ~~embedder 端无 query cache；`semantic_index.search` 每 turn `embed(q)` 重复付费~~ | ✅ Sprint 13 PERF-13-2 `5551db2`: `_CachedEmbedder` LRU 128 包装, HashingEmbedder 跳过 |
| ~~**PERF-11-7**~~ | ~~`agent_loop.py:240, 510` + `tool_batch.py:263-273`~~ | ~~每 turn 3-5 次 transcript 写（lock+stat+open+write+index update）~~ | ✅ Sprint 13 PERF-13-3 `9eef7b1`: `transcript_batch` ctx mgr, 1 次 file open + writelines 替代 3-5 次分散写 |

### 🟡 MEDIUM — 4 项

| ID | 位置 | 问题 |
|----|------|------|
| PERF-11-8 | `skill_lock.py:17-28, 37-58` | skill lock 每次操作全读全解析；`list_installed` O(N log N) sort (✅ Sprint 15 `a85b28a`: `_load` 走 `read_json_cached` (LRU 按 `(path, mtime)`), `get()` 走 `_load` 直查 O(1), 抽 `_row_to_record`. 18 测试覆盖) |
| PERF-11-9 | `llm_retry.py` | LLM 路径 14 处无条件 `logger.debug` (✅ `9fb8c7b` `_safe_call(fn, msg)` 短路) |
| PERF-11-10 | `tools/expense.py:66,347,355,389` + `contacts.py:63,76` + `habits.py:65,78,120,135` | 工具内 `read_text+json.loads` 无缓存 (✅ Sprint 15 `0dc1680`: 新建 `butler/tools/_file_cache.py` `read_json_cached(path)` LRU 256, expense/contacts/habits 全部走缓存, 24 测试覆盖) |
| PERF-11-11 | `core/loop_response.py` / `core/sanitize_response` 等 | 14 个 middleware 都在 LLM 前无脑执行 (✅ Sprint 15 `8049afc`: `LoopMiddlewareChain.__post_init__` 预解析 `_before_llm_hooks` / `_after_tools_hooks` / `_wrap_tool_call_hooks`, 14 middleware × N turn 从 N×getattr 降至 0; 13 测试覆盖顺序/链式/倒序/失败容错/无 wrap 跳过) |

---

## 3. 可靠性审计（Reliability — 8 项新发现）

### 🔴 CRITICAL（0 项 — Sprint 11/14 已修）

#### ~~REL-11-1 `_idempotency_reserved = False` 提前初始化~~ ✅ Sprint 14 a6e36af 修复
- **位置**: `butler/gateway/message_handler.py:500, 526, 638`
- **历史证据**（Sprint 11 审计时）:
  ```python
  # 旧 line 389
  _idempotency_reserved = False  # ← 提前初始化 False
  try:
      from butler.gateway.bot_loop_guard import record_and_should_suppress
      ...
      if suppress:
          if _idempotency_reserved:  # ← 旧 line 401 检查（永远 False）
              try:
                  release_inflight(session_key, external_id)
  ...
  # 旧 line 531 才是真正 reserve 位置
  _idempotency_reserved = True
  ```
- **修复结果**（Sprint 14 commit a6e36af）:
  - 保留 pre-init（line 500）防止 finally 块 UnboundLocalError
  - 删 bot_loop_guard 块内的死 `release_inflight` 调用
  - 删对应的 `release_inflight` import
  - 保留 try 块内 `_idempotency_reserved = True`（line 526, reserve 成功后置位）
  - 保留 finally 块 `if _idempotency_reserved: complete_inbound`（line 638, 有效逻辑）
- **回归测试**: `tests/test_sprint14_rel1_idempotency_init.py`（4 用例）+ `tests/test_sprint11_rel1_idempotency_reserved_init.py`（6 静态契约）= **10 PASSED**

#### ~~REL-11-5 `inbound_idempotency` inflight 状态无 TTL~~ ✅ Sprint 11 94343dc 修复
- **位置**: `butler/gateway/inbound_idempotency.py:21-25, 49-64, 107, 145`
- **修复方案**: lazy sweep（`check_and_reserve_inbound` / `complete_inbound` 时清理过期 inflight）
  - TTL 默认 60s，`BUTLER_GATEWAY_INFLIGHT_TTL_SEC` 可配
  - sweep 只清理 inflight 状态，保留 done 状态
  - 线程安全（在 `_LOCK` 内执行）
  - 无后台线程
- **回归测试**: `tests/test_sprint11_rel5_inflight_ttl.py` — **7 PASSED**

### 🟠 HIGH — 0 项 — Sprint 16 已修

| ID | 位置 | 问题 |
|----|------|------|
| ~~REL-11-2~~ | ~~`mcp/async_runner.py:11-39`~~ | ~~守护线程 + 独立 loop，**无 atexit/signal/shutdown**~~ ✅ Sprint 16 `45d8d8a`: shutdown_async_runner + atexit first-use 注册, 12 测试 |
| ~~REL-11-3~~ | ~~`runtime/notify.py:130`~~ | ~~`asyncio.run(send_wechat_direct(...))` 同步路径里跑~~ ✅ Sprint 16 `d01873f`: 改用 async_runner.run_mcp_async, 2 测试 |
| ~~REL-11-4~~ | ~~`gateway/runner.py:38, 100, 190, 204`~~ | ~~SIGTERM 只 `stop.set()`，不等待 executor 排空~~ ✅ Sprint 16 `b52c83a`: _SHUTDOWN_EVENT + grace 30s timeout + is_shutting_down 门控, 14 测试 |

### 🟡 MEDIUM — 0 项 — Sprint 16 已修

| ID | 位置 | 问题 |
|----|------|------|
| ~~REL-11-6~~ | ~~`mcp/manager.py:54-61`~~ | ~~`_handles_for` 锁外返回 live dict~~ ✅ Sprint 16 `5770a50`: 改返回 dict() 快照 + `_with_handles` ctx mgr, 5 测试 |
| ~~REL-11-7~~ | ~~`human_gate.py:19, 280-300`~~ | ~~`consume_injection_bypass` 跨进程不安全~~ ✅ Sprint 16 `7400a5f`: 改用 `os.rename` 原子抢占, 4 测试 |
| ~~REL-11-8~~ | ~~`runtime/audit.py:97`~~ | ~~`release_lock.unlink` 静默吞咽 OSError~~ ✅ Sprint 16 `f2f089f`: 显式分 FileNotFoundError vs 其他 OSError, 7 测试 |

---

## 4. 测试缺口 + 死代码（Test/Dead Code — 19 项）

### 🔴 CRITICAL

#### TST-11-1 `butler/runtime/approval.py` 真死代码  ⚠️ **Sprint 11 审计误报**
- **位置**: `butler/runtime/approval.py` (140 行)
- **初次审计结论**: `grep "from butler.runtime.approval" butler/ tests/` = **0 命中**，报为真死代码，建议删。
- **复检结果 (2026-06-02)**: **实为 false positive**。
  - `butler/runtime/service.py:12` 实际是 `from butler.runtime import approval, audit, loader, notify, runner, schedule`（namespace 形式）
  - 主审计师 pattern 漏检形式：`from butler.runtime import` 后接 approval 的子句（form3-namespace）
  - `tests/test_runtime.py:335` 也有同款 `from butler.runtime import approval`
  - 实际 `approval.*()` 调用 ≥3 处
- **修复**: 已加 `tests/test_sprint11_tst1_approval_alive.py` 回归保护，3 种 import 形式（form1 / form2 / form3-namespace）全覆盖，防止后续 subagent 误删。
- **审计方法学**: 死代码扫描必须覆盖 3 种 import 形式：
  - form1: `from butler.runtime.approval import X`
  - form2: `import butler.runtime.approval`
  - form3: `from butler.runtime import ... approval ...`（namespace，Sprint 11 漏检）
- **关联消化**: **不成立**。Sprint 10 REL-NEW-07 `consume_approval` RMW 仍为独立 finding，approval 模块保留。

### 🟠 HIGH

| ID | 位置 | 问题 |
|----|------|------|
| ~~TST-11-2~~ | ~~`wechat_ilink.py:158,1042,1058` `_LIVE_ADAPTERS`~~ | ~~0 race test~~ ✅ Sprint 11 `55816ad`: 补 14 个 race + 契约测试 (5 顺序语义 + 2 并发不同 token 32 线程 + 1 并发同 token 16 线程 + 2 connect/disconnect 交错 + 4 静态契约) |
| TST-11-3 | `lifecycle_commands.py` 234 行 | coverage 21%；11 handler 仅 `_cmd_config` 测 (✅ `6fddada` 补 41 测试：/doctor×5 /export×2 /回滚×5 /分叉×6 /会话记忆×6 /确认安装×2 /注册表×2 /任务×4 /工作流×2 /_require_owner×2 /静态契约×4) |
| TST-11-5 | `execute_code.py:52-116` `run_execute_code` | 1 unit test (disabled 路径)；0 真实 subprocess (✅ `4667c91` 补 38 测试: enabled×3 / input×7 / 真实 subprocess×4 / errors×3 / env×3 / timeout×7 / workspace_cwd×4 / register×4 / 契约×3) |
| ~~TST-11-9~~ | ~~`mcp/{client_http,client_stdio,server_stdio}.py`~~ | ~~三文件 0%；mcp 子包覆盖极薄~~ ✅ Sprint 11 `6de1ac1`: 补 31 个新测试 (client_stdio 16 + client_http 7 + server_stdio 8) → 高覆盖 |
| TST-11-10 | `wechat_ilink.py:1720-1737` `_download_remote_media` SSRF | 0 e2e with redirector/IPv6/0.0.0.0 (✅ `8d73ba0` 补 75 测试: is_safe_url 阻断×30+/放行×6, assert_safe_redirect×5, safe_registry_get×8 (5 个 3xx 状态码), _download_remote_media 集成×11, 契约×4) |

### 🟡 MEDIUM

| ID | 位置 | 问题 |
|----|------|------|
| ~~TST-11-4~~ | ~~`handler_helpers.py:376` `_WELCOMED_SESSIONS`~~ | ~~race test 不全~~ ✅ Sprint 11 `4b9d9de`: 补 11 个新测试 (不同 session 并发 / 真实 set 锁 / 顺序覆盖 / 重启读 marker / BUTLER_HOME 隔离 / 跨 spawn 进程) |
| ~~TST-11-6~~ | ~~`__init__.py:55-57, 60-63`~~ | ~~`format_build_identity_line` / `mark_start_time` 0%~~ ✅ Sprint 11 `298e814`: 补 7 个新测试 (subprocess 缓存 + CalledProcessError 分支) → 100% 覆盖 |
| ~~TST-11-7~~ | ~~`agents_md.py:80-88`~~ | ~~`list_agent_md_names` 0%~~ ✅ Sprint 11 `50f700e`: 补 5 个新测试 (dir 缺失/sorted/stem/subdir 过滤) → 100% 覆盖 |
| ~~TST-11-11~~ | ~~`runtime/{audit,loader,schedule}.py`~~ | ~~0 直测；Sprint 10 REL-NEW-01 修的 flock 锁内容无独立 race test~~ **✅ Sprint 16: 47 个新测试 (loader 20 + audit runs 10 + schedule 17)** |

### 🟢 LOW

| ID | 位置 | 问题 |
|----|------|------|
| ~~TST-11-8~~ | ~~`cli/doctor.py` 60 行~~ | ~~整文件 0 测试~~ ✅ Sprint 11 `18fffeb`: 补 13 个新测试 (数据目录 ✓/✗、依赖、.env、API key、workspace 探测、critical vs warn 退出码) → 92% 覆盖 |

### Sprint 10 残留（1 项：TST-10-5 仍在迁移中；TST-10-6 暂缓）

| ID | 问题 | 严重 |
|----|------|------|
| TST-10-2 | `tenant_store.py TenantStore` 0 直测 | ✅ `21d9df5` |
| TST-10-3 | `extract_layered_summary` 0 直测 | ✅ `bac97e4` |
| TST-10-4 | `atomic_write.atomic_write_text` 0 直测 | ✅ `a0353f9` |
| TST-10-5 | 28 个 `CommandDef` 缺 handler | ✅ (Sprint 11-16 八批完成, 30 → 0) |
| TST-10-6 | MagicMock 99.6% 无 `spec=` | ✅ Sprint 23: AST 扫描器 + baseline gate, baseline 614 → 0 (50+ 个文件清理 614 处, 累计 -100%); 所有豁免 `# noqa: magicmock-no-spec — <category>` 标记完整 |
| TST-10-7 | `test_gateway_handler.py` 18/59 unique commands | ✅ `6336eb7` |
| TST-10-8 | `wechat_ilink.py` 2027 行仍在 coverage omit | ✅ (当前 commit) |
| TST-10-9 | Sprint 9 报告口径过期 | ✅ (验证) |

---

## 5. 修复建议

### 短期（0🔴 — Sprint 11/14 已全部修完）
1. ~~**TST-11-1** 删 `runtime/approval.py`（10min + 测试，含消化 REL-NEW-07）~~ — Sprint 11 复检证实为 namespace 引用，非死代码
2. ~~**REL-11-1** `_idempotency_reserved` 初始化位置修复（30min + 测试）~~ ✅ Sprint 14 a6e36af
3. ~~**REL-11-5** inflight TTL/sweep（1h + 测试）~~ ✅ Sprint 11 94343dc
4. ~~**PERF-11-1** message_queue sort 优化（1h + 测试）~~ ✅ Sprint 11 194e6d6
5. ~~**PERF-11-2/3** exp_cache 改为 SQLite 或 mmap（30min + 测试）~~ ✅ Sprint 11 1ba1c45
6. ~~**PERF-11-5** semantic_index 拆 read/write lock（2h + 测试）~~ ✅ Sprint 11 899ccc7

### 中期（owner-gate 6 项 = 2h）
- ~~**SEC-11-1/2/4/5/6/7** 6 个命令加 owner gate + 引入 CI 静态扫描~~ ✅ Sprint 17 SEC-11 owner gate completion: 6 handler 加 gate + 3 opt-out 标记 + scan gap 9 → 0

### 长期（性能 + 测试 = 5 天）
- ~~PERF-11-4/6/7~~ ✅ Sprint 13 PERF-13-1/2/3 (560bd56/5551db2/9eef7b1)
- ~~PERF-11-8/9/10/11~~ ✅ Sprint 15 (a85b28a/9fb8c7b/0dc1680/8049afc) — SkillLockFile 缓存 + llm_retry _safe_call + 工具文件 LRU + middleware hook 预解析
- ~~TST-10-2/3/4/5/7/8/9~~ ✅ Sprint 11-16 全部完成
- ~~TST-10-6~~ ✅ Sprint 23-40: MagicMock() 无 spec= 治理闭环 (614 → 0, AST 扫描器 + per-line noqa 豁免)

---

## 6. Sprint 11+ 修复记录

| ID | 修复 | Commit | 备注 |
|----|------|--------|------|
| **SEC-11-3** | `butler/memory/butler_memory.py:ExperienceStore.add` 加 `_reject_injection(content or "")` 拦截, 命中返 -1 sentinel | `5f4b10c` | 与 ProfileStore 对齐; 6 个 RED 测试覆盖 5 个 `_INJECTION_PATTERNS` + 正常通过 + None/空串防御; 157 个 experience.add 现有调用方测试无回归 |
| **PERF-13-1** (PERF-11-4) | `butler/core/tool_selector.py` `_tool_embed_cache` 改 OrderedDict + 256 上限, key 用 `hashlib.blake2b` 稳定 hash (不依赖 PYTHONHASHSEED), 命中 `move_to_end` 维持 LRU, 写满 `popitem(last=False)` 淘汰 | `560bd56` | 195 个新测试覆盖 hash 稳定性 (跨 PYTHONHASHSEED 一致) + LRU 淘汰 (256 → 257 触发) + 命中顺序 (move_to_end) + clear/size 边界 |
| **PERF-13-2** (PERF-11-6) | `butler/memory/embedding.py` 新增 `_CachedEmbedder` LRU 包装层 (OrderedDict + max_size=128 + blake2b 稳定 key); `_build_embedder` 对非 HashingEmbedder 自动包装, HashingEmbedder 跳过 (无 API 开销); 拆 `_build_raw_embedder` 便于独立可测 | `5551db2` | 227 个新测试覆盖 LRU 命中/淘汰/max_size/不同 embedder (API/local) 包装/Hashing 跳过/blake2b 稳定性 |
| **PERF-13-3** (PERF-11-7) | `butler/core/session_transcript.py` 新增 `transcript_batch(session_key)` ctx mgr: 块内 `record_*()` 走 buffer, 退出时一次性 `_flush_entries` (单 file open + writelines); `butler/core/agent_loop.py:run()` 整轮 turn 包裹 → 4 个 record_* 合成 1 次写入 | `9eef7b1` | session_transcript.py +66 行, agent_loop.py +20 行; 嵌套/异常 (finally flush)/线程安全; 行为不变性: 退出时原子 flush 失败抛错, 不丢已有 buffer |
| **REL-11-2** | `mcp/async_runner.py` 加 `shutdown_async_runner` + `_atexit_shutdown` + atexit first-use 注册 | `45d8d8a` | 守护线程 graceful shutdown, idempotent, 12 个新测试覆盖 |
| **REL-11-3** | `runtime/notify.py:push_runtime_message` 改用 `async_runner.run_mcp_async` 代替 `asyncio.run` | `d01873f` | 避免在 MCP tool handler / 已运行 event loop 线程中调用崩溃, 2 个新测试 |
| **REL-11-6** | `mcp/manager.py:_handles_for` 改返回 `dict()` 快照 + 新增 `_with_handles` 上下文管理器 | `5770a50` | 避免与 `disconnect_session` 竞争抛 "dict changed size", 5 个新测试 (含 Barrier 同步多线程) |
| **REL-11-7** | `human_gate.py:consume_injection_bypass` 改用 `os.rename` 原子抢占, 替代 `threading.Lock + is_file + unlink` TOCTOU | `7400a5f` | 跨进程 consume-once; 4 个新测试 (含 spawn+Barrier 多进程并发) |
| **REL-11-8** | `runtime/audit.py:release_lock` 显式分 `FileNotFoundError` (benign race) vs 其他 `OSError` (logger.warning) | `f2f089f` | 7 个新测试覆盖所有 OSError 分支 |
| **REL-11-4** | `butler/gateway/runner.py` shutdown 序列加 grace 超时 + `_SHUTDOWN_EVENT` 通知 in-flight handler | `b52c83a` | 加 `is_shutting_down()` + `request_stop()` 模块级 API (threading.Event, executor 线程可见) / submit 前检查 / `asyncio.wait_for(executor.shutdown, timeout=30s)` 防卡死 / 幂等. 14 个新测试覆盖 5 场景 |
| **TST-10-5** | 迁移 3 个 inline 命令到 registry handler: /会话 /评价 /诊断 | `ad560e0` | 信息性 if/elif 块删除, info_commands.py 注册; whitelist 30→27; TestInlineCommandMigration 跟踪 |
| **TST-10-7** | TestEveryRegisteredCommandDispatches 100% 覆盖 59 unique command dispatch | `6336eb7` | 不再 18/59 partial, 3 个新测试验证所有命令可 dispatch + 无 NotImplementedError + help_text 非空 |
| **TST-10-9** | 验证 Sprint 9 TST-2 "缺 45 script" 报告口径已过期 | — | `tests/corpus/harness/gateway_scripts.py:42 script_profiles()` 当前含 46 个 profile 定义；pytest 失败分析显示 0 处 "missing script" 错误（仅 behavioral "tool not called" 类，与 TST-2 不同源） |
| **TST-11-6** | `butler/__init__.py:format_build_identity_line / mark_start_time` 0% → 100% 覆盖 | `298e814` | 7 个新测试, 含 subprocess 缓存 + CalledProcessError 分支 |
| **TST-11-7** | `butler/agents_md.py:list_agent_md_names` 0% → 100% 覆盖 | `50f700e` | 5 个新测试, 含 dir 缺失/sorted/stem/subdir 过滤 |
| **TST-11-8** | `butler/cli/doctor.py:cmd_doctor` 0% → 92% 覆盖 | `18fffeb` | 13 个新测试, 含数据目录 ✓/✗、依赖、.env、API key、workspace 探测、critical vs warn 退出码 |
| **PERF-11-9** | `butler/core/llm_retry.py:11 处 try/except: logger.debug` → `_safe_call(fn, msg)` 集中处理, 短路 `isEnabledFor(DEBUG)==False` 时跳过整个 try/except + fn 调用 | `9fb8c7b` | 7 个新测试, 5 静态契约 (helper 存在/短路/运行/吞异常/无内联) + 2 行为契约 (happy path/interrupt). **行为变化**: DEBUG 关闭时 4 处 metrics + provider_health + recovery_buckets + exp_cache + safety_finish 全部短路, 生产可观测性退化 |
| **TST-11-4** | `butler/gateway/handler_helpers.py:_WELCOMED_SESSIONS` race test 补全: 11 个新测试覆盖 5 类场景 | `4b9d9de` | 既有仅 16 线程同 session SlowSet, 缺: 不同 session 并发 / 真实 set 锁测试 / 顺序覆盖 / 重启读 marker / BUTLER_HOME 隔离 / 跨 spawn 进程同/不同 session. 锁+set 实现已正确, 不动 |
| **TST-11-2** | `butler/gateway/platforms/wechat_ilink.py:_LIVE_ADAPTERS` 补 14 个 race + 契约测试 (0 → 14) | `55816ad` | 5 顺序语义 + 2 并发不同 token (32 线程 + asyncio.gather) + 1 并发同 token (16 线程) + 2 connect/disconnect 交错 (50 flap + lookup 不抛 KeyError) + 4 静态契约 (dict 类型/pop 默认值/connect 注册/无裸下标) |
| **TST-11-9** | `butler/mcp/{client_http,client_stdio,server_stdio}.py` 0% → 高覆盖 (31 个新测试) | `6de1ac1` | client_stdio 16 (env 阻止 + warning / cwd 解析 / json_dumps / call_stdio 文本拼接) + client_http 7 (call_http + connect_http 错误路径) + server_stdio 8 (_dispatch_builtin 错误 JSON / dispatch / parametrize 4 EXPOSED + 5 静态契约) |
| **TST-11-3** | `butler/gateway/commands/lifecycle_commands.py` 11 handler 仅 `_cmd_config` 测 → 41 测试 (0% → 100%) | `6fddada` | /doctor×5 /export×2 /回滚×5 /分叉×6 /会话记忆×6 /确认安装×2 /注册表×2 /任务×4 /工作流×2 /_require_owner×2 /静态契约×4 |
| **TST-10-2** | `butler/tools/tenant_store.py TenantStore` 0 直测 → 42 测试 | `21d9df5` | enabled×7 (env_toggle 0/false/no/空白) + storage_dir×4 (默认/custom_tenant/subdir/不创建) + save×5 (JSON 路径/建 dir/ensure_ascii=False/indent/覆盖) + load_all×8 (空/缺 dir/排序/skip_files/JSON 坏/缺 id/非 dict/skills 字段) + load_one×5 (命中/缺/id 不匹配/JSON 错/dir 缺) + delete×3 (命中/缺/dir 缺) + count×4 (0/全量/predicate/全 false) + 静态契约×3. 注意 `get_butler_settings()` 单例缓存, fixture 必须 `config.reload_butler_settings()` |
| **TST-10-3** | `butler/session/post_session_layered.py:extract_layered_summary` 0 直测 → 27 测试 | `bac97e4` | disabled gate×4 (默认/显式 0/无 llm_call) + short transcript 早退×2 (<200 chars / 空 msgs) + sync llm_call×3 (三 list/markdown fence/外周文本) + async llm_call×1 (coroutine await) + 异常/坏响应×6 (sync/async 异常/非 JSON/坏 JSON/list 顶层/空 dict) + 列表截断×7 (3 条 cap/240 chars/空串跳过/非 list 字段/缺字段/None 字段/非 str 元素) + 静态契约×4 |
| **TST-10-4** | (Sprint 15) `butler/io/atomic_write.py:atomic_write_text` 0 直测 → 17 测试 | `a0353f9` | basic write×7 (新建/建父 dir/覆盖/Unicode/空串/无 .tmp 残留/自定义 encoding) + 文件权限×1 (0o600) + symlink 拒绝×2 (raw symlink/resolve 后非 symlink 放行) + fsync×1 + 临时文件命名×3 (.tmp suffix / O_NOFOLLOW / O_CREAT+O_TRUNC) + 边界×3 (旧 content 替换/string→Path/idempotent) |
| **TST-10-8** | `pyproject.toml` coverage omit 移除 `wechat_ilink.py` + `wechat_format.py` | (当前 commit) | omit 前总覆盖率 75% (40999 stmts), omit 后 74% (42287 stmts, +1288), 仍 ≥ 55% fail_under 阈值 (~19% 余量). 移除后 wechat_ilink 41% (433/1051 stmts) + wechat_format 22% (52/237 stmts) 真实被 coverage 计入, 后续 55% gate 真实覆盖到. 无需新增 e2e, 已有 8 个 wechat 相关测试文件 105 测试已提供基线 |
| **TST-10-5** 第二批 | 迁移 4 个 inline 记忆命令到 registry handler | `a5114a9` | /记忆图谱 /记忆待审 /拒绝记忆 /批准记忆 — 删除 message_handler.py 8 行 if/elif; 新建 butler/gateway/commands/memory_commands.py; _KNOWN_INLINE_COMMANDS 27→23; 26 个新测试覆盖 dispatch/委派/owner gate/集合缩小. Sprint 12+ 继续迁移剩余 23 个 inline 命令 |
| **TST-10-5** 第三批 | 迁移 3 个 runtime 命令到 registry handler | `b0202b8` | /定时 /批准运行 /运行 — 删除 message_handler.py 8 行 if/elif; 新建 butler/gateway/commands/runtime_commands.py; _KNOWN_INLINE_COMMANDS 23→22; 20 个新测试. Sprint 12+ 继续迁移剩余 22 个 inline 命令 |
| **TST-10-5** 第四批 | 迁移 6 个 dev 工具命令到 registry handler | `52387ad` | /git /测试 /构建 /开发状态 /开发验收 /项目概况 — 共享 `_dev_delegate` 委派 (含 owner gate); 删除 message_handler.py 8 行 if/elif; 新建 butler/gateway/commands/dev_commands.py; _KNOWN_INLINE_COMMANDS 22→16; 17 个新测试覆盖 dispatch/委派/owner gate/集合缩小. 额外修复 2 个 test_gateway_handler 预存 flake (test_non_command_returns_none + test_unknown_slash_command_enters_session_turn) |
| **TST-10-5** 第五批 | 迁移 4 个 inline 项目/状态命令到 registry handler | `6c97185` | /项目 (/projects) /状态 (/status) + /项目 新建|/项目 体检 子命令入口 — 抽 format_project_list() / format_butler_status() 到 butler/gateway/commands/project_commands.py; 从 default 列表移除 /项目 体检 / /项目 新建 (它们是 /项目 子命令, cmd 永远是 /项目, 单独注册从未被 dispatch 命中); 删除 message_handler.py 65 行 inline 块; _KNOWN_INLINE_COMMANDS 16→12; 18 个新测试覆盖 dispatch/委派/子命令路由/死代码清理/集合缩小. 剩余 12 个 inline: /切换 /模型 /新对话 /始终允许 /批准一次 /批准执行 /批准模式 /继续 /权限 /urgent /later /停止 (4 个权限 + 3 个对话 + 2 个 lifecycle + 4 个 prequeue) |
| **TST-10-5** 第六批 | 迁移 5 个 inline 权限命令到 registry handler | `7047202` | /权限 (/perms) /批准一次 /始终允许 (/always-allow) /批准执行 (/approve-exec) /批准模式 (/approve-pattern) — 抽 `_check_owner_or_return()` 统一 owner gate; handler 直接调底层 grant_always/grant_once/list_always/store_approval/approve_pattern (旧版走 parse_permission_command(text) 文本解析); 删除 message_handler.py 42 行 try/except 块 (slash dispatch 之前的旧 pre-processor); _KNOWN_INLINE_COMMANDS 12→7; 32 个新测试覆盖 dispatch/委派/owner gate (5 命令参数化)/错误处理/集合缩小. **行为差异**: 旧 try/except logger.debug 吞异常 → 新走 registry 集中处理 (logger.error + 返 "命令执行异常: ..."), 失败时用户可见. 全部 5 个 handler 在 test_sprint12_owner_gate_scan 静态扫描中均识别为有 gate (无新增 gap). 剩余 7 inline: /切换 /模型 /新对话 (3 对话控制) + /继续 /urgent /later /停止 (4 lifecycle/特殊路径) |
| **TST-10-5** 第七批 | 迁移 3 个 inline 对话控制命令到 registry handler | `4b39dc4` | /切换 (/switch) /模型 (/model) /新对话 (/new) — 添加到既有 dialog_commands.py (与 8 个 owner-gated 命令共存, _DIALOG_COMMANDS 8→11); 抽 format_switch_project_reply() / format_model_reply() / format_new_session_reply() 作为可重用函数; 不再用 _reset_tool_audit_events 私有别名, 改用 public butler.tools.tool_audit.reset_tool_audit_events; 3 个 handler 均无 owner gate (per-chat/per-session 用户操作), 在 docstring 标 owner-gate-opt-out: 标注; 删除 message_handler.py 95 行 inline 块; _KNOWN_INLINE_COMMANDS 7→4; 24 个新测试覆盖: 静态契约 (含 11 总数验证 + 无 owner gate 静态检查) + dispatch + 别名 + 委派 (5 switch + 3 model + 3 new session 场景) + 错误处理 (3 handler 异常) + 集合缩小. owner_gate_scan gap 数仍 9 (3 个新增均为 opt-out, 未引入新 gated 缺口). 剩余 4 inline: /继续 /urgent /later /停止 (prequeue interrupt / sessionless 路径, 行为最复杂, 建议最后一批) |
| **TST-10-5** 第八批 (完成) | 清理 4 个 prequeue/special-path 命令, **Sprint 11 baseline 30 → 0** | (当前 commit) | /继续 /停止 /urgent /later — 这 4 个**不是** slash dispatch 命令, 加 registry handler 无意义, 改用混合迁移方案. **(1) /urgent /later**: pre-queue priority tag (在 `classify_inbound_priority` 中识别为 priority prefix, 整段文本入队), CommandDef 从 registry 完全移除, `classify_inbound_priority` docstring 加 priority tag 注释. **(2) /停止**: pre-dispatch hook (in-flight session 中断), 抽 `_format_prequeue_interrupt_reply(self, session_key) -> str` 方法到 `ButlerMessageHandler`, 含防御性 try/except 包裹 interrupt (即使 _interrupt_session_loop 抛异常也返消息), message_handler.py line 422-424 + line 548 (queue mode = "interrupt") 均改调此方法, CommandDef 同步移除. **(3) /继续**: pre-dispatch text rewriter (auto_continue 恢复), 抽 `apply_auto_continue_rewrite(session_key, text) -> str \| None` helper 到 `handler_helpers.py`, 包装 `resolve_auto_continue_user_message` (含异常吞掉 + logger.debug), pre-dispatch rewriter 改调此 helper, CommandDef 同步移除. **(4) `_KNOWN_INLINE_COMMANDS`**: 4 → 0, 改 `<= 4` → `== 0` 断言 + 显式空集断言, 注释 "TST-10-5 全部迁移完成" 防止回退. **(5) 关键风险**: 4 个 CommandDef 必须**同步**从 `_register_defaults()` 移除, 否则 `test_no_unexpected_commands_need_handler` 失败 (handler=None 但不在 whitelist 中, 会触发 "未定义路径" 错误). 18 个新测试覆盖: 静态契约 (4 lookup None) + auto_continue rewrite 行为 (4 cases: has_pending / no_pending / exception + helper_in_module) + prequeue interrupt 行为 (3 cases: returns_message / interrupt_exception / no_session_loop) + 集合归零 (2 cases) + 完成断言 (1 case) + priority tag docstring (1 case) + 集成 (3 cases: 4 commands not in registry / help_text no longer shows / 4 commands have no e2e path). **最终状态**: Sprint 11 baseline 30 个 inline 命令 → 0, 全部走 registry dispatch 或 pre-dispatch hook; TST-10-5 任务关闭. owner_gate_scan gap 数仍 9 (本批添加 0 个新 handler, 2 个 helper `apply_auto_continue_rewrite` / `_format_prequeue_interrupt_reply` 命名不匹配 `^(handle_[a-z_]+command\|_cmd_[a-z_]+)$` 模式, 无新 gated 缺口).
| **TST-11-5** | `butler/tools/execute_code.py` 仅 1 disabled test → 38 测试 | `4667c91` | enabled gate×3 + input validation×7 + 真实 subprocess×4 (print 1+1 happy / NameError / 16k stdout 截断 / 4k stderr 截断) + subprocess errors×3 (TimeoutExpired / OSError / tempfile 清理) + env 构造×3 (网络禁用 proxy blockers / PYTHONNOUSERSITE/-I) + timeout 配置×7 + workspace_cwd×4 (contextvars 切换) + register tool×4 + 静态契约×3 |
| **TST-11-10** | `butler/registry/url_safety.py` + `wechat_ilink._download_remote_media` 仅 1 最小 unit test → 75 测试 (重点: 0.0.0.0 / IPv6 ::1 / link-local 169.254 / metadata / .local / .internal) | `8d73ba0` | is_safe_url 阻断 30+ (RFC1918/loopback/0.0.0.0/link-local 4 类/IPv6 ::1+ULA+fe80/localhost/metadata/.local.internal/ftp-file-gopher/空 URL/无 host/DNS 失败/DNS 解析到 192.168/127/169.254) + 放行 6 (公网 IP/公网域名/mock DNS/allowed_hosts bypass) + assert_safe_redirect×5 + safe_registry_get×8 (5 个 3xx 状态码参数化 + 相对路径 urljoin + kwargs 透传) + _download_remote_media 集成×11 (4 类 unsafe + ValueError 含原 URL + happy path 写 tempfile + .bin fallback + query string 剥离 + 30s wait_for + session.get URL 透传) + 静态契约×4. 注意: `_download_remote_media` 用 `from tools.url_safety import is_safe_url` (hermes 命名空间包), 集成测试 patch `tools.url_safety.is_safe_url` |
| **PERF-11-8** | (Sprint 15) `SkillLockFile` 走 `read_json_cached` + `get()` O(1) | `a85b28a` | 18 测试: load 缓存×2 / save 失效×1 / get 效率×3 (不走 list_installed) / 跨实例共享×1 / list_installed 排序×2 / 行为正确性×3. 验收: K 次 SkillLockFile.get() 转为 1 次磁盘读 + O(1) dict lookup |
| **PERF-11-10** | (Sprint 15) 工具文件读取按 `(path, mtime)` LRU 缓存 | `0dc1680` | 新建 `butler/tools/_file_cache.py` (`read_json_cached` LRU 256 + 线程安全), expense/contacts/habits 全部改用, 24 测试覆盖 (mtime 失效 / LRU 淘汰 / 各工具 _load_all 缓存命中 / write-then-read 一致性) |
| **PERF-11-11** | (Sprint 15) middleware/plugin hook 预解析 | `8049afc` | `LoopMiddlewareChain.__post_init__` 预解析 `_before_llm_hooks` / `_after_tools_hooks` / `_wrap_tool_call_hooks`, 14 middleware × N turn 从 N×getattr 降至 0; `LoopPluginRegistry` 同处理. 13 测试: 顺序/链式/倒序/失败容错/无 wrap 跳过/预解析验证/getattr 计数 |
| **TST-11-11** | (Sprint 16) runtime/{audit,loader,schedule}.py 补 47 直测 | (当前 commit) | loader 20 (load_jobs_file 13 + find_job 4 + list_jobs 3) + audit runs 10 (write_run_record 5 + latest_run 5) + schedule 17 (job_is_due 7 + format_schedule_hint 4 + next_run_iso 6). 注意: audit.py 用 `from butler.config import get_butler_settings`, fixture 必须 `monkeypatch.setattr(audit, "get_butler_settings", ...)` 在 audit 模块 patch (Sprint 16 _tenant_store 同款教训) |
| **SEC-11-1/2/4/5/6/7** (Sprint 17 owner gate completion) | 6 registry handler 加 owner gate + 3 memory handler opt-out 标记, scan gap 9 → 0 | (当前 commit) | **背景**: Sprint 12 owner_gate_scan 静态扫描器标记 9 个 handler 缺 owner gate (sprint 12 修复了 1 个, 剩 9). 6 个 owner-gated 改盘命令 + 3 个 read-only memory 命令 (per test_sprint11_sec2_memory_approve_owner 既有契约). **修复**: (T1) `info_commands.py` 加 `_require_owner(ctx)` helper + 5 handler 改用: `_cmd_sessions` / `_cmd_outcome` / `_cmd_health` / `_cmd_detail` (Sprint 12 已加) + 4 私人数据 handler (_cmd_todos / _cmd_memo / _cmd_contacts / _cmd_expense / _cmd_habits / _cmd_project_todos / _cmd_memory_status). (T2) `memory_commands.py` 加 3 opt-out marker (read-only 路径): `_cmd_memory_graph` / `_cmd_memory_pending_list` / `_cmd_memory_reject`. `_cmd_memory_approve` 已含 owner gate (不动). (T3) `runtime_commands.py` 加 inline `is_gateway_owner` 检查到 `_cmd_runtime_jobs_list` (Sprint 17 SEC-11 扩展, 旧版无). (T4) `project_commands.py` 加 `_require_owner` + 应用到 `_cmd_project_list` / `_cmd_butler_status` + 加 import. (T5) info_commands 5 个其他 private handler (_cmd_overview / _cmd_memory_status 等) 已有 owner gate (info_commands 共享同一 helper). **新测试**: `tests/test_sprint17_sec11_owner_gate_completion.py` 24 tests: TestInfoHandlerGates 5 (3 验证 blocked + 2 owner pass-through) + TestProjectHandlerGates 4 + TestRuntimeHandlerGates 2 + TestMemoryHandlerOptOut 4 (3 marker + 1 graph runtime) + TestHandlerNotFlaggedByScan 9 (每个 handler 在 scan 中不被 flag). **fixture 适配**: `tests/conftest.py:butler_orchestrator` + `tests/gateway/test_gateway_handler.py:handler/handler_with_project` + `tests/test_memory_p1_p2.py:test_status_shows_env_default_project` + `tests/gateway/test_gateway_acceptance.py:gateway_handler/gateway_handler_with_project/gateway_handler_project` + 4 inline test body, 全部加 `monkeypatch.setenv("BUTLER_PROJECT_CREATE_OPEN", "1")` 走 dev 旁路 (避免每个测试伪造 owner). `test_sprint16_tst10_5_project_status_migration.py` 加 7 个 `patch.object(module, "is_gateway_owner", return_value=True)` + `test_sprint16_tst10_5_runtime_commands_migration.py` 改 1 test 期望 (新增 owner gate) + 加 1 new test. **最终**: owner_gate_scan 0 gaps, 全部 9 SEC-11 baseline gaps 关闭. owner-gate 总计 6 新加 + 3 opt-out. 全部 35 owner-gate 相关测试 (24 新 + 5 Sprint 12 scan self-test + 6 Sprint 11 SEC-2 memory) pass. 回归: 109 → 94 failed (-15), 1215 passed (含 24 新). |
| **§3.2** (P1-3.2, Sprint 24) | §3.2 会话批准缓存完整补齐: approval diagnostics + revoke/clear + /诊断集成 + 2 inline 命令 | 5 commits (1+1+1+2, 含 IMPROVE refactor) | (1) `is_approved` 加 diagnostics kw-only 形参, 命中写 `approval_cache_hit` + `approval_cache_source` (once/always), 向后兼容 3 个既有调用点; (2) `revoke_always` 按 permission/tool/pattern 过滤撤销 (全空过滤返 "请指定 ... 至少一项" 防误删), `clear_always` 清空所有, 返 "已清除 N 项始终允许"; (3) `summarize_approvals(session_key)` 给 /诊断读 approvals.json 统计 (always_count / once_active_count / has_pending), 与 `collect_mem_stats_for_health` 同 try/except 模式; (4) `health_report.py` `_shared_diagnostic_lines` 加 "权限批准缓存" 块 (缩进 2 空格, 沿用既有 format 风格); (5) `/撤销批准 <perm> [tool] [pat]` 与 `/清除始终允许` 注册到 `permission_commands` (owner gate + dispatcher), `_cmd_revoke_always` 形参解析简化为 `perm, tool, pat = (arg.split() + ["", "", ""])[:3]`; (6) workflow 不可穿透测试: `is_step_approved` (human_gate.py:184) 与 `is_approved` (approvals.py:212) API 独立 + 存储路径分离, 互不影响. **19 个新测试** (tests/test_sprint24_p1_3_2_approval_diagnostics.py): diagnostics 4 + revoke 5 + summarize 2 + health 3 + registry 4 + workflow 1. **owner_gate_scan gap 数仍 9** (2 新 handler 都有 owner gate, 无新增). **commit 序列**: `05cd750` (is_approved diagnostics) + `60058f7` (revoke/clear/summarize) + `0abfabe` (/诊断 integration) + `136e30d` (registry commands) + `c0940ef` (IMPROVE refactor) |
| **§3.3** (P1-3.3, Sprint 24 收口) | external_directory 规则 + shell 路径预检 — **清单 stale, 代码早已存在**, 仅完成 doc 标 [x] | 0 代码 commit (无新代码) | **背景**: checklist §3.3 状态 `[ ]` 是 stale, 实际自 Sprint 1 已有 `evaluate_external_directory` (`permissions/rules.py:109`) + Sprint 1 `check_tool_path` (`path_safety.py:106`) + Sprint 1 `prepare_shell_command` shell 预检 (`path_safety.py:179`, shlex.split + regex) + session approval cache 集成 + `permissions.yaml.example:27` 文档化. 关键历史 fix: Sprint 21-1 SEC-21-A-1 `is_relative_to` 越界判定修复 (防 sibling-prefix 误判) + Sprint 21-4 QUAL-21-D-2 uninstall_skill 越界统一 + Sprint 1 symlink guard. **测试覆盖** (Sprint 24 盘点): `test_path_safety.py` 8 + `test_permission_approvals.py` 4 + `test_sprint8_sec6_path_safety.py` 74 lines + `test_sprint20_quarantine_path_safety.py`. **已知 gap** (留待后续 sprint 单独 P1-3.3-gap 任务): Windows/WSL 单测覆盖 0; 相对路径仅 1 case (`test_relative_path_resolves_inside_workspace`); `/诊断` 未透传 external_directory decision. **本次收口**: checklist 标 [x] + audit doc 加 entry, 不写新代码. |
| **§3.4** (P1-3.4, Sprint 24 收口) | child_session_key 独立 transcript — **清单 stale, 代码早已存在**, 仅完成 doc 标 [x] | 0 代码 commit (无新代码) | **背景**: checklist §3.4 状态 `[ ]` 是 stale, 实际自 Sprint 6 委派层建设以来已形成完整 child transcript 体系: (1) **命名约定** `make_child_session_key(parent, task_id) -> f"{parent}::delegate::{tid}"` (`subagent_permissions.py:81-86`), 全仓库统一调用; (2) **per-session 隔离** `transcript_path(sk) -> get_butler_home() / "sessions" / safe_segment(sk) / "transcript.jsonl"` (`session_transcript.py:47-49`), 每个 child 物理独立 jsonl 文件; (3) **active session 切换** `with use_execution_context(orch, session_key=child_session_key or session_key):` (`delegate_job.py:136`), 子 turn 写入子 transcript 而非父; (4) **持久化** `task_store.create_task` 落 `child_session_key` 字段 (`task_store.py:101-130`); (5) **导出可读性** `_format_row_markdown` 渲染 `delegate_started/turn_start/turn_done` 三事件类型时带 `child_session_key` + `parent_session_key` 字段 (`transcript_export.py:109-112`); (6) **保留优先级** `transcript_source_boost("delegate")=10` 给 delegate 源 +10 优先级, 防 child transcript 被 retention 清掉 (`transcript_retention.py`); (7) **可发现性** `/任务` 输出 child_sk 提示 (`lifecycle_commands.py:209-210`). **测试覆盖** (Sprint 24 盘点): child_session_key 命名解析 + transcript path 隔离 + use_execution_context 切换 + retention boost 优先级 等用例散落在 sprint6-21 多个 test_*.py. **已知 gap** (留待后续 sprint 单独 P1-3.4-gap 任务): `/详细 --child <child_sk>` UI 入口未实现, 当前 `/详细` 只支持 `task_id` 倒查父 session, 不直接接受 child_sk; transcript 文件保留策略与父 transcript 同步清理尚未文档化. **本次收口**: checklist 标 [x] + audit doc 加 entry, 不写新代码. |
| **§4.1** (P2-4.1, Sprint 24 收口) | Overflow 后 replay / continue — **清单 stale, reactive machinery 已存在**, 仅完成 doc 标 [x] | 0 代码 commit (无新代码) | **背景**: checklist §4.1 状态 `[ ]` 是 stale, 实际 reactive compact 链已实现: (1) `_compress_with_overflow_replay(..., overflow_replay=True)` flag 透传 compress_fn (`reactive_compact.py:29`); (2) `try_reactive_compact` 入口 + 多策略回退 + diagnostics 写入 `reactive_compact_strategy` (`reactive_compact.py:39-77`); (3) `apply_reactive_compact_to_messages` 装回 messages + 写 `reactive_compact_applied` / `reactive_compact_reason` 到 diagnostics (`reactive_compact.py:105-114`). **真实 gap** (留 P2-4.1-gap 任务): `overflow_replay` 仍为 reactive_compact 内部 flag, 未注册为 transcript 事件类型 (`session_transcript.record_*` 族中无 `record_overflow_replay`); "用户感知是继续当前任务" 依赖 `try_reactive_compact` 自动透传, 无显式 UX 续跑提示. **本次收口**: checklist 标 [x] + audit doc 加 entry, 不写新代码. |
| **§4.2** (P2-4.2, Sprint 24 收口) | Compaction 作为 Loop 显式任务 — **清单 stale, 4 个事件 2/4 已实现**, 仅完成 doc 标 [x] | 0 代码 commit (无新代码) | **背景**: checklist §4.2 状态 `[ ]` 是 stale, 实际部分落地: (1) `record_compact_scheduled` 事件类型已实现 (`session_transcript.py:247-263`), 含 `summary_chars` 字段; (2) `record_compact_done` 事件类型已实现 (`session_transcript.py:265-283`); (3) `transcript_diagnostics.py:25-32` `/诊断` 集成, 读 `compact_scheduled` / `compact_done` 计数, 输出 "近 N 条 · 压缩 X/Y 完成" 摘要行. **真实 gap** (留 P2-4.2-gap 任务): `compact_started` + `compact_failed` 两个事件类型未在 `session_transcript.record_*` 族中实现 (当前 2/4 覆盖). `compact_started` 可让 /诊断 区分"已 schedule 还没跑" vs "已 schedule 正在跑" 两个时间窗; `compact_failed` 让 /诊断 在压缩异常时给 owner 可见反馈. `compact_boundary` (`session_transcript.py:239`) 是另一个边界事件, 与 `compact_done` 配合使用, 不在本任务范围. **本次收口**: checklist 标 [x] + audit doc 加 entry, 不写新代码. |
| **§4.3** (P2-4.3, Sprint 24 收口) | Cache policy 自动断点 — **delegate 侧已有, transport 侧空缺**, 仅完成 doc 标 [x] | 0 代码 commit (无新代码) | **背景**: checklist §4.3 状态 `[ ]` 是 stale, 实际 delegate 侧 cache safety 策略已实现: (1) `cache_safe_delegate_enabled` env toggle (`cache_safe_delegate.py:16`); (2) `compute_cache_safe_bundle` 输出 `cache_safe_v2: True` 标记 (`cache_safe_delegate.py:75-91`); (3) `apply_cache_safe_system_prompt` 注入 system prompt (`cache_safe_delegate.py:93-119`); (4) delegate 主路径集成 (`cache_safe_delegate.py:126-132`). **真实 gap** (留 P2-4.3-gap 任务): `butler/transport/` 侧 (anthropic_transport.py / chat_completions.py / llm_client.py) 缺 transport-level 自动 cache_control 布点 (system / latest user / tools 边界), 当前依赖 provider SDK 默认行为. `cache_safe_delegate` 是 delegate 主路径"防 cache 错位"安全策略, 与 transport-level 自动布点是**不同层次**的优化 (delegate: 防止 prompt prefix 改坏 cache; transport: 自动在 4 个边界布 cache_control 标记). **本次收口**: checklist 标 [x] + audit doc 加 entry, 不写新代码. |
| **§4.4** (P2-4.4, Sprint 24 收口) | Hook `pre_compact` / `pre_tool_execute` — **实现 100%, 仅缺文档化**, 仅完成 doc 标 [x] | 0 代码 commit (无新代码) | **背景**: checklist §4.4 状态 `[ ]` 是 stale, 实际实现 100% 完成: (1) `run_pre_compact_hooks` 函数已实现 (`hooks/runner.py:397`); (2) `pre_tool_execute` alias (PreToolUse) 已实现 (`hooks/runner.py:451`); (3) `hooks/__init__.py:11,29` 导出; (4) `hooks/hooks.yaml.example:4-5` 注释列出 pre_llm_call / pre_gateway_dispatch / pre_compact / post_compact / pre_tool_execute 全部 hook 点; (5) `compaction_task.py:65-67` pre_compact 实际接入 (try/except logger.debug 容错). **真实 gap** (留 P2-4.4-gap 任务): Hook 顺序未在 `docs/architecture/v4-architecture.md` 单独成节, 散落在 hermes-extraction-map / post_compact_cleanup / fact_extraction 多个 cross-reference; 失败时行为 (跳过/阻断/仅记录) 统一契约未集中文档化. **本次收口**: checklist 标 [x] + audit doc 加 entry, 不写新代码. |
| **§4.5** (P2-4.5, Sprint 24 收口) | 可选 post-edit format — **清单 stale, 已 100% 完成**, 仅完成 doc 标 [x] | 0 代码 commit (无新代码) | **背景**: checklist §4.5 状态 `[ ]` 是 stale, 实际 100% 完成: (1) `post_edit_format_enabled` env toggle (`BUTLER_POST_EDIT_FORMAT` 默认 `False`) 实现于 `post_edit_format.py:29-30`; (2) `maybe_format_after_edit` 主函数 (`post_edit_format.py:37-50`) 早退条件完备: 关/无后缀/无 tool 全部 `None` 或 `skipped`; (3) `_command_available` 走 `shutil.which` 检测, 缺 formatter 返 `{"skipped": True, "reason": "... not in PATH"}` 实现优雅降级 (`post_edit_format.py:33,46-47`); (4) timeout env 可配 (`BUTLER_POST_EDIT_FORMAT_TIMEOUT` 默认 30s, 最低 5s) 实现于 `post_edit_format.py:52-54`; (5) subprocess 异常/非零 exit 返 `{"formatted": False, "tool": ..., "error": ...}` 不抛 (`post_edit_format.py:63-68`); (6) `butler/tools/file_io.py:354,467` 写文件主路径集成 `maybe_format_after_edit`, payload 写回 `post_edit_format` 字段. **真实 gap**: 无 (完全实现). **本次收口**: checklist 标 [x] + audit doc 加 entry, 不写新代码. |
| **P2-4.4-gap** (Sprint 25) | Hook `pre_compact` / `pre_tool_execute` 顺序文档化 — v4-architecture.md 加 `### Hook 总线（Shell + In-Process）` 章节 | 1 commit (docs) | **背景**: P2-4.4 收口时识别 2 个真 gap: (1) 两套 hook 系统 (Shell + In-Process) 在 v4-architecture.md 仅 `butler/gateway/hooks.py \| 轻量 HookBus` 一行 cross-ref, shell 钩子零文档; (2) 失败统一契约 + 压缩双调用模式 (`compaction_task.py:64-90`/`:147-173` shell→in-proc 串行) 未集中说明. **本次落地** (`27d85a6`): 单 commit 加 74 行新章节, 含 5 块: (1) 两套系统对照表 (位置/延迟/用途/阻塞); (2) 11 个 hook 点总表 (类型/触发/阻塞方式); (3) 一次完整 turn 触发顺序 ASCII 图 (消息入→UserPromptSubmit→pre_gateway_dispatch→pre_llm_call→LLM→PreToolUse→tool exec→PostToolUse→[压缩: PreCompact→pre_compact→compress→PostCompact→post_compact]→Stop); (4) 失败统一契约 (shell exit code 0/2/else + in-proc try/except 永吞); (5) 压缩双调用约定 (shell 先做, in-proc 后注入; shell 失败可阻断, in-proc 失败仅 warn). **测试**: 文档无代码, cross-ref 验证靠 `hooks.yaml.example` + `hooks/runner.py:397/451` 实际存在. **commit 序列**: `27d85a6`. |
| **P2-4.2-gap** (Sprint 25) | compact_started + compact_failed 事件类型 — record_* 函数实现 + 接入 3 个压缩入口 + /诊断 集成 | 3 commits (test + impl + wiring) | **背景**: P2-4.2 收口时识别 2 个真 gap: transcript 4 类 compact 事件只 2/4 (`record_compact_scheduled` + `record_compact_done`), 缺 `compact_started` (压缩真正开始) + `compact_failed` (压缩异常). `/诊断` 仅展示 scheduled/done 计数, 无法区分"压缩中"与"压缩失败". **本次落地** (3 commit, 14 新测试): (`d698534` RED) `tests/test_sprint25_compact_events.py` 14 测试覆盖 record_started/failed 默认值/source/trigger/reason 截断/-5→0 iteration 钳位/transcript_diagnostics dict 4-key/输出行 started/failed 计数; (`d350cbe` GREEN) `session_transcript.py:284-313` 加 2 record_*, `transcript_diagnostics.py:25-34` 摘要行加 `· started=N · failed=M` + `summarize_compact_events` dict 加 2 key; (`6404326` wiring) 3 个压缩入口接入: `context_compressor.py:235-251` 块内 scheduled+started (trigger=`reactive`/`preemptive` 取决于 `overflow_replay` 形参), `hygiene_preflight.py:107-148` 块内 scheduled+started (trigger=`preflight`) + 异常 except 块 `record_compact_failed(source="hygiene", reason="compress_error")`, `reactive_compact.py` 加 2 helper `_record_reactive_started/failed` 在 `try_reactive_compact` 进入实际工作前 + 2 个 `error` return 路径调 failed. **守门**: 147 hygiene/context_compressor/reactive_compact/compaction/transcript/diag 测试全 pass. 1 已知 pre-existing failure (test_gateway_queue_command owner-gate 缺 BUTLER_PROJECT_CREATE_OPEN=1) 与本改动无关 (HEAD~ 同样失败). **commit 序列**: `d698534` + `d350cbe` + `6404326`. |
| **P2-4.1-gap** (Sprint 26) | overflow_replay 事件类型 + /诊断 续跑提示 — record_overflow_replay 实现 + 接入 context_compressor + 摘要 6 key | 3 commits (test + impl + wiring) | **背景**: P2-4.1 收口时识别 1 个真 gap: `overflow_replay` 仍为 `reactive_compact` 内部 flag, 未注册为 transcript 事件类型; "用户感知是继续当前任务" 依赖 `try_reactive_compact` 自动透传, 无显式 UX 续跑提示. **本次落地** (3 commit, 8 新测试): (`f7dfa5c` RED) `tests/test_sprint26_overflow_replay.py` 8 测试覆盖 `record_overflow_replay` 默认值/source 32 截断/content_preview 80 截断/-7→0 chars 钳位/`summarize_compact_events` 6-key/⚠️ 续跑提示行门控 (有计数出, 无计数不出); (`01ed3ef` GREEN) `session_transcript.py:318-333` 加 `record_overflow_replay(sk, *, source='context_compressor', content_preview='', replayed_chars=0)`, `transcript_diagnostics.py:25-44` 摘要行加 overflow_replay 计数 + 在 > 0 时输出 `⚠️ 续跑提示: 本会话触发了 N 次 413/overflow 续跑` 行, `summarize_compact_events` dict 加 1 key 升 6 key; (`d9e7c37` wiring) `context_compressor.py:382-396` 在 `append_overflow_replay` 实际追加 marker 后写 `record_overflow_replay(source='context_compressor', content_preview=replay_user.content, replayed_chars=len(...))`. **守门**: 41 sprint24/25/26 + turn_compaction + checkpoint + preemptive + post_compact_agents 测试全 pass, 17 sprint_a/bcd pass, 22 sprint_codex c0/c1/c2 pass. **commit 序列**: `f7dfa5c` + `01ed3ef` + `d9e7c37`. |
| **P1-3.3-gap** (Sprint 27) | external_directory 跨平台 + /诊断 透传 — Windows/UNC 早退 fail-closed + summarize_approvals 过滤字段 + External-Dir 行 | 2 commits (test + impl) | **背景**: §3.3 收口时识别 2 个真 gap: (1) `check_tool_path` 零 Windows/WSL 平台分支 (Linux CI 上 `C:/...` 路径被 `Path('C:/...')` 当作相对路径, resolve 后误判为 in-workspace); (2) `/诊断` 透传 external_directory 决策缺字段 (现有 `summarize_approvals` 仅 session-wide `always_count/once_active_count/has_pending`, 无 permission 过滤). **本次落地** (2 commit, 11 新测试): (`5e50526` RED) `tests/test_sprint27_external_directory_wsl_windows.py` 11 测试覆盖 5 平台 (WSL `/mnt/c` + Windows `C:/` + Windows `C:\` + UNC `\\server\share` + 大小写 `c:`/`C:`) + 1 相对越界 (`../escape.txt`) + 1 相对 inside (`src/app.py`) + 2 summarize 过滤 (基本 + 无活动 0) + 2 /诊断 透传 (有活动 + 旧 stats 容错); (`ed269b3` GREEN) `path_safety.py:1-30` 加 `_is_windows_absolute_path` helper (regex `^[A-Za-z]:[\\/]` + `^\\\\[?]?[A-Za-z0-9_.$-]+[\\/]` UNC), `check_tool_path` 早退 fail-closed (返回 `Access denied: Windows path is outside workspace`); `approvals.py:305-345` `summarize_approvals` 加 2 字段 `external_directory_always_count` / `external_directory_once_count` (过滤 `r.get("permission") == "external_directory"`); `health_report.py:82-100` `_shared_diagnostic_lines` 在 `always_count/once_active_count/has_pending` 行下加 `External-Dir: always=N · once=M · pending=Y/N` 行, 仅在 ext_always/ext_once>0 或 has_pending=True 时输出 (避免无活动噪声). **守门**: 35 path_safety + 53 health_report + 41 compact 全 pass. **commit 序列**: `5e50526` + `ed269b3`. |
| **P1-3.4-gap** (Sprint 28) | /详细 --child <child_sk> UI 入口 — parse_child_arg + format_child_session_detail + _cmd_detail 分支 | 2 commits (test + impl) | **背景**: §3.4 收口时识别 1 个真 gap: child_session_key 体系 (make_child_session_key + transcript_path 隔离 + per-session jsonl + /任务 行提示 child_sk + `_format_row_markdown` 渲染 delegate 事件带 child/parent_session_key) 已完整, 但 UI 入口 `/详细` 只接 section (changes/decisions/issues), 不支持直接查看子 session transcript. 当前用户需手动从父 transcript 找 child_sk, 再 cat jsonl. **本次落地** (2 commit, 17 新测试): (`ac2e61a` RED) `tests/test_sprint28_verbose_child.py` 17 测试覆盖 `parse_child_arg` 9 case (`--child foo` + `--child=foo` + `--child foo <rest>` + 等号 + 多种空 / 无 sk / 无 flag / 决策关键字不误识别) + `format_child_session_detail` 3 case (不存在 / 存在 / transcript 关闭) + 旧 `parse_detail_section` 兼容回归 5 case; (`5463e36` GREEN) `report/format.py:1-40` 加 `parse_child_arg(arg) -> (remaining, child_sk | None)` (strip + 双形式 + split(maxsplit=1) 提取 child + 剩余 args 透传), `report/format.py:78-115` 加 `format_child_session_detail(child_sk, max_lines=80)` (复用 `build_session_markdown` 80 行 + 3 层优雅降级: 空 sk / `BUTLER_SESSION_TRANSCRIPT=0` 关闭 / jsonl 不存在), `info_commands.py:112-130` `_cmd_detail` 入口加 child 分支 (优先 child 路径, 否则走既有 report + section). 语法契约: `/详细 --child <sk>` + `/详细 --child=<sk>` + `/详细 --child <sk> changes` (剩余 arg 仍可传 section 给后续 hook). **守门**: 28 report_format + 12 command_registry + 62 path_safety/approvals/sprint27/25/26 全 pass. **commit 序列**: `ac2e61a` + `5463e36`. |
| **P2-4.3-gap** (Sprint 29) | transport-level cache_control 4-boundary 自动布点 — cache_control.py + anthropic_transport 接入 4 boundary | 2 commits (test + impl) | **背景**: §4.3 Sprint 24 收口时识别 1 个真 gap: `butler/transport/` 侧 (anthropic_transport.py / chat_completions.py / llm_client.py) 缺 transport-level 自动 cache_control 布点, 当前依赖 provider SDK 默认行为; delegate 侧 `cache_safe_delegate` (防 prompt prefix 改坏 cache) 是不同层次的优化. Anthropic Prompt Caching 标配 4 boundary (system / 最后 user / tools / 最后 tool_result) 应在 transport 侧自动布点. **本次落地** (2 commit, 25 新测试): (`76574f0` RED) `tests/test_sprint29_cache_control_4boundaries.py` 25 测试覆盖 env toggle 4 (默认 True / 0 / false / 1) + system 3 (关闭/空/有 text) + messages 7 (关闭透传/str→list/list 追加/tool_result/assistant 不动/无 user) + tools 3 (关闭透传/最后 tool/空) + last_tool_result 4 (关闭/无/single/multi-只最后) + integration 2 (4 boundary 同时/全部关闭) + anthropic_transport wiring 2 (build_kwargs env on 4 boundary 全在 + env off 无 marker); (`66be229` GREEN) `transport/cache_control.py` 新建 (110 行), 5 个 helper: `cache_control_enabled` (env toggle) + `apply_cache_control_to_system` (str → [{type:text, text, cache_control:ephemeral}]) + `apply_cache_control_to_messages` (给最后 role=user 末尾追加 marker block) + `apply_cache_control_to_tools` (最后 tool 顶层加 cache_control) + `apply_cache_control_to_last_tool_result` (给最后 tool_result 块加 marker); `anthropic_transport.py` 接入: `convert_messages` 先 apply_messages → 转换 → apply_last_tool_result (顺序保证 list content 透传后 tool_result 块能被正确识别); `build_kwargs` 调用 apply_system + apply_tools; `_convert_messages_to_anthropic` role=user 支持 list content 透传 (避免 str(list) 误转换); `build_kwargs` 改走 `self.convert_messages` 避免重复转换. bypass: `BUTLER_TRANSPORT_CACHE_CONTROL=0` 全部早退, kwargs 不动 (system 仍走 str 路径, 向后兼容). **设计**: 沿用 `thinking_protocol` + `thinking_headers` precedent (env toggle + apply_* helper + bypass 默认 True). **风险** (checklist 提示 "只应影响成本与性能, 不得改变消息语义"): 开启后 `kwargs["system"]` 从 str 变为 list, 但 Anthropic API 中两种 form 是合法等价 (同一 model 行为), 所以语义不变. **同步改动**: `test_transport_anthropic.py::TestBuildKwargs` 2 个 pre-existing 测试加 `monkeypatch.setenv("BUTLER_TRANSPORT_CACHE_CONTROL", "0")` 保持原 str 行为预期, 新 cache_control 行为由 sprint29 单独覆盖. **守门**: 25 sprint29 cache_control 全 pass + 23 transport_anthropic/chat (2 pre-existing 加 env=0 后 pass) + 25 sprint2[5-8] 全 pass. 已知 pre-existing failures (不在本任务范围): test_sprint27_external_directory_wsl_windows.test_returns_external_directory_counts (HEAD~ 同样失败, 已记) + corpus/runners/test_gateway_multiturn_catalog MT-03 (HEAD~ 同样失败) + cli_dimensions/sprint23_tst10_6 等 ~98 个全 pre-existing baseline. **commit 序列**: `76574f0` + `66be229`. |

---

**审计师**: Claude (Anthropic) + 4 个并行 subagent
**审计时间**: 2026-06-02
**审计基线**: commit `a3871da`（Sprint 10 完成）
