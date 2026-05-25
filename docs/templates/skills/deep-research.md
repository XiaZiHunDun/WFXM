---
name: deep-research
description: 深度调研：web_fetch + 项目 RAG + 结构化结论（DeerFlow 方法论子集）
triggers:
  - 深度调研
  - deep research
  - 调研报告
  - 竞品分析
  - 文献综述
version: 1
---

# deep-research

1. **澄清范围**：目标问题、时间范围、必含/排除来源；信息不足时用 `ask_clarification`。
2. **检索顺序**：
   - `search_project_knowledge` / `butler_recall` 查项目已有材料；
   - `read_file` 读关键本地文档；
   - 对外 URL 用 `web_fetch`（若工具可用），勿臆造链接内容。
3. **综合**：按「背景 → 发现 → 对比 → 风险 → 建议」输出；每条结论标注来源（文件路径或 URL）。
4. **交付**：Markdown 摘要 + 可选写入 `docs/research/<topic>-YYYY-MM.md`（需用户同意改仓库）。
5. **禁止**：未验证来源、一次性超长 paste；优先 delegate 子代理 `content` 或 `review` 角色写终稿。
