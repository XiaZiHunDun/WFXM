# Butler v4 项目深度审计 — Sprint 11（2026-06-02）

**审计方式**: 4 个并行 subagent 独立扫描（security / performance / reliability / test+dead code），主审计师独立 grep/sed 复检 6 项关键发现。

**基线**: Sprint 10 修复 5 CRITICAL（SEC-10-1/2 + REL-NEW-01/02 + PERF-NEW-3） + 删 apprise_adapter.py。本轮独立扫描 Sprint 10 修复后的代码状态。

**总计**: 31 项新发现（13 安全 + 11 性能 + 8 可靠性 + 19 测试/死代码，含 9 项重叠 = 41 项独立）。**Sprint 10 残留 16 项未动**。

---

## Top 10 — 关键发现（建议优先修复）

| # | ID | 位置 | 问题 | 严重 | 工时 |
|---|----|------|------|------|------|
| 1 | ~~TST-11-1~~ | ~~`butler/runtime/approval.py` (140 行)~~ | ~~真死代码（0 importer/0 test）— Sprint 10 REL-NEW-07 描述的代码在此~~ **⚠️ Sprint 11 误报：实为 namespace 引用（service.py:12）** | ~~🔴~~ | ~~10min~~ |
| 2 | **REL-11-1** | `message_handler.py:389,401` | `_idempotency_reserved = False` 提前初始化 → inflight 假阴性泄漏 | 🔴 | 30min |
| 3 | **REL-11-5** | `inbound_idempotency.py:22,79-82` | `inflight` 状态无 TTL/无 sweep → worker 崩溃后永久拒绝 | 🔴 | 1h |
| 4 | **PERF-11-5** | `semantic_index.py:35` | 单 RLock 串行化 9 个方法（search/upsert/delete/count）— 多 session 并发全阻塞 | 🔴 | 2h |
| 5 | **PERF-11-1** | `message_queue.py:167` | 每次 enqueue 全桶 O(N log N) sort — 高 inbound 时线性退化 | 🔴 | 1h |
| 6 | **PERF-11-2** | `exp_cache.py:79-93` | LLM 响应缓存每次 read 全文件 + 逐行 json.loads | 🔴 | 30min |
| 7 | **PERF-11-3** | `exp_cache.py:96-105` | LLM 响应缓存每次 store 写全文件 N 条 | 🔴 | 30min |
| 8 | **SEC-11-1** | `runtime_commands.py:17-75` | `/运行` + `/批准运行` 漏 owner gate | 🟠 | 10min |
| 9 | **SEC-11-2** | `memory_commands.py:86-118` | `/批准记忆 全部` 漏 owner gate → 污染 MEMORY.md | 🟠 | 10min |
| 10 | **SEC-11-3** | `butler_memory.py:239-265` | `ExperienceStore.add` 缺 `_reject_injection` → 注入持久化 sink | 🟠 | 30min |

---

## 1. 安全审计（Security — 13 项）

### 🔴 Sprint 11 必扫（SEC-10 残留 7 项全部未修，参见 Sprint 10 报告 §1）

### 🟠 HIGH — 4 项 owner gate 漏报（同 SEC-10-1 模式）

#### SEC-11-1 `/运行` + `/批准运行` 漏 owner gate
- **位置**: `butler/gateway/runtime_commands.py:17-75`
- **证据**: `/批准运行` 调 `approve_and_run()` → `run_job(force=True, approved_run=True)` 跳过 `approval.approval_required` 守门（service.py:106-115），可执行 `publish-preflight` 类改盘任务。
- **影响**: 任何 `WECHAT_ALLOWED_USERS` 中（不一定是 Owner）的用户都能改盘。

#### SEC-11-2 `/批准记忆` 漏 owner gate
- **位置**: `butler/gateway/memory_commands.py:86-118`
- **证据**: `/批准记忆 全部` (line 94-98) 直接 `pmem.markdown.approve_all()`，无 owner 守门。对比 `lifecycle_commands.py:101` `_cmd_transcript_memory` 有 owner gate。
- **影响**: 非 Owner 白名单用户可永久污染项目 MEMORY.md → 后续进入 LLM 上下文（prompt injection 注入到长期记忆）。

### 🟡 MEDIUM — 4 项

#### SEC-11-3 `ExperienceStore.add` 缺 `_reject_injection`
- **位置**: `butler/memory/butler_memory.py:239-265`
- **证据**: `grep "_reject_injection" butler_memory.py` 只在 line 73/91 (ProfileStore) 出现；line 257 `INSERT INTO experiences` 无过滤。
- **链路**: `butler_remember scope=owner_experience` (`facade.py:444`) → `experience.add()` → SQLite → `search()` 召回 → `format_for_prompt` → LLM context。
- **影响**: 与 SEC-10-6 互补，**完整 prompt-injection 持久化 sink**。

#### SEC-11-4 `/技能 搜索/列表/查看` 漏 owner gate
- **位置**: `butler/gateway/registry_commands.py:109-135`
- **证据**: 3 个 read-only 子命令均无 owner gate；line 129-130 显式"community 源需 Owner 确认" → 实际非 Owner 拿到相同内容。
- **影响**: 第三方恶意 Skill 描述喂回 LLM 形成 prompt injection。

#### SEC-11-5 `/备忘` `/通讯录` `/记账` `/打卡` 漏 owner gate
- **位置**: `butler/gateway/info_commands.py:34-56`（handler 在 `tools/memo.py:337` 等）
- **证据**: 4 命令均无 owner gate；但底层数据 owner-scoped（`memo.py:3-8` 明确 "owner-level"）。
- **影响**: 任何白名单用户可读 Owner 私人数据。

#### SEC-11-6 `/评价` 漏 owner gate
- **位置**: `butler/gateway/outcome_commands.py:8-66`
- **证据**: `handle_outcome_command` 全文 0 处 `is_gateway_owner`；写入 `experiments/outcomes.py`。
- **影响**: 污染实验评估日志，影响后续记忆提炼。

### 🟢 LOW

#### SEC-11-7 `/会话` 信息泄露
- **位置**: `butler/gateway/sessions_commands.py:9-38`
- **证据**: `list_sessions()` 返回全量 session_key（含 chat_id），无 owner gate。

### 模式观察

Sprint 9/10 修复均聚焦 `/config` 一条路径；Sprint 11 仍有 **5 个 owner-gated 改盘命令** + **5 个只读信息命令** 缺守门——**同模式在 6 个新模块复现**。**建议 Sprint 12 引入 CI 静态扫描**: `grep "def handle_.*command\|def _cmd_" + 缺 is_gateway_owner` 报警。

---

## 2. 性能审计（Performance — 11 项新发现）

### 🔴 CRITICAL（4 项）

#### PERF-11-1 `message_queue.enqueue` 全桶 sort
- **位置**: `butler/gateway/message_queue.py:167`
- **证据**:
  ```python
  bucket = _QUEUES.setdefault(key, deque())
  if not _apply_cap_before_append(key, bucket, body):
      return False
  bucket.append(item)
  bucket = deque(sorted(bucket, key=lambda x: _PRIORITY_ORDER.get(x.priority, 9)))  # ← O(N log N) 每条 enqueue
  _QUEUES[key] = bucket
  ```
- **影响**: 每条 inbound 都触发 O(N log N) sort；高 inbound 频率时线性退化。

#### PERF-11-2 `exp_cache.lookup_cached_response` 全文件读
- **位置**: `butler/core/exp_cache.py:79-93, 108-119`
- **证据**:
  ```python
  def _read_entries(path: Path) -> dict[str, dict[str, Any]]:
      if not path.is_file(): return {}
      out: dict[str, dict[str, Any]] = {}
      try:
          for line in path.read_text(encoding="utf-8").splitlines():  # ← 全文件
              line = line.strip()
              if not line: continue
              row = json.loads(line)  # ← 每行 json.loads
              ...
  ```
- **影响**: 每次 LLM 调用都重读全缓存 + 逐行 json.loads。

#### PERF-11-3 `exp_cache` store 写全文件
- **位置**: `butler/core/exp_cache.py:96-105, 142-148`
- **证据**: `_write_entries` → `atomic_write_text` 写全部 N 条；发生在每次成功 LLM 响应后。
- **影响**: 每次成功 LLM 调 = 1 次全文件 fsync。

#### PERF-11-5 `semantic_index` 单 RLock 串行化
- **位置**: `butler/memory/semantic_index.py:35` + 9 处 `with self._lock`
- **证据**: 同一 `self._lock = threading.RLock()` 保护 search/upsert/delete/count/prefetch 全部方法。
- **影响**: 多 session 并发 prefetch 全串行；单 session 内部 `search` 时其他 session 的 `upsert` 阻塞。

### 🟠 HIGH — 3 项

| ID | 位置 | 问题 |
|----|------|------|
| PERF-11-4 | `tool_selector.py:78-84` | tool embed 缓存键用 `hash(text)` 跨进程随机 + 永不 LRU 淘汰 |
| PERF-11-6 | `embedding.py:128-133, 167-172` | embedder 端无 query cache；`semantic_index.search` 每 turn `embed(q)` 重复付费 |
| PERF-11-7 | `agent_loop.py:240, 510` + `tool_batch.py:263-273` | 每 turn 3-5 次 transcript 写（lock+stat+open+write+index update） |

### 🟡 MEDIUM — 4 项

| ID | 位置 | 问题 |
|----|------|------|
| PERF-11-8 | `skill_lock.py:17-28, 37-58` | skill lock 每次操作全读全解析；`list_installed` O(N log N) sort |
| PERF-11-9 | `llm_retry.py` | LLM 路径 14 处无条件 `logger.debug` |
| PERF-11-10 | `tools/expense.py:66,347,355,389` + `contacts.py:63,76` + `habits.py:65,78,120,135` | 工具内 `read_text+json.loads` 无缓存 |
| PERF-11-11 | `core/loop_response.py` / `core/sanitize_response` 等 | 14 个 middleware 都在 LLM 前无脑执行 |

---

## 3. 可靠性审计（Reliability — 8 项新发现）

### 🔴 CRITICAL（2 项）

#### REL-11-1 `_idempotency_reserved = False` 提前初始化
- **位置**: `butler/gateway/message_handler.py:389, 401, 531`
- **证据**:
  ```python
  # line 389
  _idempotency_reserved = False  # ← 提前初始化 False

  try:
      from butler.gateway.bot_loop_guard import record_and_should_suppress
      ...
      if suppress:
          if _idempotency_reserved:  # ← line 401 检查（永远 False）
              try:
                  release_inflight(session_key, external_id)
              except Exception as exc:
                  logger.debug("Inflight release skipped: %s", exc)
  ...
  # line 531 才是真正 reserve 位置
  _idempotency_reserved = True
  ```
- **影响**: 401 行检查永远 False → `release_inflight` 是 no-op → inflight 假阴性泄漏。
- **修复**: 把 `_idempotency_reserved = False` 移到 401 行 try 块之前（紧跟 reserve 调用之后）。或重构为 `try/finally` + 状态变量。

#### REL-11-5 `inbound_idempotency` inflight 状态无 TTL
- **位置**: `butler/gateway/inbound_idempotency.py:22, 79-82`
- **证据**: 全文件 `grep "sweep|TTL|expire"` 0 命中；只 `release_inflight/complete_inbound` 主动解除。
- **影响**: worker 崩溃后 `external_id` 永久 `inflight`，后续同 ID 消息一律 `duplicate_inflight` 拒绝。

### 🟠 HIGH — 4 项

| ID | 位置 | 问题 |
|----|------|------|
| REL-11-2 | `mcp/async_runner.py:11-39` | 守护线程 + 独立 loop，**无 atexit/signal/shutdown** |
| REL-11-3 | `runtime/notify.py:130` | `asyncio.run(send_wechat_direct(...))` 同步路径里跑 |
| REL-11-4 | `gateway/runner.py:38, 100, 190, 204` | SIGTERM 只 `stop.set()`，不等待 executor 排空 |

### 🟡 MEDIUM — 3 项

| ID | 位置 | 问题 |
|----|------|------|
| REL-11-6 | `mcp/manager.py:54-61` | `_handles_for` 锁外返回 live dict |
| REL-11-7 | `human_gate.py:19, 280-300` | `consume_injection_bypass` 跨进程不安全 |
| REL-11-8 | `runtime/audit.py:97` | `release_lock.unlink` 静默吞咽 OSError |

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
| TST-11-2 | `wechat_ilink.py:158,1042,1058` `_LIVE_ADAPTERS` | 0 race test |
| TST-11-3 | `lifecycle_commands.py` 234 行 | coverage 21%；11 handler 仅 `_cmd_config` 测 (✅ `6fddada` 补 41 测试：/doctor×5 /export×2 /回滚×5 /分叉×6 /会话记忆×6 /确认安装×2 /注册表×2 /任务×4 /工作流×2 /_require_owner×2 /静态契约×4) |
| TST-11-5 | `execute_code.py:52-116` `run_execute_code` | 1 unit test (disabled 路径)；0 真实 subprocess |
| TST-11-9 | `mcp/{client_http,client_stdio,server_stdio}.py` | 三文件 0%；mcp 子包覆盖极薄 |
| TST-11-10 | `wechat_ilink.py:1720-1737` `_download_remote_media` SSRF | 0 e2e with redirector/IPv6/0.0.0.0 |

### 🟡 MEDIUM

| ID | 位置 | 问题 |
|----|------|------|
| TST-11-4 | `handler_helpers.py:376` `_WELCOMED_SESSIONS` | race test 不全 |
| TST-11-6 | `__init__.py:55-57, 60-63` | `format_build_identity_line` / `mark_start_time` 0% |
| TST-11-7 | `agents_md.py:80-88` | `list_agent_md_names` 0% |
| TST-11-11 | `runtime/{audit,loader,schedule}.py` | 0 直测；Sprint 10 REL-NEW-01 修的 flock 锁内容无独立 race test |

### 🟢 LOW

| ID | 位置 | 问题 |
|----|------|------|
| TST-11-8 | `cli/doctor.py` 60 行 | 整文件 0 测试 |

### Sprint 10 残留（8 项，全部未修）

| ID | 问题 | 严重 |
|----|------|------|
| TST-10-2 | `tenant_store.py TenantStore` 0 直测 | 🟠 |
| TST-10-3 | `extract_layered_summary` 0 直测 | 🟠 |
| TST-10-4 | `atomic_write.atomic_write_text` 0 直测 | 🟠 |
| TST-10-5 | 28 个 `CommandDef` 缺 handler | 🟠 |
| TST-10-6 | MagicMock 99.6% 无 `spec=` | 🟡 |
| TST-10-7 | `test_gateway_handler.py` 18/59 unique commands | 🟡 |
| TST-10-8 | `wechat_ilink.py` 2027 行仍在 coverage omit | 🟠 |
| TST-10-9 | Sprint 9 报告口径过期 | 🟢 |

---

## 5. 修复建议

### 短期（7🔴 = 1 个工作日）
1. **TST-11-1** 删 `runtime/approval.py`（10min + 测试，含消化 REL-NEW-07）
2. **REL-11-1** `_idempotency_reserved` 初始化位置修复（30min + 测试）
3. **REL-11-5** inflight TTL/sweep（1h + 测试）
4. **PERF-11-1** message_queue sort 优化（1h + 测试）
5. **PERF-11-2/3** exp_cache 改为 SQLite 或 mmap（30min + 测试）
6. **PERF-11-5** semantic_index 拆 read/write lock（2h + 测试）

### 中期（owner-gate 6 项 = 2h）
- **SEC-11-1/2/4/5/6/7** 6 个命令加 owner gate + 引入 CI 静态扫描

### 长期（性能 + 测试 = 5 天）
- PERF-11-4/6/7/8/9/10/11
- TST-10-2/3/4/5/7/8/9

---

## 6. Sprint 11+ 修复记录

| ID | 修复 | Commit | 备注 |
|----|------|--------|------|
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

---

**审计师**: Claude (Anthropic) + 4 个并行 subagent
**审计时间**: 2026-06-02
**审计基线**: commit `a3871da`（Sprint 10 完成）
