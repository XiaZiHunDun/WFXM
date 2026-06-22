# EXT-4：第二 OpenAPI MCP — GitHub REST（路径 A）

> **状态**：Decide ✅ **A（OpenAPI）**（2026-06-22）· Integrate ✅ · **Verify ✅**（2026-06-22 真机：仓库列表 + issues）  
> **规程**：[`extension-rd-loop-2026-06.md`](../extension-rd-loop-2026-06.md)  
> **前置**：EXT-2 Todoist ✅（同型 `@ivotoby/openapi-mcp-server`）

---

## 1. Decide（Owner：A）

| 项 | 决定 |
|----|------|
| **路径** | **A** — OpenAPI MCP（非专用 `@modelcontextprotocol/server-github`） |
| **试点 API** | GitHub REST `https://api.github.com` |
| **Spec SSOT** | 仓库 [`.butler/openapi/github-readonly.yml`](../../../../.butler/openapi/github-readonly.yml) → pin `~/.butler/openapi/` |
| **鉴权** | `GITHUB_TOKEN`（fine-grained 或 classic PAT，只读 scope） |
| **只读工具** | 4× GET（见 §3） |

---

## 2. 与 B（专用 MCP）的差异（已否决 B）

| | **A（本方案）** | B（未选） |
|--|-----------------|-----------|
| Server | `@ivotoby/openapi-mcp-server` | `@modelcontextprotocol/server-github` |
| 复用 EXT-2 | ✅ | ❌ |
| 工具面 | 自维护 OpenAPI 裁剪 | 上游手写工具集 |

---

## 3. 只读工具映射

| OpenAPI | MCP `tools.allow` 名 | 用途 |
|---------|----------------------|------|
| `GET /user` | `get-authenticated-usr` | 当前认证用户 |
| `GET /user/repos` | `lst-repos-authenticated-usr` | 列仓库 |
| `GET /repos/{owner}/{repo}` | `get-repo` | 单仓库 |
| `GET /repos/{owner}/{repo}/issues` | `lst-repo-issues` | 列 issues |

> 工具名由 openapi-mcp-server 从 path 生成；以 `npx …` 启动日志为准。

---

## 4. Integrate（一键）

```bash
cd /path/to/WFXM
bash scripts/butler-github-openapi-spec-install.sh
bash scripts/butler-extension-ext4-integrate.sh   # 追加 ~/.butler/mcp.yaml github 段
```

`secrets.yaml` 或 `.env`：

```yaml
GITHUB_TOKEN: "ghp_…"   # 或 fine-grained PAT
```

```bash
# 经典 PAT 若 Bearer 不通，可改 API_HEADERS 为 token 前缀（见 GitHub 文档）
export GITHUB_TOKEN=ghp_…
bash scripts/butler-extension-ext4-preflight.sh
```

项目 `project.yaml` 已有 `mcp_*` 时可全用；收窄示例：

```yaml
tools:
  allow:
    - mcp_github_get-authenticated-usr
    - mcp_github_lst-repos-authenticated-usr
    - mcp_github_get-repo
    - mcp_github_lst-repo-issues
```

（注册名前缀以 Butler `BUTLER_MCP_TOOL_PREFIX` 为准，默认 `mcp_github_*`。）

---

## 5. Verify

| 步 | 命令 / 动作 |
|----|-------------|
| Token 同步 | `bash scripts/butler-github-token-sync.sh`（secrets → `.env`，MCP 子进程必读 env） |
| Preflight | `bash scripts/butler-extension-ext4-preflight.sh`（MCP 开启时 token 仅 secrets → **硬失败**） |
| Extension Verify | `bash scripts/butler-extension-verify.sh github-readonly`（manifest golden cases） |
| 网关 | `butler-gateway-ops.sh restart && verify` |
| 微信 | `/诊断` → MCP 段含 `github [ok]` + **Extension Verify** 行 |
| 真机一句 | 「列出我的 GitHub 仓库」；「列出 WFXM 的 issues」 |

Manifest SSOT：[`.butler/extensions/github-readonly/manifest.yaml`](../../../../.butler/extensions/github-readonly/manifest.yaml)

---

## 6. 回滚

1. 从 `~/.butler/mcp.yaml` 删除 `github:` 段或 `BUTLER_MCP_ENABLED=0`
2. 项目 `tools` 去掉 `mcp_github_*`

---

## 7. Track

| 日期 | 事件 |
|------|------|
| 2026-06-22 | Decide **A**；仓库 spec + integrate/preflight 脚本 |
| 2026-06-22 | Verify ✅ 真机（12 repos + WFXM issues）；Extension Manifest + `butler-extension-verify.sh` |
