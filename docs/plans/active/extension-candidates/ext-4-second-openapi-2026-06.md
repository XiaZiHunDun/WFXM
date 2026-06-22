# EXT-4：第二 OpenAPI MCP（候选队列）

> **状态**：Research（2026-06-22）· **未 Decide** — 须 Owner 选试点 API + token  
> **规程**：[`extension-rd-loop-2026-06.md`](../extension-rd-loop-2026-06.md)  
> **前置**：EXT-2 Todoist ✅（OpenAPI MCP 路径已验）

---

## 1. 痛点与信号

| 项 | 内容 |
|----|------|
| **现象** | 已有 Firecrawl + Todoist；Owner 可能重复「接某某 REST」 |
| **信号** | P2 backlog「第二个 OpenAPI MCP」；`/诊断` 工具重叠需降噪（2026-06-22 已接 orthogonality lint） |
| **约束** | 同 EXT-2：stdio + npx + 只读 GET 试点 + `secrets.yaml` |

---

## 2. 候选（2–3）

| 候选 | 类型 | 只读试点 | fit | 依赖 |
|------|------|----------|-----|------|
| **A. GitHub REST** | OpenAPI MCP | `GET /user`、`GET /repos/{owner}/{repo}` | 高（工程管家常查 repo/issue） | `GITHUB_TOKEN` |
| **B. 专用 `github` MCP** | 专用 MCP Server | `search_repositories` 等 | 高（catalog 已有模板） | 同左；非 OpenAPI 通用路径 |
| **C. 内网只读 OpenAPI** | OpenAPI MCP | 1 个 GET 健康检查 | 中（无公网依赖） | 内网 token |

**推荐（Research）**：若目标是 **验证第二条 OpenAPI 复用 EXT-2 管线** → **A**（pin `~/.butler/openapi/github-readonly.yml`）；若目标是 **最快可用** → **B**（`butler mcp add github`，见 `skill-mcp-registry`）。

---

## 3. 验收标准（Decide 后）

- `~/.butler/mcp.yaml` 新 server 块 + preflight 脚本 `butler-extension-ext4-preflight.sh`
- `project.yaml` / permissions 只读白名单
- 微信：`/诊断` MCP 段显示 `[ok]`；一句只读查询真机
- 守门：`test_mcp_features.py` 子集 + `butler-pre-release-smoke.sh`

---

## 4. 不做什么

- 不写 POST/merge/issue 变更类工具（首期）
- 不默认启用（须 `BUTLER_MCP_ENABLED=1` + Owner token）
- 不替代 EXT-1 Firecrawl / EXT-3 ingest

---

## 5. 下一步（Owner）

1. 选 **A（OpenAPI）** 或 **B（专用 github MCP）**
2. 提供 token / 试点项目
3. Agent 走 Integrate → Verify → 更新 `extension-rd-loop` Track 表
