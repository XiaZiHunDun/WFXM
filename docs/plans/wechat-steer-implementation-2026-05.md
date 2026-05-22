# 微信 `/steer` 实施（S1 — 2026-05-22）

> **状态**：已完成  
> **分析**：[`p3-deferred-deep-dive-2026-05.md`](p3-deferred-deep-dive-2026-05.md) §3

---

## 1. 产品语义

- **不打断** 当前工具执行；指引追加到 **下一批 tool 结果** 后供模型继续读。
- 仅在本会话 **Agent 轮次进行中** 可写入；否则明确拒绝（避免用户以为已插队）。
- 与 `/interrupt` 区分：steer 不取消 loop。

---

## 2. 技术方案（S1）

| 项 | 实现 |
|----|------|
| 分桶 | `_pending_by_session[session_key]` |
| 活跃轮次 | `_run_depth` + `mark_run_active` / `mark_run_inactive`（`AgentLoop.run`） |
| 网关 | `/steer`、`/指引` → sessionless；`steer(arg, session_key=…)` |
| CLI | `session_key="cli"` |
| 清理 | 每轮 `clear_steer(session_key)` 仅清本会话 |

---

## 3. 改动文件

- `butler/core/steer.py` — 会话分桶与活跃检测
- `butler/core/agent_loop.py` — run 边界 mark + `clear_steer(session)`
- `butler/gateway/message_handler.py` — 命令 + sessionless 集
- `butler/main.py` — CLI session_key
- `tests/test_steer_sessions.py`

---

## 4. 验收

- `pytest tests/test_steer_sessions.py tests/test_run_agent_extraction.py -q`
- 全仓 pytest + `butler-smoke.sh --tier=standard`

---

## 5. 执行记录

| 日期 | 说明 |
|------|------|
| 2026-05-22 | S1 落地；pytest 1110 + standard smoke 全绿 |
