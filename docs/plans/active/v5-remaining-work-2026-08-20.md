# v5 剩余开发计划（2026-08-20）

> **唯一工程项**：R8.x.19 iLink 入站媒体解密。  
> **否决项**见 [`v5-optional-debt-triage-2026-08-20.md`](../decisions/v5-optional-debt-triage-2026-08-20.md)。  
> **日历**：2026-09-18 后按 D1 删除 `~/.butler/`（不写代码）。

## R8.x.19 — 入站 CDN 媒体

**目标**：微信发来的图片 / 语音 / 文件，管家能拿到明文内容再进 butler loop，而不是 `[image]` 占位符。

**现状**：`extractIlinkMediaPlaceholder`（`packages/adapters/src/wechat/ilink-protocol.ts`）在无文本时写占位；不下载、不解密。

**范围（做）**

1. 从 iLink item（type 2/3/4/5）取出 CDN URL 与加解密所需字段（对照 v4 `wechat_ilink` 媒体路径，只移植入站下载）。
2. 下载并解密到工作区缓存（路径在 `BUTLER_V5_WORKSPACE_ROOT` 下，限制大小）。
3. 图片：把本地路径或简短说明注入 inbound 文本（先不做多模态 vision，除非已有 provider 支持）。
4. 语音 / 文件：落盘 + 文本提示「已保存到 …」；语音转写不在本阶段。
5. 失败时保持现有占位符，不丢整条消息。

**范围（不做）**

- 出站发图 / 发文件
- 语音 ASR
- 扩大 `run_command` 白名单

**验收**

- 协议解析 + 解密失败回退：单测（mock HTTP，不打真实 CDN）
- mock 入站 type=2：inbound 文本含缓存路径或明确说明
- 不回归纯文本 `getupdates` → `sendmessage`

**建议顺序**：TDD 协议字段 → 下载/解密模块 → poller 接入占位符替换。
