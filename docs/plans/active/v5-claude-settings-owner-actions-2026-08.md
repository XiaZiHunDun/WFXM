# Claude Code settings.json — Owner 人工动作（2026-08-24）

> **状态**：✅ Done（2026-08-24）  
> **关联**：[`v5-engineering-handoff-2026-08.md`](../decisions/v5-engineering-handoff-2026-08.md) · [`v5-ai-guard-migration-checklist-2026-08.md`](../archive/v5-ai-guard-migration-checklist-2026-08.md)

---

## 已交付

| 项 | 变更 |
| --- | --- |
| `.claude/settings.json` Stop | 移除 `BLACKBOARD_STRICT=1` → v5 软提醒 |
| `claude_session_end.py` | legacy strict 仍可用；v5 默认走 `scripts/claude_session_end_v5.py` |
| Legacy strict | `BLACKBOARD_STRICT=1` 仍可用 v4 班次卡 hard gate（勿在生产 Stop 启用） |

Stop 命令（当前）：

```text
BLACKBOARD_AGENT=claude-code BLACKBOARD_ROOT=.../.blackboard python3 .../scripts/claude_session_end_v5.py
```

实现：`scripts/claude_session_end_v5.py`（v5 默认）；`BLACKBOARD_STRICT=1` 时委托 legacy `butler.blackboard.integrations.claude_session_end`。

---

## 仍可选（非阻塞）

- [ ] `.blackboard/README.md` 改为一页规约指向 `v5-engineering-handoff`（受保护文件，Owner 人工）

---

## 验收

- [x] Claude Code Stop 缺 state.md 段时 WARN，不 block（exit 0）
- [x] `tests/blackboard/test_session_end.py` 覆盖 v5 软 / v4 strict 双路径
- [x] commit 含 settings.json 变更（`[MANUAL-OVERRIDE]` 若 pre-commit 要求）
