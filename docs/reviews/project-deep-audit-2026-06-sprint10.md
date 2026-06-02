# Butler v4 项目深度审计 — Sprint 10（2026-06-02）

**审计方式**: 4 个并行 subagent 独立扫描（security / performance / reliability / test+dead code），主审计师独立 grep/sed 复检 CRITICAL 项。

**基线**: Sprint 9（2026-06-01）修复 5 CRITICAL（SEC-9.1/9.5 + REL-9/10/11） + 删 1070 行死代码（3 文件）。本轮独立扫描 450 Python 文件 + 274 测试文件。

**总计**: 48 项独立发现（含 4 项 Sprint 9 漏报/未落地）。

---

## Top 10 — 关键发现（建议优先修复）

| # | ID | 位置 | 问题 | 严重 | 工时 |
|---|----|------|------|------|------|
| 1 | **SEC-10-1** | `gateway/commands/lifecycle_commands.py:145-163` | `/config set` slash 命令旁路 owner gate（Sprint 9 SEC-9.5 漏报） | 🔴 | 10min |
| 2 | **PERF-NEW-3** | `transport/llm_client.py:84-94, 109-119` | OpenAI/Anthropic client 缺 `max_retries=0` — **Sprint 9 修复未落地** | 🔴 | 10min |
| 3 | **REL-NEW-01** | `durable_outbox.py:77,100` + `audit.py:84,102` + `install_pending.py:71` | 3 处 `flock` 路径缺 `O_NOFOLLOW` → symlink bypass，Sprint 9 锁修复打折 | 🔴 | 30min |
| 4 | **SEC-10-2** | `tools/document_reader.py:40` | `convert_document` 路径未经 `check_tool_path` → /etc/passwd 等任意可读 | 🔴 | 30min |
| 5 | **REL-NEW-02** | `gateway/durable_outbox.py:136,147` | `_transition_outbox_entry` 读取在写锁外 → 状态错乱/重复发送 | 🟠 | 30min |
| 6 | **REL-NEW-06** | `gateway/message_queue.py:324-346` | `_persist_remove` RMW 无锁 → 并发 pop 丢消息 | 🟠 | 1h |
| 7 | **REL-NEW-07** | `runtime/approval.py:61,89-99` | `consume_approval` RMW 无锁 → approval 双重消费 | 🟠 | 30min |
| 8 | **TST-10-1** | `gateway/platforms/apprise_adapter.py` (105 行) | 0 生产引用 → 整模块死代码（同时消化 SEC-9.2） | 🟠 | 10min |
| 9 | **SEC-10-3** | `gateway/platforms/apprise_adapter.py:60-95` | Sprint 9 SEC-9.2 报"已修"，实际未脱敏 PII（与 #8 同源） | 🟠 | 见 #8 |
| 10 | **PERF-NEW-NEW-1** | `memory/semantic_index.py:162-238` | O(N) Python-loop cosine + 1M float ops/recall → 召回慢 | 🟠 | 4h |

---

## 1. 安全审计（Security — 10 项）

### 🔴 CRITICAL

#### SEC-10-1 `/config set` slash 命令旁路 owner gate（Sprint 9 漏报）
- **位置**: `butler/gateway/commands/lifecycle_commands.py:145-163`
- **证据**:
  ```python
  def _cmd_config(ctx: CommandContext) -> Optional[str]:
      from butler.config_service import config_set, ...
      ...
      if sub == "set":
          kv = sub_arg.split(maxsplit=1)
          if len(kv) == 2:
              result = config_set(kv[0], kv[1])  # ← 无 is_gateway_owner
  ```
- **影响**: Sprint 9 SEC-9.5 只修了 `tools/config_tools.py`（tool action="set" 路径），slash 命令入口未同步。Prompt 注入 → `/config set BUTLER_LOG_LEVEL DEBUG` / `/config set BUTLER_WEB_SEARCH_TIMEOUT 99999` 即可改运行时配置 + 阻塞 session。
- **修复**: 在 `_cmd_config` `sub=="set"` 分支 + `_cmd_config` 同文件其他 `_cmd_revert/_cmd_fork` 同款 `is_gateway_owner(platform=ctx.platform, external_id=ctx.external_id, session_key=ctx.session_key)` 校验。

#### SEC-10-2 `read_document` 路径遍历（新发现）
- **位置**: `butler/tools/document_reader.py:40`
- **证据**:
  ```python
  def convert_document(path: str, *, max_chars: int = _MAX_OUTPUT_CHARS) -> dict[str, Any]:
      p = Path(path).expanduser().resolve()  # ← 无 check_tool_path
      if not p.is_file():
          return {"error": f"File not found: {path}"}
  ```
  全文 0 个 `check_tool_path` 调用。
- **对比**: `_tool_terminal/_tool_search_files/_tool_list_directory/_tool_write_file` 全部走 `tools/path_safety.py:106` 的 `check_tool_path`，唯独 `read_document` 例外。
- **影响**: 支持 .pdf/.docx/.html/.csv/.json/.xml/.zip/.epub —— prompt 注入可读 `/etc/passwd`、`~/.aws/credentials`、SSH 私钥、Sprint 6 path_safety 修过的所有路径再次沦陷。
- **修复**: 在 `convert_document` 起手处 `check_tool_path(p, "read_document")`，复用现有守门。

### 🟠 HIGH

#### SEC-10-3 apprise 出站 PII 未脱敏（Sprint 9 SEC-9.2 误报"已修"）
- **位置**: `butler/gateway/platforms/apprise_adapter.py:60-95`
- **证据**: `grep "scrub" apprise_adapter.py` = 0 命中；`send_notification` line 83-87 `ap.notify(body=body, ...)` 原样发。
- **对比**: `wechat_ilink:1921` / `outbound_bridge:382` / `completion_notify:280` 都调 `scrub_outbound_text`，apprise 例外。
- **关联**: 与 TST-10-1（apprise 整模块 0 生产引用）同源 —— 删模块即消化此项。

#### SEC-10-4 web_search/web_fetch timeout 无上限
- **位置**: `tools/web_search.py:30` + `tools/web_fetch.py:29`
- **证据**: `max(3.0, float(...))` 仅下限，无上限。`_MUTABLE_KEYS` 含 `BUTLER_WEB_SEARCH_TIMEOUT/15` 与 `BUTLER_WEB_FETCH_TIMEOUT/20` (config_service.py:58/62)。
- **影响**: 配合 SEC-10-1 → prompt 注入 + `/config set BUTLER_WEB_SEARCH_TIMEOUT 99999` → 阻塞 27h。

#### SEC-10-5 io_guardrail tripwire 零审计
- **位置**: `butler/core/io_guardrail.py:39-75` + `butler/gateway/message_handler.py:294-295`
- **证据**: tripwire 检测 secret/pii 模式全程 0 logger / 0 transcript entry。`injection_score` 走 `append_transcript_entry` (line 326-336)，tripwire 漏。
- **影响**: 攻击者反复试探 secret pattern 无痕迹。

### 🟡 MEDIUM

#### SEC-10-6 butler_remember 入库未脱敏
- **位置**: `butler/memory/facade.py:385-402` `_remember`
- **证据**: 只剥 `<private>` 标签，未调 `scrub_outbound_text`。
- **影响**: content 永久进 FTS5 + 向量，recall 时反复召回 PII。

#### SEC-10-7 MCP `_expand_env` 跳过 protected check
- **位置**: `butler/mcp/config.py:75-82`
- **证据**: `re.sub(r"\$\{(\w+)\}", lambda m: os.getenv(m.group(1), ""), ...)` 不验证 key 是否在 `_PROTECTED_ENV_KEYS`。
- **影响**: `mcp.yaml` 写 `env: {X: "${PATH}"}` 注入 PATH 字符串到配置 dict。

#### SEC-10-8 hooks stdin/env 截断不一致
- **位置**: `butler/hooks/runner.py:519,526`
- **证据**: `BUTLER_HOOK_INPUT: stdin_json[:8000]` 截断；`input=stdin_json` 完整未截断。
- **影响**: 1MB butler_remember content 可让 hook 脚本 OOM。

#### SEC-10-9 静态审计漏扫 MCP stdio allowlist
- **位置**: `butler/ops/security_audit.py`
- **证据**: 检查 HTTP_HOSTS_ALLOW / ALLOW_PRIVATE，未检查 `BUTLER_MCP_STDIO_ALLOW_COMMANDS`。
- **影响**: 运维设 `=bash,sh,curl` 后，配合 LLM 生成的 args 走 `bash -c` 任意执行。

### 🟢 LOW

#### SEC-10-10 module-load 注册模式 CI 缺扫
- **位置**: `gateway/commands/{lifecycle,dialog,info}_commands.py` 末尾 `for _cmd in _X_COMMANDS: register(_cmd)`
- **建议**: CI 加 `grep -n "^\s*for\b.*register" butler/` 全量扫描，防止再现"看似死代码实则注册"漏判。

---

## 2. 性能审计（Performance — 9 项）

### 🔴 CRITICAL

#### PERF-NEW-3（Sprint 9 修复未落地）
- **位置**: `butler/transport/llm_client.py:84-94, 109-119`
- **证据**: 全文 0 处 `max_retries` 参数。
  ```python
  self._client = OpenAI(
      api_key=api_key,
      base_url=self._base_url,
      timeout=self.timeout,
  )  # ← 无 max_retries=0
  ```
- **影响**: OpenAI SDK 默认 2 次重试 × `llm_retry` 3 次 = 单次最坏 6 次 + 90s stale → **20+ 分钟抖动仍存在**。
- **修复**: 加 `max_retries=0`。

### 🟠 HIGH

| ID | 位置 | 问题 |
|----|------|------|
| PERF-10-1 | `memory/semantic_index.py:162-238` `search()` | O(N) Python-loop cosine：1000 行 = 1000 json.loads + 1M float ops/recall。无索引 |
| PERF-10-2 | `memory/butler_memory.py:605-628` `sync_profile_vectors()` | `delete_source_prefix` + 全量重建：O(N²) 向量 upsert |
| PERF-10-3 | `gateway/durable_outbox.py:185-199` `outbox_counts()` | 3 状态目录 × N 文件 + `json.loads`，/health 每次都付 600 json.loads |
| PERF-10-4 | `core/session_transcript.py:46-58` + `transcript_index.py:43-68` | 每条 append：4 disk I/O；单 turn 5+ 条 = 15+ I/O；index 写还是裸 write_text |
| PERF-10-5 | `memory/vector_store.py:166-169,188-219` `InMemoryVectorStore` | fallback 路径全量重写 + brute-force cosine |
| PERF-10-6 | `runtime/push_queue.py:42-58,60-68` | enqueue = 2 次 fsync 全文件（atomic_write + `_trim_queue`） |

### 🟡 MEDIUM

#### PERF-10-7 `notify.push_runtime_message` 在同步路径里 `asyncio.run`
- **位置**: `butler/runtime/notify.py:130-137`
- **影响**: drain_push_queue 同步路径里 `asyncio.run(send_wechat_direct...)`；未来 drain async 化将 RuntimeError。

#### PERF-10-8 `gateway/runner._run_in_worker` 超时不杀线程
- **位置**: `butler/gateway/runner.py:99-102`
- **影响**: `wait_for(run_in_executor)` 取消 awaitable，executor 内继续跑；socket 持有 30s+。

---

## 3. 可靠性审计（Reliability — 15 项）

### 🔴 CRITICAL

#### REL-NEW-01 3 处 `flock` 缺 `O_NOFOLLOW` → symlink bypass
- **位置**:
  - `butler/gateway/durable_outbox.py:77,100`
  - `butler/runtime/audit.py:84,102`
  - `butler/registry/install_pending.py:71`
- **证据**:
  ```python
  fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)  # ← no O_NOFOLLOW
  ```
- **影响**: 攻击者/前序进程预置 symlink → lock 落在宿主文件，后续 `os.replace` / `write` 改写非预期目标。Sprint 9 REL-10 修复（process token）打折。
- **修复**: 三处都加 `os.O_NOFOLLOW`，并 catch `OSError` → False/return。

### 🟠 HIGH

#### REL-NEW-02 `_transition_outbox_entry` 读在写锁外（TOCTOU）
- **位置**: `butler/gateway/durable_outbox.py:136-147`
- **证据**:
  ```python
  def _transition_outbox_entry(entry_id, *, target_state, ...):
      ...
      row = json.loads(pending.read_text(...))  # ← line 136 读，无锁
      ...
      with _outbox_write_lock():                # ← line 147 写锁
          _write_entry(pending, row)
          pending.replace(target)
  ```
- **影响**: 并发 `mark_delivered` + 周期性 `_recover_orphans` → 同一条 outbox 被改写回 `pending` / 重复发送。

#### REL-NEW-03 `wechat_ilink._LIVE_ADAPTERS` 无锁
- **位置**: `butler/gateway/platforms/wechat_ilink.py:158,1042,1058,1956`
- **影响**: 跨 cron / gateway / signal handler 读写同一 dict，`disconnect` + `connect` 非原子 → adapter 引用泄露 / 双连接。

#### REL-NEW-04 `interruptible_client._worker` 线程泄漏
- **位置**: `butler/transport/interruptible_client.py:29-50`
- **影响**: 用户连续 Esc 取消 → daemon 线程继续持 httpx socket 30s+。

#### REL-NEW-05 `mcp/manager._handles_for` 锁外返回 live dict
- **位置**: `butler/mcp/manager.py:54-61`
- **影响**: 多 session 并发初始化同一 scope → `RuntimeError: dictionary changed size during iteration`。

#### REL-NEW-06 `message_queue._persist_remove` RMW 无锁
- **位置**: `butler/gateway/message_queue.py:324-346`
- **证据**: 字符串匹配 `'"id": "{persist_id}"'` 重写全文件，无 flock；marker 还会误中前缀 ID。
- **影响**: 双进程 gateway / 重连风暴 → inbound 丢失 / 重复消费。

#### REL-NEW-07 `consume_approval` RMW 无锁
- **位置**: `butler/runtime/approval.py:61,89-99`
- **证据**: `grant_approval` 裸 `write_text`；`consume_approval` 读+改+写无锁。
- **影响**: Web UI 与 CLI 同时审批 → approval 双重消费 → 危险操作被绕过。

### 🟡 MEDIUM

| ID | 位置 | 问题 |
|----|------|------|
| REL-NEW-08 | `gateway/runner.py:99-115` | handler 超时不杀工作线程 → executor 耗尽 |
| REL-NEW-09 | `mcp/async_runner.py:11-39` | 无 atexit cleanup → MCP stdio 进程泄漏 |
| REL-NEW-10 | `runtime/notify.py:57` | `_write_last_push_monotonic` 裸 `write_text` |
| REL-NEW-11 | `butler/human_gate.py:280-300` | `consume_injection_bypass` 跨进程不安全 |
| REL-NEW-12 | `runtime/failure_tracker.py:44,64-83` + `permissions/approvals.py:79` | 同 REL-13 裸 write_text + RMW 模式 |

### 🟢 LOW

| ID | 位置 | 问题 |
|----|------|------|
| REL-NEW-13 | `wechat_ilink.py:307-379` + `gateway/platforms/helpers.py:24-42` | TypingTicketCache / MessageDeduplicator 无锁 |
| REL-NEW-14 | `wechat_ilink.py:1057-1083,1139-1141` | `disconnect` vs `poll_loop` 取消竞态 |
| REL-NEW-15 | `gateway/inbound_idempotency.py:94` | "inflight" 状态无超时回收 |

---

## 4. 测试缺口 + 死代码（Test/Dead Code — 9 项）

### 🟠 HIGH

#### TST-10-1 死代码：`gateway/platforms/apprise_adapter.py` 整模块 105 行
- **证据**: `grep -rn "from butler.gateway.platforms.apprise_adapter" butler/` = 0 命中；`platforms/__init__.py:3` 只 export `WeChatAdapter`；apprise 只被 `tests/test_dependency_extras.py` 引用。
- **建议**: 整文件删除，同时消化 SEC-10-3（apprise PII）和 Sprint 9 SEC-9.2 误报。

#### TST-10-2 `butler/tools/tenant_store.py:18` `class TenantStore` 0 直接测试
- **证据**: `grep -rln "TenantStore\|from butler.tools.tenant_store" tests/` = 0 命中。
- **影响**: Sprint 9 §5.11 报 33.3% 是错估，实际 0%。

#### TST-10-3 `extract_layered_summary` 0 直接测试
- **位置**: `butler/session/post_session_layered.py:32`
- **证据**: 2 个生产调用（`cli/sessions_cli.py:125` + `session/post_session.py:254`），但 `grep "extract_layered_summary" tests/` 只命中 docstring/import；唯一测试 `test_post_session_layered_disabled_by_default` 只测 env 开关。
- **影响**: 核心 async 抽取逻辑 + JSON 解析容错 0 测。

### 🟡 MEDIUM

#### TST-10-4 `butler/io/atomic_write.py` 12 importers / 0 直接测试
- **证据**: `tests/test_sprint8_rel3_atomic_write.py` 只测 `atomic_json_write` wrapper。
- **缺**: encoding 错 / fsync 验证 / 0o600 perm 拒绝 case。

#### TST-10-5 29 个 `CommandDef` 重复注册（覆盖语义不明）
- **位置**: `command_registry.py:133-197`（60 个无 handler）+ `commands/{dialog,info,lifecycle}_commands.py`（31 个有 handler）
- **证据**: `_register_defaults()` 顶层 + `message_handler.py:975` 触发 3 子模块 → **31 个同名字段被静默覆盖**。
- **影响**: `tests/test_command_registry.py` 0 case 断言"每 name 最多一个 CommandDef"。

#### TST-10-6 `MagicMock` 99.5% 无 `spec=`
- **证据**: `grep "MagicMock(" tests/` = 373 命中，`spec=` 仅 2 命中（`test_dev_commands.py:453,475`）。

### 🟢 LOW

| ID | 位置 | 问题 |
|----|------|------|
| TST-10-7 | `test_gateway_handler.py` | 60 个 default name 的 dispatch 路径 0 e2e case |
| TST-10-8 | `wechat_ilink.py` 2027 行 | 仍在 `pyproject.toml:111` omit（TST-13 未修） |
| TST-10-9 | Sprint 9 TST-2 报告口径过期 | 实测当前 0 缺 script（实际已被合并/补全静默修） |

---

## 5. Sprint 9 修复后副作用确认

✅ **REL-9 outbox writer LOCK_EX**：短持锁，无副作用。但 `enqueue` + `mark_sent` 路径走 2 次 LOCK_EX，可优化为单锁事务。
✅ **REL-10 audit lock process token**：复检 `release_lock` 在 `unlink` 前 split + pid+token 校验，无副作用。
✅ **REL-11 install_pending LOCK_EX**：短持锁，无副作用。
✅ **SEC-9.5 config tool owner gate**：`is_gateway_owner` 3 次 getenv，非热路径，无副作用。**但 SEC-10-1 揭示 slash 命令路径未修。**
❌ **PERF-NEW-3 max_retries=0**：**未落地**！全文 0 处 `max_retries`。
❌ **SEC-9.2 apprise PII**：报告标"已修"，实际全文 0 处 `scrub`。

---

## 6. 修复建议

### 短期（5🔴 + 1🟠 死代码 = 1 个工作日）
1. **SEC-10-1** `/config` slash owner gate（10min + 测试）
2. **PERF-NEW-3** `max_retries=0` 落地（10min + 测试）
3. **REL-NEW-01** 3 处 `O_NOFOLLOW`（30min + 测试）
4. **SEC-10-2** `read_document` `check_tool_path`（30min + 测试）
5. **REL-NEW-02** `_transition_outbox_entry` 整体进锁（30min + 测试）
6. **TST-10-1** 删 `apprise_adapter.py`（10min + 测试）

### 中期（3🟠 数据安全 = 2 天）
- **REL-NEW-06** `message_queue` flock 化
- **REL-NEW-07** `approval` flock 化
- **REL-NEW-12** `failure_tracker` + `permissions/approvals` flock 化
- **SEC-10-4** web_search/web_fetch timeout 上限

### 长期（性能 + 测试 = 5 天）
- **PERF-10-1** `semantic_index` 索引化
- **PERF-10-2** `sync_profile_vectors` 增量化
- **TST-10-2/3** `TenantStore` + `extract_layered_summary` 直测

---

**审计师**: Claude (Anthropic) + 4 个并行 subagent
**审计时间**: 2026-06-02
**审计基线**: commit `ae3c485`（Sprint 9 完成）
