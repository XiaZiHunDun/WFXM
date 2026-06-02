# Butler v4 项目深度审计 — Sprint 9 (2026-06)

> 范围：Sprint 8 修复 6 项（SEC-2/3/5/6 + REL-2/3）**之后**剩余的真实问题。
> 上游：`project-deep-audit-2026-06.md`（Sprint 7）+ `project-deep-audit-2026-06-sprint8.md`
> 流程：4 个并行 subagent 扫描（安全 / 性能 / 可靠性 / 测试）→ 复检人对 5 个 CRITICAL 项逐个 grep/sed 取证 → 归档。

## 0. 审计元信息

- **执行时间**: 2026-06-02
- **执行方式**: 4 subagent 并行 + 复检人对 CRITICAL 项逐一 grep 取证
- **依赖前置**: Sprint 8 全部 6 项修复已 commit（6 commit + 1 audit doc，已推 origin/main）
- **基线**: pytest 2850+ 通过 / 78 预存在失败（corpus L1 utterance：45 缺失 script + 1 flaky runner + 1 profile 组装 + 31 其他）

## 1. 总体结论

### 1.1 项目总评

Sprint 8 修掉 6 项典型一阶问题后，剩余项集中在**三个深层共因 + 一个新维度**：

1. **配置面 = 攻击面（升级）** — Sprint 8 修了 owner_gate / approvals，但 `butler_config` 写路径仍无 owner 鉴权；`_MUTABLE_KEYS` 实际注册了 **5 个安全类 key + 3 个 dev 类 key = 8 个**（Sprint 8 报的是 4 个，漏了 `BUTLER_TERMINAL_DANGER_CHECK` 与 dev 类 3 个）。
2. **写路径缺乏真·原子 + 真·锁（恶化）** — Sprint 8 REL-2/3 只修了 outbox 读路径 + `atomic_json_write`；writer 路径 + 18+ 其他工具文件仍裸 `write_text`；`runtime/audit.try_acquire_lock` 锁内容只写 `time.time()`，stale takeover 后原 owner release 会 unlink 新 owner 的锁 → **实际不互斥**。
3. **可观测性塌方（持续）** — `/health` 仍不报 outbox pending、circuit-breaker、daemon 线程、idempotency 命中率；tripwire 事件无审计行。
4. **死代码污染仓库（新维度）** — Sprint 8 TST-1（`inbound_pipeline.py` 453 行）揭开更深问题：累计 6 个模块共 **1553 行 / 30 def/class 0 importer**（`turn_runner.py` / `runtime/schedule.py` / `core/loop_turn.py` / `commands/{lifecycle,dialog,info}_commands.py`），全部 0 测试。

### 1.2 风险分布（80 项去重后）

| 维度 | CRITICAL | HIGH | MEDIUM | LOW | 小计 |
|------|---------:|-----:|-------:|----:|-----:|
| 安全 | 2 | 2 | 4 | 2 | 10 |
| 性能 | 0 | 3 | 7 | 1 | 11 |
| 可靠性 | 3 | 6 | 8 | 1 | 18 |
| 测试缺口 | 0 | 6 | 6 | 1 | 13 |
| 死代码 (去重 TST-1) | — | 6 文件 | — | — | 6 文件 / 1553 行 |
| **合计** | **5** | **17** | **25** | **5** | **52 项** + **6 文件死代码** |

### 1.3 5 个 CRITICAL 项（已逐一 grep 取证）

| ID | 位置 | 问题 | 证据 |
|----|------|------|------|
| SEC-9.1 | `config_service.py:65-81` | `_MUTABLE_KEYS` 实际注册 5 个安全类 key（Sprint 8 漏报 1：`BUTLER_TERMINAL_DANGER_CHECK`）+ 3 dev 类，共 8 个 key 可被 `butler_config` 运行时关 | line 65-69 5 个安全 + line 76-81 3 个 dev（`BUTLER_ENABLE_TERMINAL` / `BUTLER_ENABLE_GIT_PUSH` / `BUTLER_EXECUTE_CODE`） |
| SEC-9.5 | `tools/config_tools.py:42-49` | `tool_butler_config(action="set")` 无 `is_gateway_owner` 校验，**任何 Agent 都能 set 上述 8 个 key** | `grep "is_gateway_owner" config_tools.py` 0 命中；`config_set`（`config_service.py:138`）也无 |
| REL-9 + Sprint 8 REL-1 | `durable_outbox.py:45-47 + 94 + 117-118` | Sprint 8 REL-2 修的是 reader LOCK_SH；writer 路径 `_write_entry` 仍是裸 `path.write_text` 无 flock/fsync；docstring 谎称 "Writers use LOCK_EX" 实际无 | `_write_entry` line 45-47；`enqueue` line 94；`_transition` line 117-118 |
| REL-10 | `runtime/audit.py:59-93` | `try_acquire_lock` 锁内容只写 `time.time()`（line 90），**无 PID/token**；`release_lock` 不验证持有者 → stale takeover 后原 owner release 会 unlink 新 owner 的锁 → **实际不互斥** | line 90 `os.write(fd, str(time.time()).encode("utf-8"))`；`release_lock` line 96-99 仅 unlink |
| REL-11 | `registry/install_pending.py:89-99 + 120` | `get_pending` 是"读"路径却 `_save_all` 写盘清理过期项（line 95-99）；`save_pending` 走 `_save_all` 裸 `write_text`（line 120），并发 save 互相覆盖 | `get_pending` 末尾 `self._save_all(self._load())`；`_save_all` line 50 裸 write |

### 1.4 优先修复 Top 10（按 ROI 排序）

| 序 | 维度 | ID | 严重 | 位置 | 一句话 | 修复成本 |
|---|------|----|------|------|--------|---------|
| 1 | 安全 | SEC-9.1 + Sprint 8 SEC-1 | 🔴 | `config_service.py:65-81` | 8 个 key 全部从 `_MUTABLE_KEYS` 移出；保留写入白名单需 owner 二次确认 | 低 |
| 2 | 安全 | SEC-9.5 | 🔴 | `tools/config_tools.py:42-49` | `config_set` 入口加 `is_gateway_owner` 二次校验（即使白名单也强制 owner） | 极低 |
| 3 | 可靠性 | REL-9 + Sprint 8 REL-1 | 🔴 | `durable_outbox.py:45-118` | writer 加 `flock(LOCK_EX)` + `_write_entry` 改 `atomic_write_text` | 低 |
| 4 | 可靠性 | REL-10 | 🔴 | `runtime/audit.py:59-93` | 锁内容存 `os.getpid() + random_token`；`release_lock` 先 stat 验证 token | 中 |
| 5 | 可靠性 | REL-11 | 🔴 | `registry/install_pending.py` | `get_pending` 改名 `_load_purge_in_place`；`_save_all` 改 `atomic_write_text` | 低 |
| 6 | 测试 | TST-9-12 | 🟠 | 6 文件 1553 行死代码 | 决定删 / 接管；与 Sprint 8 TST-1 (inbound_pipeline) 同源问题集中处理 | 低（删）/ 中（补测） |
| 7 | 测试 | TST-2 | 🟠 | `gateway_scripts.py` 缺 45 个 script | 补 `script_profiles()` 缺失的 45 个定义 → 抹平 78 预存在失败 | 中 |
| 8 | 测试 | TST-13 | 🟠 | `pyproject.toml:111` wechat_ilink omit | 移除 omit + 补 4 个 e2e（覆盖 Sprint 7/8 4 个 iLink 修复） | 中 |
| 9 | 安全 | SEC-9.2 + 9.3 | 🟠 | `apprise_adapter.py:60-95` + `platforms/base.py:125` | apprise `send_notification` + 错误回显统一走 `scrub_outbound_text` | 低 |
| 10 | 性能 | PERF-NEW-1 + NEW-3 | 🟠 | `core/exp_cache.py` + `transport/llm_client.py:84,109` | exp_cache 内存化（启动 load + debounce 写回）；OpenAI `max_retries=0` 避免与 `llm_retry` 叠层 60-90s | 中 |

### 1.5 推荐下一步

- **短期（5-10 天）**：先修 5 个 CRITICAL + TST-9-12 死代码（6-1 集中判定删除/接管）— 共 6 项
- **中期**：SEC-9.2/9.3（PII 扩展）、TST-2（抹平 78 失败）、TST-13（wechat 回归保障）
- **长期**：性能 11 项（连接池 / 缓存 / 异步化）、可观测性（/health 完善）
- 仍有 25 MEDIUM + 5 LOW + 16 Sprint 8 旧未修项 归入 Sprint 10 候选

## 2. 安全维度（Sprint 9）

### 2.1 [🔴 CRITICAL] SEC-9.1 `_MUTABLE_KEYS` 漏列 1 个 + 漏算 3 dev 类共 8 key 可关

- **位置**: `butler/config_service.py:65-81`（注册）+ `:138`（写入 `os.environ`）
- **Sprint 8 SEC-1 复检**：Sprint 8 报"4 个安全类 key"，实际是 5 个：line 65-69 列出 `BUTLER_DOOM_LOOP_THRESHOLD` / `BUTLER_DOOM_LOOP_MODE` / `BUTLER_TERMINAL_DANGER_CHECK` / `BUTLER_IO_GUARDRAIL` / `BUTLER_READ_BEFORE_EDIT`。
- **dev 类也漏了**：line 76-81 还有 `BUTLER_ENABLE_TERMINAL` / `BUTLER_ENABLE_GIT_PUSH` / `BUTLER_EXECUTE_CODE` — 全部注册在 `_MUTABLE_KEYS`。
- **合计 8 个 key** 可被 `butler_config` 工具运行时关。
- **证据**:
  ```python
  # line 65-69
  _register("BUTLER_DOOM_LOOP_THRESHOLD", "安全", ..., "3", vtype="int")
  _register("BUTLER_DOOM_LOOP_MODE", "安全", ..., "block", vtype="str")
  _register("BUTLER_TERMINAL_DANGER_CHECK", "安全", "终端危险命令检测", "1")
  _register("BUTLER_IO_GUARDRAIL", "安全", "入站明文密钥/过长消息检测", "1")
  _register("BUTLER_READ_BEFORE_EDIT", "安全", "编辑前须先读取文件", "1")
  # line 76-81
  _register("BUTLER_ENABLE_TERMINAL", "开发", "终端工具", "0")
  _register("BUTLER_ENABLE_GIT_PUSH", "开发", "Git push（需 Owner 审批）", "0")
  _register("BUTLER_EXECUTE_CODE", "开发", "代码沙箱执行", "0")
  # line 138
  os.environ[key] = value
  ```
- **影响**: prompt 注入 → `butler_config set BUTLER_IO_GUARDRAIL 0` + `set BUTLER_EXECUTE_CODE 1` + `set BUTLER_DOOM_LOOP_MODE ask` + `set BUTLER_TERMINAL_DANGER_CHECK 0` + `set BUTLER_ENABLE_GIT_PUSH 1` 5 个 set 后，所有入站 / 终端 / doom-loop / execute_code / git push 全部失守
- **建议**:
  1. 把这 8 个 key 全部从 `_MUTABLE_KEYS` 移出（运行时不可改）
  2. 如需保留可改，加 "安全/开发" 类别白名单 + owner 二次确认（与 SEC-9.5 联动）

### 2.2 [🔴 CRITICAL] SEC-9.5 `butler_config` 写路径无 owner 鉴权

- **位置**: `butler/tools/config_tools.py:42-49` + `butler/config_service.py:126-138`
- **证据**:
  ```bash
  $ grep "is_gateway_owner" butler/tools/config_tools.py
  (0 命中)
  $ grep "owner_required" butler/tools/config_tools.py
  (0 命中)
  ```
- **影响**: 即使 SEC-9.1 修完，`butler_config` 工具对任何 Agent 可用，写非安全 key 也意味着"任何会话能改运行时配置"
- **建议**: `config_set` 入口加 `is_gateway_owner(platform=platform, external_id=external_id)`；如 SEC-9.1 不把全部移出，至少写路径必须 owner 二次确认

### 2.3 [🟠 HIGH] SEC-9.2 `apprise` 出站未脱敏 PII

- **位置**: `butler/gateway/platforms/apprise_adapter.py:60-95`
- **证据**: `grep "scrub_outbound_text" apprise_adapter.py` 0 命中；`ap.notify(body=body, title=title, notify_type=nt)`（line 83-87）原样发
- **影响**: `butler_remember` 召回的 owner profile 含 PII 时，走 apprise 通道全部原文外发
- **建议**: `send_notification` 入口加 `body = scrub_outbound_text(body)`（2 行）

### 2.4 [🟠 HIGH] SEC-9.3 平台基类 `format_gateway_user_error` 错误回显未脱敏

- **位置**: `butler/gateway/platforms/base.py:115,125`
- **证据**: `await self.send(chat_id, format_gateway_user_error(exc))`（line 125）把异常对象 `str()` 后直接出站
- **影响**: 工具异常时 traceback / 文件路径 / 输入片段（可能含 PII）原文外发
- **建议**: `ButlerPlatformAdapter.send` 基类层统一调 `scrub_outbound_text(content)`；`format_gateway_user_error` 改用白名单模板

### 2.5 [🟡 MEDIUM] SEC-9.4 MCP `env` 注入（Sprint 8 SEC-4 扩展）

- **位置**: `butler/mcp/client_stdio.py:15-18` + `:28-30`
- **证据**: `_PROTECTED_ENV_KEYS` 仅 8 个；`PYTHONSTARTUP` / `NODE_OPTIONS` / `BASH_ENV` 等可被恶意 `mcp.yaml` 注入实现 RCE
- **建议**: 改白名单（仅 `_PROTECTED_ENV_KEYS` 中 + `BUTLER_MCP_ENV_ALLOW` 显式 opt-in）

### 2.6 [🟡 MEDIUM] SEC-9.6 `butler_remember` 入库未脱敏

- **位置**: `butler/memory/facade.py:406-458`
- **证据**: `prof.add(content)`（line 428）原文入库
- **影响**: 走非 WeChat 平台（如 apprise）召回即泄露
- **建议**: 写入时按 opt-in `BUTLER_MEMORY_PII_SCRUB` scrub；或 recall 出口统一 scrub

### 2.7 [🟡 MEDIUM] SEC-9.9 静态安全审计漏扫 `_MUTABLE_KEYS` + `BUTLER_PROJECT_CREATE_OPEN`

- **位置**: `butler/ops/security_audit.py:17-141`
- **建议**: 增加 `MUTABLE_SECURITY_KEYS_OPEN` finding：遍历 `_MUTABLE_KEYS`，若某 key category=安全/dev 且运行时已非默认值 → 告警

### 2.8 [🟡 MEDIUM] SEC-9.10 `io_guardrail` tripwire 事件无审计行

- **位置**: `butler/tools/tool_audit.py:80-101` + `butler/core/io_guardrail.py:45-75`
- **建议**: tripwire 命中时 `_record_tool_audit(name="io_guardrail", ok=False, code="GUARDRAIL_TRIPWIRE", ...)`

### 2.9 [🟢 LOW] SEC-9.7 `web_search` timeout 可被覆写拉高

- **位置**: `butler/tools/web_search.py:37` + `butler/tools/url_safety.py:73-75`
- **建议**: 硬 cap timeout=30s

### 2.10 [🟢 LOW] SEC-9.8 钩子输入 args 未截断

- **位置**: `butler/hooks/runner.py:515-519` + `_hook_payload` line 105-134
- **建议**: 序列化前 `args value[:1500]`

## 3. 性能维度（Sprint 9）

### 3.1 [🟠 HIGH] PERF-NEW-1 `exp_cache` 全文件 read+parse 每次 LLM 调用

- **位置**: `butler/core/exp_cache.py:108-118 + 142-152`
- **量化**: 500 entries × ~2KB ≈ 1MB；单次 read+parse ≈ 5-15ms；命中 0 时反而劣化 P50
- **影响**: 单 turn 2-3 次 LLM 调用 → 60-180ms 纯 I/O；预期 P95 延迟 +100-300ms
- **建议**: 内存 dict + 启动时一次 load + 写回 debounce(1s)

### 3.2 [🟠 HIGH] PERF-NEW-3 OpenAI SDK `max_retries=2` 与 `llm_retry` 20 次叠层

- **位置**: `butler/transport/llm_client.py:84,109`
- **量化**: SDK 默认 2 次重试 + 应用层 20 次 = 单次 60-90s 抖动 → 最坏 60s × 20 = **20min**
- **建议**: 构造时 `OpenAI(..., max_retries=0)`，重试全交给 `llm_retry`

### 3.3 [🟠 HIGH] PERF-NEW-8 `push_queue` 同一文件 4 处 read+rewrite

- **位置**: `butler/runtime/push_queue.py:33-58, 78-91, 100-110`
- **建议**: 内存 dict + 启动 load + 写回 debounce

### 3.4-3.10 [🟡 MEDIUM] 略（详见子 agent 报告 PERF-NEW-4/5/6/7/9）

### 3.11 [🟢 LOW] PERF-NEW-11 `effective_retries = min(20, ...)` 无 jitter

## 4. 可靠性维度（Sprint 9）

### 4.1 [🔴 CRITICAL] REL-9 + Sprint 8 REL-1 outbox writer 仍裸 write_text

- **位置**: `butler/gateway/durable_outbox.py:45-47 + 94 + 117-118`
- **证据**:
  ```python
  # line 45-47
  def _write_entry(path: Path, row: dict[str, Any]) -> None:
      path.parent.mkdir(parents=True, exist_ok=True)
      path.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
  # line 117-118
  _write_entry(pending, row)
  pending.replace(target)
  ```
- **Sprint 8 docstring 谎称** "Writers use LOCK_EX" 实际无 — `_outbox_read_lock` (line 67-78) 只用了 LOCK_SH，writer 路径完全没动
- **影响**: 双 daemon 启动 replay → mark_sent 互相覆盖；daemon 在 line 117 写完 target 后 crash → pending 与 target 同 id 共存 → 下次 replay 双发微信
- **建议**: `_write_entry` 改 `atomic_write_text` + writer 加 `flock(LOCK_EX)` 与 reader 对称

### 4.2 [🔴 CRITICAL] REL-10 `try_acquire_lock` 锁内容只写 time.time()

- **位置**: `butler/runtime/audit.py:59-93`
- **证据**:
  ```python
  # line 89-92
  try:
      os.write(fd, str(time.time()).encode("utf-8"))
  finally:
      os.close(fd)
  # release_lock line 96-99
  def release_lock(project_name: str, job_id: str) -> None:
      try:
          lock_path(project_name, job_id).unlink(missing_ok=True)
      except OSError:
          ...
  ```
- **影响**: 锁内无 PID/token，stale takeover 流程：stat → unlink → reopen。原 owner 进程 run 完 release_lock 时 unlink 的是**新 owner 的锁**（不验证持有者），新 owner 下一轮 acquire 还能成功 → **实际不互斥**
- **建议**: 锁内容 `os.getpid() + ":" + random_token`；release_lock 先 stat 验证 token 再 unlink

### 4.3 [🔴 CRITICAL] REL-11 `install_pending.get_pending` 副作用写 + 全链路裸 write

- **位置**: `butler/registry/install_pending.py:89-99 + 120`
- **证据**:
  ```python
  # line 95-99（get_pending 末尾副作用写盘）
  expired_ids = [pid for pid, info in self._pending.items() if now - info.get("created_at", 0) > self.ttl_seconds]
  for pid in expired_ids:
      del self._pending[pid]
  self._save_all(self._load())  # 副作用写盘
  ...
  # line 120
  def _save_all(self, pending):
      ...
      path.write_text(json.dumps(...), encoding="utf-8")  # 裸写
  ```
- **影响**: 两次 `/确认安装` 并发 → 第二次写覆盖第一次；`get_pending` 副作用写盘让"读"路径也非幂等
- **建议**: `get_pending` 改名 `_load_purge_in_place`；`_save_all` 改 `atomic_write_text` + 写失败抛 `RuntimeError`

### 4.4 [🟠 HIGH] REL-12 `session_transcript._tombstone_tail` 全文件重写无 fsync

- **位置**: `butler/core/session_transcript.py:75-110` + `butler/core/transcript_index.py:140-145`
- **建议**: 整段重写改 `tmp + os.fsync + os.replace`；index 同款

### 4.5 [🟠 HIGH] REL-13 `human_gate.consume_injection_bypass` 双花

- **位置**: `butler/human_gate.py:281-296`
- **影响**: 同一 turn 多个 bypass-消费者工具 → Owner 一条 /bypass 抵消两次
- **建议**: `os.rename` 到 `.consumed` 标记 + `O_EXCL` sentinel

### 4.6 [🟠 HIGH] REL-14 `mcp/manager._handles_for` 全局 dict 跨进程/线程返回活引用

- **位置**: `butler/mcp/manager.py:54-61`
- **建议**: 返回 `dict(snapshot)` 而非活引用；或加版本号

### 4.7 [🟠 HIGH] REL-15 18+ 工具路径继续裸 `path.write_text`

- **位置**: `grep "write_text" butler/ | grep -v "atomic_write_text" | grep -v "tests/"` 24+ 处命中
  - `runtime/notify.py:57` `runtime/approval.py:61,97,129`
  - `runtime/failure_tracker.py:44` `core/fact_extraction.py:54`
  - `core/transcript_index.py:140` `core/auto_continue.py:87`
  - `core/compaction_checkpoint.py:48` `core/two_phase_confirm.py:142`
  - `core/session_todos.py:110-120`（已 tmp+replace 但**无 fsync**）
  - `tools/tenant_store.py:47` + `memo.py:58` + `contacts.py:52` + `habits.py:52,109,276`
  - `tools/terminal_pattern_approval.py:60,80` + `terminal_approval.py:64`
  - `registry/skill_lock.py:32` + `mcp_install.py:181,231` + `hub_index_cache.py:62` + `catalog_integrity.py:54`
  - `core/goal_loop.py:43` + `workflows/pause_state.py:46` + `plan/store.py:39` + `report/store.py:45`
- **建议**: 集中替换为 `butler.io.atomic_write_text`（已含 fsync + symlink 拒绝）

### 4.8 [🟠 HIGH] REL-16 `interruptible_client` 中断后线程泄漏

- **位置**: `butler/transport/interruptible_client.py:36-49`
- **影响**: 用户 /中断长 LLM 流 → daemon 持 socket 60-90s
- **建议**: `httpx.AsyncClient` + `asyncio.timeout`；或 `_worker` 内 `transport.close()`

### 4.9 [🟠 HIGH] REL-17 `push_queue` read-modify-write 无锁

- **位置**: `butler/runtime/push_queue.py:42-58, 88-130`
- **影响**: 微信推送失败瞬时高频 + daemon 启动 + cron drain 并发 → 同一条失败推送被发 2-3 次
- **建议**: `flock(LOCK_EX)` 跨进程锁

### 4.10 [🟡 MEDIUM] REL-18 outbox writer lock 联动（合并入 REL-9）

### 4.11 [🟡 MEDIUM] REL-19 `mcp/async_runner` daemon loop 无 atexit

- **位置**: `butler/mcp/async_runner.py:11-39`
- **建议**: `atexit.register(_shutdown_loop)`

### 4.12 [🟡 MEDIUM] REL-20 `notify._write_last_push_monotonic` 冷却竞态

- **位置**: `butler/runtime/notify.py:57-61`
- **建议**: `atomic_write_text` + 同进程内 `threading.Lock`

### 4.13 [🟡 MEDIUM] REL-21 `gateway/runner._poll_reminders_loop` 同步 `bridge.send_text`

- **位置**: `butler/gateway/runner.py:200-225`
- **建议**: `await loop.run_in_executor(None, bridge.send_text, ...)`

### 4.14 [🟡 MEDIUM] REL-22 `mcp_install.install_catalog_server` lock 写失败不回滚 yaml

- **位置**: `butler/registry/mcp_install.py:155-194`

### 4.15 [🟡 MEDIUM] REL-23 `mcp_install.remove_mcp_server` yaml 整段覆盖无 fsync

- **位置**: `butler/registry/mcp_install.py:226-231`

### 4.16 [🟡 MEDIUM] REL-24 `vector_store._persist` 整文件 rewrite

- **位置**: `butler/memory/vector_store.py:169-171`

### 4.17 [🟢 LOW] REL-25 terminal `_watch` watcher 持闭包变量

- **位置**: `butler/tools/terminal_impl.py:148-180`

### 4.18 [🟢 LOW] REL-26 `post_session_ops` 后台线程 daemon 无 join

- **位置**: `butler/session/post_session_ops.py:147`

## 5. 测试缺口维度（Sprint 9）

### 5.1 [🟠 HIGH] TST-9 `turn_runner.py` 死代码

- **位置**: `butler/gateway/turn_runner.py:1-212`（2 def）
- **证据**: `grep -rln "from butler.gateway.turn_runner" butler/ tests/` 0 命中
- **建议**: 删（0.5d）或接管（1d e2e）

### 5.2 [🟠 HIGH] TST-10 `runtime/schedule.py` 死代码

- **位置**: `butler/runtime/schedule.py:1-51`（3 def）
- **证据**: 0 importers；`runtime_metrics.schedule` 已重叠
- **建议**: 删（0.5d）

### 5.3 [🟠 HIGH] TST-11 `core/loop_turn.py` 死代码

- **位置**: `butler/core/loop_turn.py:1-405`（2 def）
- **证据**: 0 importers；agent_loop 走 inline 实现
- **建议**: 删（0.5d）

### 5.4 [🟠 HIGH] TST-12 `commands/{lifecycle,dialog,info}_commands.py` 死代码

- **位置**: 3 文件 432 LOC / 30 def
- **证据**: 0 importers；commands 子包分裂后未挂回 main.py
- **建议**: 删（0.5d）

### 5.5 [🟠 HIGH] TST-13 `wechat_ilink` 2027 行 omit 中

- **位置**: `pyproject.toml:111`
- **影响**: Sprint 7 修过的 4 个 iLink bug（5.2.1 retain / 4.1.2 token / 4.1.4 chmod / Sprint 8 SEC-5 PII）任何回滚无信号
- **建议**: 移除 omit + 补 4 个 e2e

### 5.6 [🟠 HIGH] TST-14 `try_acquire_lock` 4 分支只测 atomicity

- **位置**: `butler/runtime/audit.py:67-87` + `tests/test_runtime_audit_lock.py:1-67`
- **影响**: stale 2h 后 takeover / unlink OSError / 重新抢占竞争 3 路径 0 测
- **建议**: 0.5d

### 5.7 [🟠 HIGH] TST-15 outbox writer 锁 + race 测试

- **位置**: `butler/gateway/durable_outbox.py:46-58`
- **证据**: Sprint 8 REL-2 加了 reader LOCK_SH，writer 仍裸 write_text；`grep "LOCK_EX" durable_outbox.py` 0 命中
- **建议**: 0.5d + 1 regression test

### 5.8 [🟡 MEDIUM] TST-16 `butler/io/atomic_write_text` 0 直测

- **位置**: `butler/io/atomic_write.py:1-9`（12 importers）
- **建议**: 5 case (encoding 错 / fsync / symlink / parent 缺 / 0o600 拒绝)

### 5.9 [🟡 MEDIUM] TST-17 `observation_store` flush 失败 / 落盘原子

### 5.10 [🟡 MEDIUM] TST-18 `session/post_session_layered.py` 30.6% 覆盖

### 5.11 [🟡 MEDIUM] TST-19 `tools/tenant_store.py` 33.3% 覆盖

### 5.12 [🟡 MEDIUM] TST-20 19 处 `time.sleep` 缺 monkeypatch stub

### 5.13 [🟢 LOW] TST-21 478 处 MagicMock 仅 2 处 `spec=`

### 5.14 预存在失败分类

| 根因 | 数量 | 根因 |
|------|------|------|
| mock 不一致（45 缺 script） | 45+ | `gateway_scripts.py:script_profiles()` 缺失定义；`comm -23` 取证 |
| flaky（线程竞争） | 1 | `test_handler_timeout_returns_wechat_message` |
| fixture 缺位（profile 组装） | 1 | `test_owner_profile_gateway` |
| 其他 | ~31 | misc |

**TST-2 单独列出**：抹平 45 缺 script = 抹平 78 失败中相当部分，是高 ROI 测试任务。

## 6. Sprint 8 旧未修的复核（Sprint 9 视角）

| ID | 仍存在 | 严重 | Sprint 9 处理 |
|----|--------|------|---------------|
| SEC-1 (`butler_config` 关安全 key) | ✅ 但漏算 1 + 漏 3 dev | 🔴 | 合并入 SEC-9.1 + SEC-9.5 |
| SEC-4 (MCP stdio args) | ✅ 扩展到 env 注入 | 🟠 | 合并入 SEC-9.4 |
| SEC-7 (execute_code HOME) | ✅ | 🟠 | 独立进 Sprint 10 |
| REL-1 (outbox 非原子) | ✅ writer 路径完全没动 | 🔴 | 合并入 REL-9 |
| TST-1 (`inbound_pipeline.py` 死代码) | ✅ 0 importer | 🔴 | 合并入 TST-9-12 集中处理 |

## 7. 推荐 Sprint 9 修复策略

### 7.1 短期（5-10 天）：6 个 CRITICAL + 死代码清理

1. **SEC-9.1 + SEC-9.5**：8 个 key 移出 `_MUTABLE_KEYS` + `butler_config` 加 owner 鉴权 — 1 天
2. **REL-9**：outbox writer 加 `flock(LOCK_EX)` + `_write_entry` 改 `atomic_write_text` — 0.5 天
3. **REL-10**：`try_acquire_lock` 锁内容 PID+token；`release_lock` 验证 — 0.5 天
4. **REL-11**：`get_pending` 改名 + `_save_all` atomic — 0.5 天
5. **TST-9-12 + Sprint 8 TST-1**：7 个死代码文件共 2006 行一次性删 — 0.5 天

### 7.2 中期（1-2 周）：PII 扩展 + 测试基础设施

6. **SEC-9.2/9.3** + REL-15（部分）：apprise + 平台基类 PII scrub + 18+ 工具 atomic 化 — 2-3 天
7. **TST-2**：补 45 缺失 script → 抹平 78 预存在失败 — 1 天
8. **TST-13**：移除 wechat_ilink omit + 4 e2e — 1 天
9. **TST-15/TST-16/TST-19/TST-20**：补关键 e2e + atomic_write 直测 + tenant_store 单测 + time.sleep stub — 2 天

### 7.3 长期：性能 + 可观测性

- 性能 11 项（PERF-NEW-1/3/4/5/6/7/8 + 6 个 Sprint 8 旧未修）— 5-7 天
- 可观测性：tripwire 审计行 + /health 完整化 + circuit-breaker metrics — 2-3 天
- Sprint 10 候选：剩余 25 MEDIUM + 5 LOW + 16 Sprint 8 旧未修项

## 8. 附录

### 8.1 复检命令汇总

```bash
# SEC-9.1: _MUTABLE_KEYS 注册
grep -n "_register\|category=\"安全\"\|category=\"开发\"" butler/config_service.py

# SEC-9.5: config_tools owner 鉴权
grep -n "is_gateway_owner\|owner_required" butler/tools/config_tools.py
# (0 命中 = 确认无)

# SEC-9.2/9.3: PII 脱敏接入
grep -rn "scrub_outbound_text" butler/gateway/platforms/
# (wechat_ilink 已修；apprise + base 0 命中 = 确认无)

# REL-9: outbox writer
grep -n "_write_entry\|LOCK_EX\|flock" butler/gateway/durable_outbox.py
# (_write_entry 用 path.write_text = 确认无 atomic；LOCK_EX 全 0 = 确认无)

# REL-10: audit lock 内容
sed -n '59,93p' butler/runtime/audit.py
# (锁内容只写 str(time.time()) = 确认)

# TST-9-12: 死代码
for mod in butler/gateway/turn_runner.py butler/runtime/schedule.py butler/core/loop_turn.py \
           butler/gateway/commands/lifecycle_commands.py butler/gateway/commands/dialog_commands.py \
           butler/gateway/commands/info_commands.py; do
  grep -rln --include='*.py' -E "from $(echo $mod|sed 's|/|.|g;s|\.py$||')" butler/ tests/
done
# (6 个全部 0 importer = 确认死代码)
```

### 8.2 subagent 报告

- 安全 subagent：SEC-9.1 ~ 9.10 共 10 项
- 性能 subagent：PERF-NEW-1 ~ NEW-11 共 11 项
- 可靠性 subagent：REL-9 ~ REL-26 共 18 项
- 测试 subagent：TST-9 ~ TST-21 共 13 项 + 6 文件死代码

### 8.3 范围声明

- Sprint 8 修复 6 项不在本表重复
- Sprint 7 修复 10 项不在本表重复
- 本表只列 Sprint 8 之后**仍存在**或**新暴露**的问题
- Sprint 8 旧未修项集中列于 §6，便于跨 Sprint 追踪
