# Sprint Codex-C2（2026-05）

对标 `reference/codex` 的 remote compact、memories、thread fork、app-server Item 事件；**默认保守**（远程压缩与 transcript 记忆均关）。

## 能力一览

| ID | Codex 来源 | Butler 模块 | 默认 |
|----|-----------|-------------|------|
| C2-1 | `compact_remote_v2.rs` | `butler/core/remote_compact.py` + `context_compressor` | **关** |
| C2-2 | `memories/` | `butler/memory/transcript_memory_pipeline.py` | **关** |
| C2-3 | `thread_manager` fork | `butler/core/transcript_fork.py` | 开（需 owner） |
| C2-4 | app-server Item | `butler/gateway/item_events.py` + `item_event_sink` | 开 |

## 环境变量

| 变量 | 说明 |
|------|------|
| `BUTLER_REMOTE_COMPACT=1` | 对 OpenAI 兼容 host 尝试 `POST /v1/responses/compact`，失败则回退本地 auxiliary |
| `BUTLER_REMOTE_COMPACT_URL` | 覆盖 compact 完整 URL |
| `BUTLER_REMOTE_COMPACT_FORCE=1` | 非 openai.com host 也尝试 compact |
| `BUTLER_TRANSCRIPT_MEMORY=1` | 启用 `/记忆提炼` 从 JSONL transcript 跑 PostSession 记忆通道 |
| `BUTLER_TRANSCRIPT_MEMORY_MAX_LINES` | 读取 transcript 尾部行数（默认 400） |

## 网关命令（owner）

- `/fork-transcript N`、`/transcript-fork N`、`/分叉 N` — 从第 N 条 `type=user` 行保留 transcript
- `/记忆提炼 [项目名]` — 需 `BUTLER_TRANSCRIPT_MEMORY=1`

健康检查 `health.thread_items` 与 `outbound_events` 中 `kind=thread_item` 可见最近压缩 Item 生命周期。

## 验收

```bash
pytest tests/test_sprint_codex_c0.py tests/test_sprint_codex_c1.py tests/test_sprint_codex_c2.py -q
```

对照总表：[codex-butler-comparison-2026-05.md](../plans/codex-butler-comparison-2026-05.md)
