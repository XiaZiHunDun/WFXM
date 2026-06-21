# EXT-2：声明式 HTTP / OpenAPI 工具

> **状态**：Research ✅（2026-06-20）· Decide ✅（2026-06-19，试点 **Todoist**）· Integrate ✅（2026-06-20）· **Verify ✅**（2026-06-20 微信真机）  
> **规程**：[`extension-rd-loop-2026-06.md`](../extension-rd-loop-2026-06.md)  
> **对照**：[`dify-butler-comparison-2026-05.md`](../../comparisons/dify-butler-comparison-2026-05.md) §3.4 · [`butler-mcp-capability-2026-05.md`](../../../guides/butler-mcp-capability-2026-05.md)

---

## 1. 痛点与信号

| 项 | 内容 |
|----|------|
| **现象** | 每个 SaaS / 内网 REST 若写 builtin 周期长；Dify 类「OpenAPI → tool」成熟 |
| **信号** | `roadmap-backlog` §3.2；Owner 未来可能重复「接某某 API」 |
| **已有近似** | `fetch-readonly`（`mcp-server-fetch`）= **泛 HTTP GET**，非 OpenAPI 多操作；`github` MCP = 专用，非通用 OpenAPI |
| **不做的信号** | Plugin daemon、全量 MCP Host、OpenAPI 平台进 core 默认依赖 |

---

## 2. 候选对比（Research 2026-06-20）

| 候选 | 类型 | 运行方式 | Butler fit | 依赖 | 维护 | 结论 |
|------|------|----------|------------|------|------|------|
| **A. `@ivotoby/openapi-mcp-server`** | MCP stdio | `npx -y @ivotoby/openapi-mcp-server` + spec URL/路径 | **高**：与 EXT-1 `npx` 同型 | Node 18+、`npx` 白名单 | GitHub 活跃（v1.14, 2026-03） | **Decide 首选** |
| **B. `mcp-openapi`（rmasters）** | MCP stdio | `uvx mcp-openapi --openapi-url=… stdio` | **高**：`uvx` 已在默认白名单 | Python/uvx | PyPI 包，较小社区 | **Decide 备选**（偏 Python 栈） |
| **C. FastMCP `from_openapi()`** | 自建脚本 | 仓库内 `scripts/mcp-*.py` + `python3` stdio | 中：需维护脚本与 httpx 客户端 | `fastmcp`、optional-extra | 官方文档完善 | **Integrate 工作量大于 A/B** |
| **D. Stainless / Speakeasy / Mintlify 生成** | 托管或生成物 | 多为 HTTP MCP 或需 CI 生成 | 低：微信 Gateway 偏本机 stdio；远程 HTTP 增 OAuth/运维面 | 商业/生成管线 | 适合 API 厂商对外 | **不作为 Butler 首试点** |
| **E. Butler `.butler/tools/*.yaml`** | 内置声明 | 解析 OpenAPI → registry 工具 | 中–高开发：SSRF、鉴权、schema 需产品定义 | 无 Node | 自控 | **MCP 不够时再立项**（roadmap 原话） |
| **F. 维持现状** | 手工 `mcp.yaml` | 每 SaaS 找**专用** MCP（如 github、firecrawl） | 已验证 | — | — | API 少时足够 |

### 与 `fetch-readonly` 的边界

| | `fetch-readonly` | OpenAPI MCP（A/B） |
|--|------------------|---------------------|
| 输入 | 单 URL | spec 内**多 operation** → 多 `mcp_*` 工具 |
| 典型用 | 抓一个 HTTP 响应 | 调 REST API（带 path/query/body schema） |
| EXT 归属 | 个人管家只读模板（已存在 catalog） | **EXT-2** |

---

## 3. Decide 结论（2026-06-19，Owner：1 = Todoist）

| 项 | 决定 |
|----|------|
| **试点 API** | [Todoist](https://developer.todoist.com/) **REST API v2** · base `https://api.todoist.com/rest/v2` |
| **OpenAPI spec** | **自维护 v1 只读** `~/.butler/openapi/todoist-v1-readonly.yml`（REST v2 社区 spec 已 **410**） |
| **鉴权** | Personal API Token → `Authorization: Bearer`（env：`TODOIST_API_TOKEN`） |
| **只读 vs 写** | **仅只读 GET**（§6.2 工具白名单）；POST/PUT/DELETE 不进 `tools.allow` |
| **MCP 路径** | **A**：`npx @ivotoby/openapi-mcp-server`（与 EXT-1 同型，须 `npx` 白名单） |
| **安装面** | **租户** `~/.butler/mcp.yaml`（个人待办跨项目）；项目 `project.yaml` 用 `mcp_todoist_*` 或 `mcp_*` 门控 |
| **否决** | 否 — 继续 EXT-2 试点 |

**路径**：

```text
Todoist OpenAPI spec（URL 或 pin 本地）
    → npx @ivotoby/openapi-mcp-server（stdio）
    → ~/.butler/mcp.yaml server_id=todoist
    → secrets / .env：TODOIST_API_TOKEN
    → project tools 白名单 + permissions ask（mutating 默认不开）
```

**暂不推荐**：Streamable HTTP 远程 MCP 作为微信 Gateway 默认（运维、OAuth 2.1、多会话与 Butler 单进程微信边界冲突）。

### 3.1 API 漂移风险（须 Track）

| 风险 | 说明 | 缓解 |
|------|------|------|
| **REST v2 退役** | Todoist REST v2 已返回 **410**（2026-06-20 实测） | 已切 **api/v1** + 自维护只读 OpenAPI（4 GET） |
| **spec 非官方** | aaddrick/GPT-Actions 社区维护 | pin 本地 yaml；`mcp.lock.json` 记录 spec 版本 |

---

## 4. Butler 接入约束（实现无关，Decide 必守）

| 约束 | 依据 |
|------|------|
| `BUTLER_MCP_ENABLED=1` opt-in | `butler-mcp-capability` |
| stdio 命令 ∈ `BUTLER_MCP_STDIO_ALLOW_COMMANDS` | 默认含 `uvx`；OpenAPI+npx 须加 `npx`（与 EXT-1 同） |
| 密钥仅 `secrets.yaml` / env | 不进 transcript |
| `project.yaml` `tools` 白名单具体 `mcp_<server>_*` | T6 门控 |
| `permissions.yaml` 对 mutating 工具 `ask` | 扩展规程 §5 |
| HTTP transport MCP 须 `hosts_allow` | `mcp.yaml.example`；OpenAPI 服务端**出站**由 MCP 子进程发起，须评估 SSRF |
| 不做动态 MCP 市场安装 | 产品边界 |

---

## 5. 试点验收（Decide 锁定 · Todoist）

| 类 | 标准 |
|----|------|
| **功能** | Loop 可调 ≥1 个 `mcp_todoist_*` 只读工具（列项目/列任务） |
| **微信话术** | 「我 Todoist 今天还有什么待办」「列出灵文相关项目」 |
| **安全** | HTTPS only；`TODOIST_API_TOKEN` 在 secrets / env；mutating 不在 `tools.allow` |
| **开关** | 租户 `~/.butler/mcp.yaml`；`BUTLER_MCP_ENABLED=1` opt-in |
| **守门** | `test_mcp_features.py` · `bash scripts/butler-extension-ext2-preflight.sh` · 可选 live 1 调用 |
| **诊断** | `butler mcp status` / 微信 `/诊断` MCP 段 |

### 技术演示备选（非本次试点）

| 试点 | spec | 用途 |
|------|------|------|
| **httpbin** | `https://httpbin.org/spec.json` | 仅无密钥时验链路 |

---

## 6. Decide 勾选单（2026-06-19 已填）

- [x] 试点 API：**Todoist** · `https://api.todoist.com/rest/v2`
- [x] 只读 vs 写：**只读 GET**（§6.2）
- [x] 路径 **A（npx @ivotoby）**
- [x] 安装面：**租户** `~/.butler/mcp.yaml`
- [x] 否决 EXT-2：**否**

### 6.1 试点只读 MCP 工具名（`tools.allow` · probe 后）

`@ivotoby/openapi-mcp-server` 注册名为 **短 slug**（非 operationId）。v1 只读试点：

| MCP tool | Butler 注册名 | 用途 |
|----------|---------------|------|
| `lst-projects` | `mcp_todoist_lst_projects` | 列项目 |
| `get-project` | `mcp_todoist_get_project` | 单项目（需 `project_id`） |
| `lst-tasks` | `mcp_todoist_lst_tasks` | 列任务（可 `project_id` / `limit`） |
| `get-task` | `mcp_todoist_get_task` | 单任务（需 `task_id`） |

**默认不开**：所有 POST/DELETE 及官方 `@doist/todoist-mcp` 写工具。

**槽位**：`BUTLER_MCP_MAX_TOOLS=20`；Firecrawl `tools.allow` 已收窄为 scrape/crawl/map（与 EXT-1 一致），避免挤占 Todoist。

### 6.2 密钥

```yaml
# ~/.butler/secrets.yaml（推荐）
TODOIST_API_TOKEN: "0123456789abcdef0123456789abcdef01234567"
```

或 gateway `.env`（与 EXT-1 Firecrawl 同型）：

```bash
TODOIST_API_TOKEN=0123456789abcdef0123456789abcdef01234567
```

注册：Todoist Web → 头像 → Settings → Integrations → Developer → **Copy API token**。

---

## 7. Integrate 清单（Todoist，待 token 后执行）

### 7.1 前置

```bash
# Node 18+、npx 在 PATH
pip install 'butler-system[mcp]'   # 若未装

# .env 或 gateway env
BUTLER_MCP_ENABLED=1
BUTLER_MCP_STDIO_ALLOW_COMMANDS=python,python3,uvx,npx
```

可选 pin spec（避免 raw.githubusercontent.com 漂移）：

```bash
mkdir -p ~/.butler/openapi
curl -fsSL -o ~/.butler/openapi/todoist-rest-v2.yml \
  'https://raw.githubusercontent.com/aaddrick/GPT-Actions/main/Todoist/REST/V2/todoist_rest_v2_openapi-3.1.0.yml'
```

### 7.2 `~/.butler/mcp.yaml`（路径 A · Todoist）

仓库示例见 [`.butler/mcp.yaml.example`](../../../../.butler/mcp.yaml.example) **`todoist`** 段。

```yaml
version: 1
servers:
  todoist:
    transport: stdio
    command: npx
    args:
      - "-y"
      - "@ivotoby/openapi-mcp-server"
      - "--api-base-url"
      - "https://api.todoist.com/rest/v2"
      - "--openapi-spec"
      - "/home/<user>/.butler/openapi/todoist-rest-v2.yml"   # 或 §7.1 的 raw URL
    timeout_seconds: 90
    env:
      API_HEADERS: "Authorization:Bearer ${TODOIST_API_TOKEN}"
    tools:
      allow:
        - getAllProjects
        - getProject
        - getActiveTasks
        - getActiveTask
        - getAllSections
        - getSingleSection
        - getAllPersonalLabels
        - getPersonalLabel
    classify:
      getAllProjects: readonly
      getProject: readonly
      getActiveTasks: readonly
      getActiveTask: readonly
      getAllSections: readonly
      getSingleSection: readonly
      getAllPersonalLabels: readonly
      getPersonalLabel: readonly
```

> `API_HEADERS` 格式为 `key:value`（ivo-toby 约定）；`${TODOIST_API_TOKEN}` 由 Butler `_expand_env` 从进程环境解析。

### 7.3 项目白名单与权限

`projects/LingWen1/project.yaml` 已有 `mcp_*`。若需收窄：

```yaml
tools:
  - mcp_todoist_getAllProjects
  - mcp_todoist_getActiveTasks
  # 或保留 mcp_* 通配
```

`permissions.yaml`（租户或项目，建议 mutating 兜底）：

```yaml
rules:
  - tool: "mcp_todoist_*"
    action: ask
    reason: "Todoist 外部 API（试点只读；写操作未开放）"
```

### 7.4 验证

```bash
cd /path/to/WFXM
export PYTHONPATH=.
bash scripts/butler-extension-ext2-preflight.sh
butler mcp reload
butler mcp status    # 应见 todoist connected / tools listed

# gateway 改 env 后
bash scripts/butler-gateway-ops.sh restart

PYTHONPATH=. pytest tests/test_mcp_features.py -q
```

**微信抽测**：「请列出我 Todoist 里的所有项目」或「今天有哪些待办」。

probe 若工具名与 operationId 不一致，以 `butler mcp status` 输出为准，回改 `tools.allow`。

### 7.5 回滚

1. 从 `mcp.yaml` 删除 `todoist` 段，或 `BUTLER_MCP_ENABLED=0`
2. `butler mcp reload` + gateway restart
3. 项目 `tools` 去掉 `mcp_todoist_*`
4. Todoist 侧可 **Issue a new API token** 作废旧 token

### 7.6 路径 B（备选，未选）

```yaml
  todoist:
    transport: stdio
    command: uvx
    args:
      - "mcp-openapi"
      - "--openapi-url=https://raw.githubusercontent.com/aaddrick/GPT-Actions/main/Todoist/REST/V2/todoist_rest_v2_openapi-3.1.0.yml"
      - "stdio"
    timeout_seconds: 90
```

路径 B 的 Bearer 注入方式以 `mcp-openapi` 文档为准；Decide 已选路径 A。

### 7.7 路径 E（延后）

`.butler/tools/<name>.yaml` — 需单独产品 schema 与 `registry` 扩展；**不在本次范围**。

---

## 8. 风险登记

| 风险 | 缓解 |
|------|------|
| OpenAPI 全量 endpoints → 工具爆炸 | `tools.allow` 只开只读；或 spec 过滤 |
| SSRF / 内网探测 | 试点禁止 `127.0.0.1` spec；生产用固定 host；审计 mutating |
| spec 与生产 API 漂移 | `mcp.lock.json` + 发版时 `butler mcp reload` |
| 与 `web_fetch` / Firecrawl 混淆 | 文档分工：页面抓取 EXT-1，结构化 API EXT-2 |

---

## 9. 不做什么（边界）

- 不接 Dify plugin_daemon / 全量 OpenAPI 平台
- 不把 OpenAPI 解析器默认写进 `butler/tools/registry.py`
- 不为 EXT-2 单独引入 Playwright/浏览器
- 微信主路径不**依赖** EXT-2（opt-in）

---

## 10. Track

| 日期 | 事件 |
|------|------|
| 2026-06-20 | **Research ✅**：候选 A–F 对比；推荐 MCP npx/uvx；一页纸初版 |
| 2026-06-19 | **Decide ✅**：试点 **Todoist REST v2 只读**；路径 A；租户 `mcp.yaml` |
| 2026-06-20 | **Integrate ✅**：`TODOIST_API_TOKEN` → `.env` + `~/.butler/secrets.yaml`；`todoist` MCP；REST v2 **410** → 自维护 **v1 只读 spec**；live `lst-projects`/`lst-tasks` ok |
| 2026-06-20 | **Verify ✅**：微信「用Todoist列出所有项目」12 项 ·「Inbox有哪些任务」MCP 只读 ok；路由修复（归一化 + intent + web_search 拦截 + tool_pair 预修复） |

### 10.1 两周观察窗（2026-06-20 → 2026-07-04）

| 检查项 | 频率 | 通过标准 | 状态 |
|--------|------|----------|------|
| 只读 4 GET 仍可用 | 每周 | `lst-projects` / `lst-tasks` live 或微信一句 | ⏳ |
| 写操作未误开 | 发版时 | `mcp.yaml` `tools.allow` 无 POST/PUT/DELETE | ✅ |
| API/spec 漂移 | 异常时 | v1 410 或 schema 变 → 更新 `todoist-v1-readonly.yml` | — |
| Token 卫生 | 一次性 | 轮换 `TODOIST_API_TOKEN`（曾出现在聊天） | ⏳ 待 Owner — 见 §10.2 |

### 10.2 Token 轮换（Owner · secrets + `.env` 双写）

1. Todoist Web → [Integrations → Developer](https://todoist.com/prefs/integrations) → **Revoke** 旧 token → **Copy** 新 token  
2. 本机（勿把 token 贴进聊天 / 勿 commit）：

```bash
cd /path/to/WFXM
TODOIST_API_TOKEN_NEW='粘贴新token' bash scripts/butler-todoist-token-rotate.sh
```

3. 微信验证：「用 Todoist 列出所有项目」  
4. 成功后可将上表 Token 卫生标 ✅

当前配置：`~/.butler/secrets.yaml` 与项目 `.env` 均含 `TODOIST_API_TOKEN`；`mcp.yaml` 使用 `${TODOIST_API_TOKEN}` 引用。
| 是否扩展写操作 | 窗末 | 仅 Owner 显式立项；默认维持只读 | 待定 |

---

## 11. 相关链接（调研源）

| 资源 | URL |
|------|-----|
| ivo-toby/openapi-mcp-server | https://github.com/ivo-toby/mcp-openapi-server |
| rmasters/mcp-openapi | https://github.com/rmasters/mcp-openapi |
| FastMCP OpenAPI | https://gofastmcp.com/integrations/openapi |
| Butler MCP 能力 | [`butler-mcp-capability-2026-05.md`](../../../guides/butler-mcp-capability-2026-05.md) |
