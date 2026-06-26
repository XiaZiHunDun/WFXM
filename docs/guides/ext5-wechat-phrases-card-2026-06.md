# EXT-5 + Owner 首周 — 微信可复制话术卡

> **用法**：按顺序复制到微信发给 Butler（每条单独发）。  
> **前置**：gateway preflight 绿 · `butler-extension-ext5-verify.sh` PASS  
> **详版**：[`ext5-wechat-verify-2026-06.md`](ext5-wechat-verify-2026-06.md) · [`owner-first-week-2026-06.md`](owner-first-week-2026-06.md)

终端打印本卡：`bash scripts/butler-ext5-wechat-phrases-card.sh`

---

## 准备（发第 1 条前）

```
/切换 灵文1号
```

期望：回复含「已切换到项目: 灵文1号」。

---

## EXT-5 真机四句

### #1 诊断（MCP 在线）

**发送：**

```
/诊断 详细
```

**通过标准：** 收到 `.txt` 附件，正文含：

- `markitdown (stdio) [ok]`
- `markitdown-ingest [ok]`（Extension Verify 行）

---

### #2 项目内 TXT → Markdown

**发送：**

```
把 docs/ext5-fixture-sample.txt 转成 Markdown
```

**通过标准：** 回复含转换/委派完成；项目内存在 `docs/ext5-fixture-sample.md`（或等价路径）。

---

### #3  ingest 进记忆

**有 PDF 时** — 先在微信发 PDF 附件，再发：

```
把这份 PDF 转成 Markdown 放进记忆
```

**无 PDF 时（等价替代）** — 直接发：

```
把 docs/ext5-fixture-sample.txt 转成 Markdown 放进记忆
```

**通过标准：** 回复提及 ingest / 记忆 / 转换；`~/.butler/ingest/` 有新 `.md`（可选 SSH：`ls -lt ~/.butler/ingest/ | head`）。

---

### #4 manifest 参考书（防幻觉路径）

**发送：**

```
用 MarkItDown 转换项目里的参考书 docs/ext5-fixture-sample.txt
```

**通过标准：** 路径指向 **项目内** `docs/…`，不编造仓库外文件名；有转换摘要或委派结果。

---

## Owner 首周补两条（可选，~1 分钟）

### 每日节奏

```
/简报
```

期望：四块 — 待办 / 队列 / 门控 / 昨夜 job。

### OT2 真机硬反馈（与 handler 烟测对照）

```
/反馈 真机验收：EXT-5 话术卡走通
```

期望：回复「已记录反馈（计入 OT2 Owner 硬反馈）」。

---

## 结案勾选

真机 #1–#4 全通过后（**或** verify 指南 §2.1 handler sim 全绿），SSH 执行：

```bash
cd /path/to/WFXM
bash scripts/butler-extension-verify.sh markitdown-ingest
```

然后在 [`ext-5-markitdown-mcp-2026-06.md`](../plans/active/extension-candidates/ext-5-markitdown-mcp-2026-06.md) §8 勾 **Verify 真机 ✅**。

**handler sim 复跑戳**（P5 收束后）：见 [`ext5-wechat-verify`](ext5-wechat-verify-2026-06.md) §2.1（2026-06-26 全 PASS）。

---

## 速查表

| # | 一键复制 |
|---|----------|
| 准备 | `/切换 灵文1号` |
| 1 | `/诊断 详细` |
| 2 | `把 docs/ext5-fixture-sample.txt 转成 Markdown` |
| 3a | `把这份 PDF 转成 Markdown 放进记忆`（先发 PDF） |
| 3b | `把 docs/ext5-fixture-sample.txt 转成 Markdown 放进记忆`（无 PDF） |
| 4 | `用 MarkItDown 转换项目里的参考书 docs/ext5-fixture-sample.txt` |
| 简报 | `/简报` |
| 反馈 | `/反馈 真机验收：EXT-5 话术卡走通` |

---

## 未通过？

| 现象 | 处理 |
|------|------|
| 无 markitdown | `.env` 设 `BUTLER_MCP_MAX_SERVERS=4`，`butler-gateway-ops.sh restart` |
| 找不到 tests/fixtures | 必须用 **docs/** 项目路径，先 `/切换 灵文1号` |
| 超时 | `pip install markitdown-mcp` 或 sim 前 prewarm |
| 无附件 | 等 15–25s；仍无则看 `logs/butler-gateway.log` |
