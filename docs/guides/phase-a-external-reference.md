# 阶段 A — 外部对标落地（Hermes / LangChain / Dify / Langflow）

> 2026-05-25 · 零新增 pip 依赖

## 已落地

| 项 | 模块 | 环境变量 |
|----|------|----------|
| 压缩前 AI/Tool 成对切分 | `butler/core/compaction_cutoff.py` | — |
| 压缩触发优先 usage | `hygiene_preflight.py` | `/诊断` 见 `hygiene_compact_trigger_source` |
| 流式 memory-context scrub | `transport/memory_context_scrubber.py` | `BUTLER_STREAM_MEMORY_SCRUB` |
| Gateway 流式预览（ack） | `outbound_bridge.append_stream_preview` | `BUTLER_GATEWAY_STREAM_PREVIEW=1` |
| auto-continue | `core/auto_continue.py` | `BUTLER_AUTO_CONTINUE` / `MAX_AGE` |
| slash 旁路 `/stop` 等 | `message_handler` 入队前 | — |
| workflow 节点事件 | `session_transcript` `workflow_step` + bridge | — |
| 出站事件类型 | `gateway/outbound_events.py` | health `outbound_events` |

## 验收

```bash
pytest tests/test_phase_a_external.py -q
```

微信：

1. 长任务中 ack（可选 `BUTLER_GATEWAY_STREAM_PREVIEW=1`）是否带预览尾句  
2. 中断后 1h 内发「继续」是否带上文任务（非空 preview）  
3. `/stop` 在队列积压时是否立刻打断  
4. workflow 失败步骤是否在 transcript 有 `workflow_step` `phase=fail`

## 后续阶段

- B/C 与补做：[`external-reference-roadmap-2026-05.md`](external-reference-roadmap-2026-05.md)
