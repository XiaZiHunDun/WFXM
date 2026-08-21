# Butler v5 AI 守卫迁移 — 分步脚本

> 你手动逐步执行，每步把 `STEP xx RESULT` 整段贴回给 Agent。

## 顺序

| 步 | 脚本 | 作用 |
| --- | --- | --- |
| 0 | `bash scripts/v5_ai_guard/step-00-preflight.sh` | 环境探测（只读） |
| 1 | `bash scripts/v5_ai_guard/step-01-backup.sh` | 备份待改文件 |
| 2 | `bash scripts/v5_ai_guard/step-02-post-hook.sh` | PostToolUse + v5 vitest |
| 3 | `bash scripts/v5_ai_guard/step-03-pre-hook.sh` | PreToolUse + v5 受保护文件 |
| 4 | `bash scripts/v5_ai_guard/step-04-cursorrules.sh` | .cursorrules v5 banner |
| 5 | `bash scripts/v5_ai_guard/step-05-agents-md.sh` | butler-v5/AGENTS.md §0 |
| 6 | `bash scripts/v5_ai_guard/step-06-pretooluse-optional.sh` | 可选：Claude PreToolUse |
| 7 | `bash scripts/v5_ai_guard/step-07-verify.sh` | 验收（pnpm test + hook 冒烟） |
| 8 | `bash scripts/v5_ai_guard/step-08-report.sh` | 摘要 + 建议 commit |

## 回滚

```bash
STAMP=$(cat .backup/v5-ai-guard/LATEST)
cp -a .backup/v5-ai-guard/$STAMP/* .
# 或按路径逐个 cp
```

## 注意

- Step 2–5 会改受保护文件；脚本幂等，重复跑会 SKIP。
- Step 6 仅 Claude Code 需要；Cursor 可跳过。
- commit 需 `[MANUAL-OVERRIDE]`（见 step-08 输出）。
