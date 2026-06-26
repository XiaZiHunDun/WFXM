# 扩展季度评审（2026-Q3 → Q4 衔接）

> **规程**：[`extension-rd-loop-2026-06.md`](extension-rd-loop-2026-06.md) §2  
> **Backlog**：[`roadmap-backlog` §3.0](../decisions/roadmap-backlog-and-boundaries-2026-05.md#30-扩展选型与接入extension-rd-loop) · **PROD-P2-04**  
> **日期**：2026-06-22

---

## 1. Observe（观测信号）

| 信号源 | 2026-06 快照 | 含义 |
|--------|--------------|------|
| EXT Verify | firecrawl / todoist-readonly / **github-readonly** manifest + golden | OpenAPI 复用路径已验证（EXT-2 → EXT-4） |
| `/诊断` MCP 段 | `github [ok]` + Extension Verify 行（真机 2026-06-22） | 第二 OpenAPI 试点生产可用 |
| 记忆 ingest | EXT-3 CLI `butler memory ingest` 绿；灵文参考书试点 | PDF/Office **进料**仍偏 CLI，微信侧缺「发文件即 ingest」 |
| 网页采集 | EXT-1 Firecrawl + builtin `web_fetch` | JS/反爬仍依赖 MCP；Browser 交互 **未**接 |
| eval / B9 | delegate 与记忆探针 PASS | 暂无「必须新 MCP 才能过门」硬阻塞 |
| Owner 原话（归纳） | 「接某某 API」「参考书入库」「查 GitHub」 | OpenAPI 型需求重复；ingest 与 Browser 分列 |

**缺口陈述（1 段）**：Q3 四条 EXT 试点（采集 / OpenAPI×2 / ingest CLI）已覆盖 80% 长尾；**Q4 优先**应是 **EXT-3 的 MCP 化（MarkItDown）** 以补微信触达，而非再开重型 builtin 或 Browser 默认路径。

---

## 2. Track — EXT-1 … EXT-4 状态

| ID | 能力 | Decide | Integrate | Verify | 一页纸 |
|----|------|--------|-----------|--------|--------|
| EXT-1 | Firecrawl MCP | ✅ | ✅ | ✅ 2026-06-18 | [ext-1](extension-candidates/ext-1-web-scrape-mcp-2026-06.md) |
| EXT-2 | Todoist OpenAPI MCP | ✅ | ✅ | ✅ 2026-06-20 | [ext-2](extension-candidates/ext-2-openapi-http-2026-06.md) |
| EXT-3 | 文档 ingest CLI | ✅ | ✅ | ✅ 2026-06-20 | [ext-3](extension-candidates/ext-3-document-ingest-2026-06.md) |
| EXT-4 | GitHub OpenAPI MCP | ✅ A | ✅ | ✅ 2026-06-22 | [ext-4](extension-candidates/ext-4-second-openapi-2026-06.md) |

**EXT-4 守门**：`bash scripts/butler-extension-ext4-gate.sh` · manifest [`.butler/extensions/github-readonly/manifest.yaml`](../../../.butler/extensions/github-readonly/manifest.yaml)

---

## 3. Research — EXT-5+ 候选排序（2026-Q4）

| 优先级 | ID | 候选 | 类型 | 依赖/风险 | 微信 fit | 建议 |
|--------|-----|------|------|-----------|----------|------|
| **P0** | **EXT-5** | **MarkItDown MCP** | MCP stdio | `documents` extra；无 SSRF | 高：PDF/Office→MD→ingest | **立项一页纸** → Owner Decide |
| P1 | EXT-5b | Browser / Playwright MCP | MCP | 重、慢、`ask` 权限 | 低（远程微信） | **暂缓**；EXT-1 已标注 EXT-1b |
| P2 | EXT-6 | 第三 OpenAPI（Linear / Notion 只读） | OpenAPI MCP | 同 EXT-2/4 模板 | 中（看 Owner 工具栈） | 有明确 SaaS 需求再 Decide |
| P3 | EXT-7 | PostgreSQL read-only MCP | MCP catalog | DB 凭证、SQL 误用 | 中（dev 项目） | Backlog；优先 OpenAPI 型 |

**推荐路径（Agent）**：下一项走 **EXT-5 MarkItDown MCP**，复用 EXT-4 manifest / verify / preflight 模式；**不**改 core 默认依赖。

---

## 4. Decide（Owner）

| 项 | 状态 |
|----|------|
| EXT-4 GitHub OpenAPI | ✅ **已 Decide + Verify**（见 ext-4 一页纸） |
| EXT-5 MarkItDown MCP | ✅ **Owner 批准 A** · Integrate ✅ — [ext-5](extension-candidates/ext-5-markitdown-mcp-2026-06.md) · Verify sim ✅ · 真机话术 ⏳ |
| EXT-5b Browser MCP | ❌ **暂不立项**（安全 + ROI） |
| EXT-6 第三 OpenAPI | ⏸ **按需**（Owner 指定 SaaS 后复制 EXT-4 规程） |

---

## 5. 下一动作（Integrate 前）

1. Owner 读 EXT-5 一页纸 → 确认 / 否决 / 改候选  
2. 若批准 EXT-5：`manifest.yaml` + `butler-extension-ext5-*` + `butler-extension-verify.sh markitdown-ingest`  
3. 季度末更新本文 Track 表与 `roadmap-backlog` §3.0

---

## 6. 相关守门

```bash
# EXT-4 回归（无 token 时 golden 跳过）
bash scripts/butler-extension-ext4-gate.sh

# 扩展总览（MCP 开 + token 时）
bash scripts/butler-extension-verify.sh github-readonly
```
