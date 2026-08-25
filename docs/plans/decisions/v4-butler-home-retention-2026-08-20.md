# v4 `~/.butler/` 数据保留决策（观察窗口）

> **Decision date**: 2026-08-20  
> **Decision owner**: ailearn (D1)  
> **Status**: EXECUTED (2026-08-25)  
> **关联**: `docs/architecture/v5-r10-handoff.md` §8.1  
> **执行交接**: [`v5-d1-execution-handoff-2026-08-25.md`](../active/v5-d1-execution-handoff-2026-08-25.md)

---

## TL;DR

**已删除** `~/.butler/`（2026-08-25，Owner 提前于原日历 2026-09-18 执行）。

`butler/` 源码已在 git 历史中，不必为保留实现而留运行时状态。

---

## 执行记录（2026-08-25）

- 备份：`~/backup-butler-home-20260825.tgz`（sha256 删除前后均 OK）
- 删除前 smoke：healthz OK；`smoke-project-knowledge.mjs` PASS
- 分块删 v4 子树 → `rm -rf ~/.butler`（目录已不存在）
- 删除后 smoke：gateway restart；healthz OK；`smoke-project-knowledge.mjs` PASS
- v5 audit 路径：`~/.config/butler-v5/audit/subagent.jsonl` 未受影响

---

## 约束（历史）

- ~~窗口内任何 Agent **不得**删除或搬空 `~/.butler/`~~ — 已于 2026-08-25 执行完毕。
- v5 凭证在 `~/.config/butler-v5/env`；不要把 v4 目录当生产配置源（目录已删）。
