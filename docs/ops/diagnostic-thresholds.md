# `/诊断` 运行指标 — 阈值说明

> 指标由 `butler/ops/runtime_metrics.py` 进程内累计，无 Prometheus 依赖。  
> 在微信发送 **`/诊断`** 或 CLI 等价命令查看。

## 进程累计（全局）

| 指标 | 含义 | 建议关注 |
|------|------|----------|
| `llm_request{outcome=ok}` | LLM 成功次数 | 与 fail 对比 |
| `llm_request{outcome=fail}` | 全部重试后仍失败 | 单轮突增 → 查模型/网络 |
| `llm_request{outcome=interrupt}` | 用户中断 | 正常 |
| `llm_latency{...}` p50/p95 | 单次 LLM 延迟 | p95 持续 >30s → 查 provider |
| `tool_call{outcome=error}` | 工具返回 error | 按 tool 标签定位 |
| `turn_duration{...}` | 整轮耗时 | p95 过长 → 查委派/工具 |
| `gateway_sessions` | 内存中会话数 | 接近 max_sessions → LRU 将驱逐 |
| `gateway_active_turns` | 正在跑 Loop 的会话 | 长期 ≥1 且卡住 → 查超时 |
| `inbound_queue_depth_total` | 全站入站队列条数 | 持续 >10 → 用户连发或 turn 过慢 |

## 本会话

| 指标 | 含义 |
|------|------|
| `gateway_completion_push{outcome=*}` | 出站推送成功/失败/入队 |
| `inbound_queue_depth` | 当前会话排队条数 |
| `turn_finished` / `turn_duration` | 本会话轮次结束原因与耗时 |

## 排障顺序

1. 看 `llm_request{outcome=fail}` 是否增加  
2. 看 `tool_call{outcome=error}` 与工具审计行  
3. 看 `inbound_queue_depth` 与「入站队列待发」  
4. 看 `gateway_active_turns` 是否异常挂起  

重置：发送 **`/new`** 会清除**本会话**运行指标采样（与 hook/completion 遥测一并 reset）。
