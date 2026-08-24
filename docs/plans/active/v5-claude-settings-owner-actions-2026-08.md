# Claude Code settings.json — Owner 人工动作（2026-08-24）

> **状态**：Pending Owner  
> **原因**：`.claude/settings.json` 在 PreToolUse `PROTECTED_FILES`，AI 不可直接改  
> **关联**：[`v5-ai-guard-migration-checklist-2026-08.md`](v5-ai-guard-migration-checklist-2026-08.md) · [`v5-engineering-handoff-2026-08.md`](../decisions/v5-engineering-handoff-2026-08.md)

---

## 现状

`/.claude/settings.json` 仍含 v4 口径 **Stop hard gate**：

```json
"Stop": [{
  "command": "BLACKBOARD_STRICT=1 BLACKBOARD_AGENT=claude-code ... claude_session_end"
}]
```

根 `.cursorrules` 与 hooks 已 v5 收敛；**Claude Code Stop 仍强制五件套班次卡**（与 2026-08 工程交接「短 state.md」不一致）。

PreToolUse / PostToolUse 已指向 v5 guard（`scripts/ai_guard/*`），无需改。

---

## 建议 Owner 修改（二选一）

### A. 软提醒（推荐，对齐 v5-engineering-handoff）

将 Stop hook 改为软提醒或移除 `BLACKBOARD_STRICT=1`：

```bash
# 编辑后验证
python3 scripts/ai_guard/pre_tool_use_hook.py --match-only .claude/settings.json
# 预期：block（需人工 [MANUAL-OVERRIDE] commit）
```

Stop 命令可改为仅检查 `state.md` 存在且 `_last_synced` 非空，缺卡 WARN 不 block。

### B. 维持 hard gate 至 v4 只读归档

不改 settings.json；Claude Code 会话仍须写完整班次卡。Cursor 侧以 `.blackboard/state.md` 短快照为准。

---

## 验收

- [ ] Owner 选定 A 或 B 并在 GitHub issue / 本文件记录
- [ ] 若选 A：人工改 settings.json + commit `[MANUAL-OVERRIDE]`
- [ ] 新 Claude Code 会话 Stop 行为与 `v5-engineering-handoff-2026-08.md` 一致
