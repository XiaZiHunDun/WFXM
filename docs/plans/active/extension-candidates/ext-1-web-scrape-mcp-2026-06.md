# EXT-1：网页采集增强（Firecrawl MCP）

> **状态**：Decide ✅ · Integrate ✅ · **Verify ✅**（2026-06-18 微信真机 `mcp_firecrawl_firecrawl_scrape`）  
> **规程**：[`extension-rd-loop-2026-06.md`](../extension-rd-loop-2026-06.md)  
> **对照**：[`firecrawl-butler-comparison-2026-05.md`](../../comparisons/firecrawl-butler-comparison-2026-05.md)

---

## 1. 痛点与信号

| 项 | 内容 |
|----|------|
| **现象** | 内置 `web_fetch`（`BUTLER_ENABLE_WEB_FETCH=0` 默认关）适合静态 HTML + trafilatura；JS 渲染、反爬、站点级 crawl 自建 Playwright 管线成本过高 |
| **信号** | 深度调研 / 竞品分析类任务；`web_fetch` 返回空壳或失败；Firecrawl 对照报告 §6 建议 **MCP 外挂** |
| **不做的信号** | 需要点击登录、表单交互 → 另立项 Browser MCP（权限 `ask`），**不在 EXT-1 范围** |

---

## 2. 候选对比

| 候选 | 类型 | 许可 | 依赖 | 微信 fit | 结论 |
|------|------|------|------|----------|------|
| **A. Firecrawl MCP** (`firecrawl-mcp`) | MCP stdio (npx) | MIT | Node 18+、Firecrawl API Key | 高：scrape/crawl/map 返回 Markdown | **推荐** |
| **B. 增强 builtin `web_fetch`** | Python | 已有 | trafilatura/httpx | 中：仅静态页 | **保留 fallback**，不扩 Playwright |
| **C. Browser-use / Playwright MCP** | MCP | 各异 | 重、慢 | 低（远程微信 + 安全） | **EXT-1b 备选**，默认不接 |

---

## 3. 推荐路径

- [x] **MCP**（Firecrawl）
- [ ] optional-extra（无独立 Python SDK 进 core 计划）
- [ ] 新 builtin 抓取平台
- [ ] 否决

**分工**：

```text
静态 / 简单 URL  →  web_fetch（BUTLER_ENABLE_WEB_FETCH=1）
复杂 / crawl     →  mcp_firecrawl_*（BUTLER_MCP_ENABLED=1 + 白名单）
```

工具名前缀：Butler 注册为 `mcp_{server_id}_{tool}`（默认 prefix `mcp`）。server_id 建议 **`firecrawl`**。

---

## 4. 验收标准

| 类 | 标准 |
|----|------|
| **功能** | Owner 在项目启用 MCP 后，Loop 可调用 Firecrawl scrape（至少 1 个工具）；返回 Markdown 进上下文或 spill |
| **安全** | API Key 仅 `secrets.yaml` 或进程 env；`project.yaml` 含 `mcp_*` 或具体工具名；`permissions.yaml` 对 `mcp_firecrawl_*` 可设 `ask` |
| **开关** | `BUTLER_MCP_ENABLED=1`；`BUTLER_MCP_STDIO_ALLOW_COMMANDS` 含 `npx`；可选 `BUTLER_ENABLE_WEB_FETCH=1` |
| **诊断** | 微信 `/诊断` 或 `butler mcp status` 显示 `firecrawl` connected |
| **守门** | `PYTHONPATH=. pytest tests/test_mcp_features.py tests/test_mcp_deferred.py -q`；有 Key 时手动 scrape 1 URL |

---

## 5. 不做什么（边界）

- 不自建 NuQ/RabbitMQ/Playwright 抓取农场（Firecrawl 对照 §1）
- 不把 Firecrawl 设为默认依赖；**opt-in**
- 不让委派子 Agent 默认开 MCP（现有产品边界）
- 不用 MCP Host /npm 市场动态安装

---

## 6. 接入步骤（Owner 一次性）

### 6.1 前置

```bash
# Node 18+（Firecrawl MCP 官方要求）
node --version
which npx

# Butler MCP 可选包
pip install 'butler-system[mcp]'
```

### 6.2 密钥

在 `~/.butler/secrets.yaml`（勿提交 git）：

```yaml
FIRECRAWL_API_KEY: fc-xxxxxxxx
```

或在 `.env`（gateway 已加载）：

```bash
FIRECRAWL_API_KEY=fc-xxxxxxxx
```

### 6.3 MCP 配置

复制 [`.butler/mcp.yaml.example`](../../../../.butler/mcp.yaml.example) 中 **`firecrawl`** 段到 `~/.butler/mcp.yaml`（或项目 `.butler/mcp.yaml`）。

进程 env（`.env` 或 systemd）：

```bash
BUTLER_MCP_ENABLED=1
# stdio 白名单须含 npx（默认仅 python,python3,uvx）
BUTLER_MCP_STDIO_ALLOW_COMMANDS=python,python3,uvx,npx
# 可选：与 builtin 并用
BUTLER_ENABLE_WEB_FETCH=1
```

### 6.4 项目白名单

`project.yaml` 已有范例（灵文1号）：

```yaml
tools:
  - mcp_*          # 或仅 mcp_firecrawl_*
```

**Lead（厂长）模式**：微信默认项目为灵文时走 `lead` 角色；`project.yaml` 中的 `mcp_*` 会保留进工具白名单（v4 修复前 Lead 会误过滤 MCP）。

`permissions.yaml`（建议 scrape/crawl 走确认）：

```yaml
rules:
  - tool: "mcp_firecrawl_*"
    action: ask
    reason: "外部网页采集（Firecrawl 计费）"
```

### 6.5 验证

```bash
cd /path/to/WFXM
export PYTHONPATH=.
butler mcp status
butler mcp reload          # 改 yaml 后
bash scripts/butler-extension-ext1-preflight.sh   # 可选守门

# gateway 改 env 后
bash scripts/butler-gateway-ops.sh restart
```

微信抽测：「请用 Firecrawl 抓取 https://example.com 并三句话总结」（需 MCP 工具对 LLM 可见）。

---

## 7. 回滚

1. `BUTLER_MCP_ENABLED=0` 或从 `mcp.yaml` 删除 `firecrawl` 段  
2. `butler mcp reload` + gateway restart  
3. 项目 `tools` 去掉 `mcp_*`  
4. 仍可用 `web_fetch` 单独 fallback  

---

## 8. 回写与跟踪

| 里程碑 | 动作 |
|--------|------|
| API Key 配置 + 首次 scrape 成功 | 本页状态 → Integrate ✅；`extension-rd-loop` §5 勾选 |
| 2–4 周使用 | eval / Owner 反馈 → Experience 或调整 permissions |
| 失败 | 记录原因；考虑 EXT-1b 或仅 web_fetch |

**Integrate 记录（2026-06-18）**：`FIRECRAWL_API_KEY` → `.env`；`~/.butler/mcp.yaml` firecrawl；gateway 经 `butler-gateway-exec.sh`；CLI + 微信 `mcp_firecrawl_firecrawl_scrape(https://example.com)` 均 ok；守门 22 passed。

**Verify 记录（2026-06-18）**：微信 `/新对话` 后抽测通过（session transcript 有 `tool_action` + `ok`）。

**检索链真机（2026-06-19）**：微信「帮我搜一下 AI 写作助手竞品，列 3 个」— `web_search`→`firecrawl_search`×3；无 agent/feedback；完整 `https://` 来源；Sudowrite/Novelcrafter/彩云小梦；页脚 `检索4次`；~68s。门控/配额/出站净化见 commit `33ebf65`。

**Track（2026-06-18 起，2–4 周）**：日常查资料类任务优先 Firecrawl；观察成功率与 `permissions.yaml` 的 `ask` 体验；勿与 `fetch-readonly`（uvx）等陈旧项目 MCP 混装。Gateway 内 `web_search` 间歇零结果时用 `bash scripts/butler-web-search-probe.sh` 自查；检索以 Firecrawl 兜底即可。

微信抽测话术：
- scrape：「请用 Firecrawl 抓取 https://example.com 并三句话总结」
- 检索链：「帮我搜一下 AI 写作助手竞品，列 3 个就行」

---

## 9. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-06-18 | 选型一页纸；推荐 Firecrawl MCP；接入步骤与验收定稿 |
| 2026-06-18 | Integrate ✅：Key + mcp.yaml + live scrape + pytest 守门 |
| 2026-06-18 | 修复：Lead `mcp_*` 白名单；gateway PATH（`/bin` + nvm 优先于 conda `npx`） |
| 2026-06-18 | Verify ✅：微信真机 scrape；移除灵文陈旧 `fetch-readonly` 项目 MCP |
| 2026-06-18 | P2：`/新对话` 等 slash 单气泡；同轮 Firecrawl scrape URL 去重 |
| 2026-06-18 | 双回复根因：gateway 单实例 flock + restart 清孤儿；P2 改经 bridge/metadata 跨线程 |
| 2026-06-19 | 检索链真机 ✅：门控+配额+来源 URL；封 agent/feedback；commit `33ebf65` |
