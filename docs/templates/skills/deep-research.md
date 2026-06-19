---
name: deep-research
description: 深度调研：web_search + web_fetch + Firecrawl + 项目 RAG（DeerFlow 方法论子集）
triggers:
  - 深度调研
  - deep research
  - 调研报告
  - 竞品分析
  - 文献综述
version: 1
preferred_tools:
  - search_project_knowledge
  - butler_recall
  - web_search
  - web_fetch
  - mcp_firecrawl_scrape
  - read_file
network_search_policy:
  max_firecrawl_search_per_turn: 3
  max_firecrawl_agent_per_turn: 0
  prefer_web_search_before_firecrawl: true
---

# deep-research

1. **澄清范围**：目标问题、时间范围、必含/排除来源；信息不足时用 `ask_clarification`。
2. **检索顺序**：
   - `search_project_knowledge` / `butler_recall` 查项目已有材料；
   - `read_file` 读关键本地文档；
   - 对外 URL：先用 `web_search`（`BUTLER_ENABLE_WEB_SEARCH=1` 且项目 tools 含 `web_search`）找链接；
   - 再用 `web_fetch`（`BUTLER_ENABLE_WEB_FETCH=1`）；若失败或需 JS/crawl 且 MCP 已开，用 `mcp_firecrawl_scrape` 读已选 URL（见 [`ext-1-web-scrape-mcp`](../../plans/active/extension-candidates/ext-1-web-scrape-mcp-2026-06.md)）；勿臆造链接内容。
   - **禁止**一轮内连续 10+ 次 `mcp_firecrawl_*_search`；`web_search` 可用时必须先用它找链接，Firecrawl search 每轮 ≤3 次且优先 scrape 已有 URL。
   - `web_search` 单次总预算默认 60s（`BUTLER_WEB_SEARCH_BUDGET`）；超时或零结果后立即改用 Firecrawl，勿重复空搜。本机有 HTTP 代理时默认只走代理（`BUTLER_WEB_SEARCH_TRY_DIRECT=1` 才试直连）。
   - **禁止** `mcp_firecrawl_*_agent`、`*_feedback` 等 mutating/高成本 MCP（检索场景默认上限均为 0）。
   - `web_search` 零结果时：用 `firecrawl_search` 拿 URL → `mcp_firecrawl_scrape` 读正文 → 总结；**禁止**向用户提及审批/确认/内部流程。
3. **综合**：按「背景 → 发现 → 对比 → 风险 → 建议」输出；**每条结论必须标注来源**（文件路径或完整 `https://` URL，禁止只写域名）。微信短答格式：`来源：https://...`
   - **小说/长篇竞品**优先：Sudowrite、Novelcrafter、彩云小梦、秘塔写作猫等；勿把 Jasper/Copy.ai 等营销文案工具当作默认答案，除非用户明确要商业文案场景。
4. **交付**：Markdown 摘要 + 可选写入 `docs/research/<topic>-YYYY-MM.md`（需用户同意改仓库）。
5. **禁止**：未验证来源、一次性超长 paste；优先 delegate 子代理 `content` 或 `review` 角色写终稿。
