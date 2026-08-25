# v5 四项跟进裁决（2026-08-20）

> Owner 点名评估：扩大 `run_command` 白名单、修嵌套 architecture 门禁、出站发图、语音 ASR。  
> **立项正文**：[`v5-followon-projects-2026-08-20.md`](../active/v5-followon-projects-2026-08-20.md)

## 裁决

| 项 | 裁决 | 理由 |
|----|------|------|
| 修嵌套 architecture 门禁 `r2–r6` | **不立项** | 已从默认 vitest 排除。本质是在测试里再跑一遍 `pnpm gate`，对微信管家零收益。文件可留作考古，不要再修到绿。 |
| 扩大 `run_command` 白名单 | **立项 R8.x.20（窄名单）** | 现网 argv 无 shell，只有 `cat/date/echo/git/head/ls/pwd/wc`。微信侧编码管家几乎跑不了 `pnpm`/`python3`/`rg`。**不是**放开 `bash`/`rm`。 |
| 出站发图 | **立项 R8.x.21** | 入站已落盘，但手机看不到服务器路径；管家只能回文字。闭环缺「把本地文件发回微信」。v4 已有 CDN 上传+AES，可移植。 |
| 语音 ASR | **立项 R8.x.22** | 语音已存 `.silk`，模型听不到。手机主输入经常是语音。先吃 iLink `voice_item.text`（若有），再上 silk 解码 + 已有 DashScope/DeepSeek 侧转写。 |

## 不做的边界（写进立项，避免膨胀）

- 不立项：嵌套 architecture 门禁；`bash`/`sh`/`rm`/`sudo`；出站视频；实时通话。
- D1：**EXECUTED 2026-08-25** — `~/.butler/` 已删；与这四项无关。
