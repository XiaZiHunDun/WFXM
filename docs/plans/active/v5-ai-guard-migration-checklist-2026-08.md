# Butler v5 AI Guard 迁移清单

> **状态**：✅ Done（2026-08-22，Owner）  
> **Issue**：[GitHub #2](https://github.com/XiaZiHunDun/WFXM/issues/2)  
> **备份**：`.backup/v5-ai-guard/20260821-110247/`（增量见本次 commit）

## 已交付

| 项 | 位置 |
| --- | --- |
| PreToolUse v5 承重文件 block | `scripts/ai_guard/pre_tool_use_hook.py` → `PROTECTED_FILES` |
| v5 schema 目录 warn | `PROTECTED_DIR_PATTERNS` → `butler-v5/packages/persistence/src/migrations/` |
| PostToolUse vitest 映射 | `scripts/ai_guard/post_tool_use_hook.py` → `V5_FILE_TO_TESTS` |
| pre-commit v5 保护 | `scripts/ai_guard/pre_commit_hook.sh` |
| 生产 vs 脚手架 | `butler-v5/AGENTS.md` §0 |
| v4 保护保留 | 未删除 legacy 项 |

## v5 承重文件（PreToolUse block）

- `butler-v5/apps/api/src/wechat-inbound-butler.ts`
- `butler-v5/apps/api/src/workspace-tools.ts`
- `butler-v5/apps/api/src/tool-boundary.ts`
- `butler-v5/apps/api/src/capability-guard.ts`
- `butler-v5/packages/runtime/src/agent-kernel.ts`
- `butler-v5/packages/runtime/src/run-engine.ts`
- `butler-v5/packages/runtime/src/bridge.ts`
- `butler-v5/packages/runtime/src/capability-boundary.ts`
- `butler-v5/packages/persistence/src/migrations/0001_initial.sql`

## PostToolUse vitest 触发（示例）

```bash
python3 scripts/ai_guard/post_tool_use_hook.py --match-only butler-v5/apps/api/src/workspace-tools.ts
# → v5 workspace tools -> apps/api/src/workspace-tools.test.ts
```

## 验收

- [x] 修改 `wechat-inbound-butler.ts` / `workspace-tools.ts` 触发 v5 测试子集
- [x] Agent 无法直接改受保护守卫文件（`pre_tool_use_hook.py` self-protect）
- [x] `butler-v5/AGENTS.md` 区分生产路径 vs 未接线脚手架（§0）
- [x] 守卫变更需 `[MANUAL-OVERRIDE]`（pre-commit）

## 仍由 Owner 维护

- 根 `.cursorrules` / `.claude/settings.json` 与 v4 保护并存至 v4 只读归档
- 新 v5 承重文件加入清单时同步三处：`pre_tool_use_hook.py`、`post_tool_use_hook.py`、`pre_commit_hook.sh`
