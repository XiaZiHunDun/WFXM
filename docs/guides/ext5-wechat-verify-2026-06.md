# EXT-5 MarkItDown — 微信真机验收（2026-06）

> **前置**：Integrate ✅ · handler sim ✅ · **真机话术 ✅ 2026-06-26** · **P5 收束后 handler sim 复跑 ✅ 2026-06-26**  
> **规程**：[`extension-rd-loop-2026-06.md`](../plans/active/extension-rd-loop-2026-06.md) · 一页纸 [`ext-5-markitdown-mcp-2026-06.md`](../plans/active/extension-candidates/ext-5-markitdown-mcp-2026-06.md)

---

## 0. 自动化验收（SSH，真机前必跑）

```bash
cd /path/to/WFXM
bash scripts/butler-extension-ext5-verify.sh        # 全量（preflight + MCP + handler sim）
bash scripts/butler-owner-week1-ops-sim.sh          # 首周 playbook + G1-04 /反馈 烟测
bash scripts/butler-g1-04-weekly-checkin.sh --log   # OT2 周打卡写 pilot-log
```

| 检查项 | 自动化 | 真机 |
|--------|--------|------|
| markitdown MCP `[ok]` | `ext5-verify` | `/诊断 详细` 附件 |
| markitdown-ingest | `extension-verify` | 话术 #2–4 |
| Owner `/简报` `/切换` `/反馈` | `owner-week1-ops-sim` | playbook 每天 30 秒 |
| OT2 Owner 硬反馈 | handler `/反馈` 烟测 | 微信发 `/反馈 …` |

自动化通过后，再跑下方 §3 真机话术。§2 为 ext5 专项快速命令。

---

## 1. Gateway 配置（一次性）

在 **gateway 宿主机** `WFXM/.env`：

```bash
BUTLER_MCP_ENABLED=1
BUTLER_INGEST_ENABLED=1
BUTLER_MCP_MAX_SERVERS=4    # firecrawl + todoist + github + markitdown
BUTLER_MCP_STDIO_ALLOW_COMMANDS=python,python3,uvx,npx
```

`~/.butler/mcp.yaml` 含 `markitdown:` 段（`bash scripts/butler-extension-ext5-integrate.sh`）。

依赖（二选一）：

```bash
pip install markitdown-mcp
# 或首次 uvx 冷启动前预热：uvx markitdown-mcp --help
```

重启 gateway：

```bash
bash scripts/butler-gateway-ops.sh restart
bash scripts/butler-gateway-ops.sh preflight   # 应无 MCP_MAX_SERVERS 告警
```

---

## 2. EXT-5 专项自动化（不经微信）

```bash
cd /path/to/WFXM
bash scripts/butler-extension-ext5-verify.sh        # 全量（含 handler sim）
bash scripts/butler-extension-ext5-verify.sh --quick  # 仅 /诊断 + MCP
```

通过标准：`markitdown (stdio) [ok]` · `markitdown-ingest [ok]` · sim ALL PASS。

### 2.1 P5 收束后 handler sim 复跑（2026-06-26）

> **方式**：`ButlerMessageHandler` 模拟微信入站（不经 iLink）· 项目 **灵文1号** · `BUTLER_DEV_VERIFY_SUCCESS_GATE=1`  
> **触发**：PROD-P5-A/B/C 上线后回归 EXT-5 话术卡 + ingest 验收语义

| # | 模拟消息 | 结果 | 备注 |
|---|----------|------|------|
| 准备 | `/切换 灵文1号` | ✅ | |
| 1 | `/诊断 详细` | ✅ | Extension Verify · markitdown |
| 2 | `把 docs/ext5-fixture-sample.txt 转成 Markdown` | ✅ | `task_679a5546ec71`；`docs/ext5-fixture-sample.md` 落盘（commit `25b142e`） |
| 3 | `…放进记忆` | ✅ | `task_9cf71c2bfe9e`；验收卡 `测试：—（ingest 写盘）`；无 `DEV_VERIFY_GATE` |
| 4 | `用 MarkItDown 转换项目里的参考书 docs/…` | ✅ | 项目内路径，无 hallucination |
| 补 | `/简报` · `/反馈 …` | ✅ | 首周节奏 + OT2 硬反馈烟测 |

**产物路径**：`projects/LingWen1/docs/ext5-fixture-sample.md` · `projects/LingWen1/.butler/ingest/docs/ext5-fixture-sample.md`

**运维提示**：#2 在同会话连跑时曾出现「委派报 PASS 但 `docs/*.md` 未落盘」；验收宜 **逐条单独发** 或 **独立 session**（与真机话术卡顺序一致）。本地观测写 `projects/LingWen1/docs/pilot-log.md`（gitignore，不进仓）。

### 2.2 话术卡 #3a PDF 附件（handler sim · 2026-06-26）

> **方式**：`build_inbound_user_text` 模拟微信 PDF 入站 → 再发「放进记忆」  
> **脚本**：`bash scripts/butler-ext5-pdf-ingest-sim.sh`  
> **fixture**：`tests/fixtures/ext5/sample.pdf`

| 步 | 模拟 | 通过标准 |
|----|------|----------|
| 1 | PDF 附件 → inbound 文本含 `EXT-5 fixture` | 委派或 ingest 完成；无 `DEV_VERIFY_GATE` |
| 2 | `把这份 PDF 转成 Markdown 放进记忆` | `.butler/ingest/**/*.md` 含 PDF 正文；无 `butler_remember` 反问 |

**说明**：Lead 可能在第 1 步即完成 ingest（与真机「先发 PDF、再发话术」等价结果）。iLink 真机附件链路仍建议偶尔抽测。

**回归**：`bash scripts/butler-wechat-owner-sim.sh --track ext` — **8/8 PASS**（2026-06-26，`verify_files_exist` 仅用于写盘话术 case）。

---

## 3. 微信真机话术

**可复制话术卡（推荐）**：[`ext5-wechat-phrases-card-2026-06.md`](ext5-wechat-phrases-card-2026-06.md) · 终端 `bash scripts/butler-ext5-wechat-phrases-card.sh`

| # | 发送内容 | 期望 |
|---|----------|------|
| 1 | `/诊断 详细` | 附件 `.txt` 含 `markitdown (stdio) [ok]`、`Extension Verify` 行 `markitdown-ingest [ok]` |
| 2 | `把 docs/ext5-fixture-sample.txt 转成 Markdown`（先 `/切换 灵文1号`） | 回复含转换结果或委派完成；项目内生成/更新 `.md` |
| 3 | manifest：`把这份 PDF 转成 Markdown 放进记忆` | 调 MCP 或委派；`.butler/ingest/` 有新 MD；可选 `butler memory reindex` |
| 4 | manifest：`用 MarkItDown 转换项目里的参考书` | 指向项目内可读路径；无 hallucination 仓库名 |

**样例 fixture**（sim 已用）：`projects/LingWen1/docs/ext5-fixture-sample.txt`（可由 `tests/fixtures/ext5/sample.txt` 复制）。

---

## 4. 结案勾选

真机 1–4 通过后：

```bash
bash scripts/butler-extension-verify.sh markitdown-ingest
```

更新一页纸 §8 **Verify 真机 ✅** 与 [`extension-rd-loop`](../plans/active/extension-rd-loop-2026-06.md) EXT-5 状态。

---

## 5. 常见问题

| 症状 | 处理 |
|------|------|
| `/诊断` 无 markitdown | `BUTLER_MCP_MAX_SERVERS` 升到 4；重启 gateway |
| MCP connect markitdown TimeoutError | 首次 `uvx` 下载慢；`pip install markitdown-mcp` 或 sim 前 prewarm |
| 「找不到 tests/fixtures/…」 | 真机用 **项目内** `docs/` 路径，先 `/切换` 对应项目 |
| 附件无 Extension Verify | 先跑 `butler-extension-verify.sh markitdown-ingest` |
