# EXT-5：MarkItDown MCP（文档 ingest 微信触达）

> **状态**：Decide ✅ **A**（Owner 2026-06-25）· Integrate ✅ · **Verify** handler sim ✅ 2026-06-25 · **真机话术** ⏳（见 [`ext5-wechat-verify`](../../guides/ext5-wechat-verify-2026-06.md)）  
> **规程**：[`extension-rd-loop-2026-06.md`](../extension-rd-loop-2026-06.md) · [`extension-quarterly-review-2026-06.md`](../extension-quarterly-review-2026-06.md)  
> **前置**：EXT-3 sidecar CLI ingest ✅ · EXT-4 manifest/verify 模板 ✅

---

## 1. 痛点与信号

| 项 | 内容 |
|----|------|
| **现象** | EXT-3 已支持 `butler memory ingest` + `.butler/ingest/*.md` + reindex；Owner 在微信侧发 PDF/Office 后仍需 SSH/CLI 或委派 dev 跑 ingest |
| **信号** | 灵文参考书扩容；「把这份资料放进记忆」重复需求；`/诊断` 记忆段有向量但 ingest 目录 stale |
| **不做的信号** | RAGFlow Studio、MinerU 全家桶、默认 core 依赖 markitdown → roadmap §1 / EXT-3 已否决 |

---

## 2. 候选（2–3）

| 候选 | 类型 | 许可 | 依赖重量 | 微信 fit | 结论 |
|------|------|------|----------|----------|------|
| **A. MarkItDown MCP** | MCP stdio | MIT | Node/Python 二选一 Server；`pip install -e ".[documents]"` 可选 | 高：单文件 convert → MD 路径 | **推荐** |
| **B. 维持 EXT-3 CLI only** | sidecar | 已有 | 无新 MCP | 低：无微信一键 | fallback |
| **C. Unstructured MCP** | MCP | Apache-2 | 重、多系统依赖 | 中 | 备选（更重） |

---

## 3. 推荐路径

- [x] **MCP**（MarkItDown 官方或社区 Server，stdio）
- [x] **optional-extra** `documents`（与现有 pyproject 对齐）
- [ ] 新 builtin ingest 管线
- [ ] 否决

**分工**（与 EXT-3 一致，只加 MCP 触达）：

```text
微信 / Loop 调 MCP convert  →  写入 workspace/.butler/ingest/
                           →  butler memory reindex（opt-in 或 manifest hook）
检索                      →  现有 semantic_index（不改 core）
```

---

## 4. Integrate（一键）

```bash
cd /path/to/WFXM
bash scripts/butler-extension-ext5-integrate.sh
bash scripts/butler-extension-ext5-preflight.sh
bash scripts/butler-extension-ext5-verify.sh    # 自动化验收（含 handler sim）
```

真机话术：[`docs/guides/ext5-wechat-verify-2026-06.md`](../../guides/ext5-wechat-verify-2026-06.md)

`.env` **必填**（与 EXT-1..4 并存时）：

```bash
BUTLER_MCP_MAX_SERVERS=4
```

依赖（二选一）：

```bash
pip install markitdown-mcp
# 或
pip install -e ".[documents]"   # 与 EXT-3 CLI 共用 markitdown 栈
```

`project.yaml` 收窄示例：

```yaml
tools:
  allow:
    - mcp_markitdown_convert_to_markdown
    - read_document          # builtin fallback（documents extra）
```

转换后写入 ingest 并 reindex：

```bash
# Agent 调 MCP 得 Markdown 后，或手工：
butler memory ingest --project <name> --dir <含 PDF 的目录>
butler memory reindex --project <name>
```

---

## 5. 验收标准（Integrate 阶段）

| 类 | 标准 |
|----|------|
| **功能** | 1 个试点 workspace；MCP 将 `.pdf`/`.docx` 转为 Markdown 文件；`butler memory search` 可召回标题/片段 |
| **安全** | 仅 project workspace 内路径；`permissions.yaml` 对 `mcp_markitdown_*` 默认 `ask`；无 outbound SSRF（stdio） |
| **开关** | `BUTLER_MCP_ENABLED=1`；`BUTLER_INGEST_ENABLED=1`；project `tools.allow` 含 `mcp_markitdown_*` |
| **Manifest** | `.butler/extensions/markitdown-ingest/manifest.yaml` + golden case |
| **守门** | `bash scripts/butler-extension-ext5-preflight.sh` · `butler-extension-verify.sh markitdown-ingest` · pytest 子集 |

---

## 6. 不做什么（边界）

- 不把 markitdown 写入 core `dependencies`
- 不做全库 cron 批量 ingest（仍用 EXT-3 CLI / 项目脚本）
- 不接 Browser / Playwright（见 EXT-5b 暂缓）
- 不替代 `memory ingest` builtin CLI

---

## 7. 回滚

1. 从 `mcp.yaml` 移除 `markitdown` server 或 `BUTLER_MCP_ENABLED=0`
2. 删除 project `tools.allow` 中 `mcp_markitdown_*`
3. 已写入 `.butler/ingest/` 的 MD 可保留或手工清理

---

## 8. Owner Decide

- [x] **批准 EXT-5 A** — Integrate ✅ 2026-06-25
- [x] **Verify 自动化** — `butler-extension-ext5-verify.sh` + handler sim ✅ 2026-06-26（全量 PASS）
- [ ] **Verify 真机话术** — 微信 §3 四句（[`话术卡`](../../../guides/ext5-wechat-phrases-card-2026-06.md) · `butler-ext5-wechat-phrases-card.sh`）

---

## 9. Track

| 日期 | 事件 |
|------|------|
| 2026-06-22 | Research + 季度评审 P0 推荐 |
| 2026-06-25 | Owner 批准 A；manifest + integrate/preflight/gate |
| 2026-06-25 | handler sim + `BUTLER_MCP_MAX_SERVERS=4`；verify 指南 |
| 2026-06-26 | `butler-owner-week1-ops-sim` + ext5-verify 全量 PASS；G1-04 首条 owner_hard_feedback |
