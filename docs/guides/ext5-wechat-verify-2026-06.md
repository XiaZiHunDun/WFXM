# EXT-5 MarkItDown — 微信真机验收（2026-06）

> **前置**：Integrate ✅ · handler sim ✅ · **本页 = 生产 gateway 真机话术**  
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

---

## 3. 微信真机话术

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
