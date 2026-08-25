# v5 可选债 triage（2026-08-20）

> **裁决**：从交接「下次 / optional debt」里清掉三项长期挂账。  
> **关联**：[`v5-remaining-work-2026-08-20.md`](../active/v5-remaining-work-2026-08-20.md)

## 裁决表

| 项 | 裁决 | 原因 |
|----|------|------|
| iLink CDN 媒体解密（图/语音/文件） | **做** | 微信管家入站非文本目前只有占位符，模型看不到内容。这是产品缺口，不是工程洁癖。 |
| `run_command` 扩大白名单 | **不做** | 现有 `cat/date/echo/git/head/ls/pwd/wc` 已覆盖只读探查；扩 `bash`/`rm` 等会抬高风险。没有具体缺哪条命令的需求。需要时按命令名单独立项。 |
| `tests/architecture/r{2,3,4,5,6}-end-to-end.test.ts` | **不做（并从默认 vitest 排除）** | 在 vitest 里再跑一遍 `pnpm typecheck/lint/format:check`，与 `pnpm gate` 重复，拖时长，且会因仓库里未 prettier 的无关文件变红。R6 dry-run 已有 `scripts/cutover/run-cutover.test.mjs`。 |

## 仍保留但不算「可选债清单」

- **D1**：**EXECUTED 2026-08-25** — `~/.butler/` 已删（日历动作，非开发 backlog）。
