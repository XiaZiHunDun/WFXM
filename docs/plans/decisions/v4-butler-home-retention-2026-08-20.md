# v4 `~/.butler/` 数据保留决策（观察窗口）

> **Decision date**: 2026-08-20  
> **Decision owner**: ailearn (D1)  
> **Status**: DEFERRED until 2026-09-18  
> **关联**: `docs/architecture/v5-r10-handoff.md` §8.1

---

## TL;DR

**现在不删** `~/.butler/`。观察窗口到 **2026-09-18**，若 v5 微信主线仍稳定，再删除该目录。

`butler/` 源码已在 git 历史中，不必为保留实现而留运行时状态。

---

## 约束

- 窗口内任何 Agent **不得**删除或搬空 `~/.butler/`，除非 owner 另行明确授权。
- v5 凭证已在 `~/.config/butler-v5/env`；不要把 v4 目录当生产配置源。
