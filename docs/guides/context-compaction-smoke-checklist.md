# 长会话上下文压缩 — 压测清单

> 配合 `scripts/butler-context-compaction-smoke.sh`（CI/本地）与微信真机抽测。  
> 架构说明：[`v4-context-memory-compaction.md`](../architecture/v4-context-memory-compaction.md)

## 自动化（每次改 core/context 后）

```bash
cd /path/to/WFXM
bash scripts/butler-context-compaction-smoke.sh
```

预期：全部 pytest 通过，无新增 `context_compact_circuit_open`。

---

## 微信真机 — 长会话剧本（约 15–25 轮）

**前提**：网关已启动；当前项目有可读文件（如灵文1号 `docs/`）。

| 步 | 用户发送 | 预期 |
|----|----------|------|
| 1 | `/new` | 新会话 |
| 2 | `请连续 read_file 读取 docs 下 5 个文件并各用一句话总结` | 多轮 tool；回复变短但不空 |
| 3 | `再搜一下项目里所有 test_ 开头的文件` | `search_files` 大结果可能被剪枝 |
| 4 | `把我们刚才读过哪些文件列个清单` | 应能答出（摘要或 facts 锚点） |
| 5 | `/诊断` | `压缩:` 曾为「已压缩」或「预检压缩」；若有 facts 则见 `事实锚点:` |
| 6 | 静置 2 分钟后再问同一清单问题 | 不应重复入站；记忆仍连贯 |

**通过标准**

- 无「处理超时」连环
- `/诊断` 中 `压缩状态` 非 `circuit_open`
- 步骤 4 清单 **大致正确**（允许措辞变化，文件路径应对）
- 若触发压缩：`事实锚点` 行存在或 `记忆度量 S_f` 有数值

---

## 可选：强制触发压缩（仅测试环境）

一键启用/恢复（会改 `.env` 并重启网关）：

```bash
bash scripts/butler-compaction-live-test.sh enable    # 默认 reserve=5000
bash scripts/butler-compaction-live-test.sh status
bash scripts/butler-compaction-live-test.sh checklist
bash scripts/butler-compaction-live-test.sh disable   # 测完务必执行
```

或手动在 `.env` 临时设置（测完恢复）：

```bash
BUTLER_CONTEXT_COMPACT_RESERVE=5000
```

**注意（真机 token 门槛）**：`44,000` 有效窗口下，自动压缩最低触发约 **37,400 tokens**（85% 下限），与 `reserve` 设多低无关。本轮 `/诊断` 约 **15k**，还需再堆 **~22k tokens**（约 8–12 轮大段 `read_file` + 长总结）才会出现 `压缩: 已压缩` 与 `事实锚点:`。可继续发：

```text
请 read_file 读完 docs 剩下 4 个文件，每个文件用至少 3 句话详细总结；再把前 5 个已读文件各用 3 句话复述一遍
```

本地 pytest 模拟：`tests/test_context_pipeline.py`、`tests/test_turn_compaction.py`。

---

## 故障排查

| 现象 | 查什么 |
|------|--------|
| 压缩熔断 | `/诊断` `circuit_open`；日志 `consecutive compact failures` |
| 压缩后失忆 | `~/.butler/session_facts/` 是否有会话 json；`BUTLER_FACT_EXTRACTION` |
| 记忆预取过长 | 下调 `BUTLER_PREFETCH_TOTAL_MAX_CHARS` |
| 413 仍失败 | `reactive_compact` 日志；考虑换更大上下文模型 |
