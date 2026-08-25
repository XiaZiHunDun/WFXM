# v5 剩余开发计划（2026-08-20）

> **工程项**：R8.x.19 入站 CDN 媒体 — **已完成 2026-08-20**。  
> **跟进立项（独立）**：[`v5-followon-projects-2026-08-20.md`](v5-followon-projects-2026-08-20.md)（ASR / 出站发图 / 窄白名单 — **均 done**）。  
> **日历**：D1 删 `~/.butler/` — **EXECUTED 2026-08-25**（见 [`v4-butler-home-retention-2026-08-20.md`](../decisions/v4-butler-home-retention-2026-08-20.md)）。

## R8.x.19 — 入站 CDN 媒体（done）

下载并 AES-128-ECB 解密微信图/语音/文件到 `{workspace}/.butler/ilink-media/`，inbound 文本改为「已保存到 <path>」。失败时保留占位符。出站发图、ASR、扩大 `run_command` 白名单仍不做。
