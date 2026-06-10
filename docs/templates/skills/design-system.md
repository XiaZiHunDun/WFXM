---
name: design-system
description: UI 任务须先读 DESIGN.md，按 token 单组件迭代，遵守 Do's/Don'ts 与断点
triggers:
  - ui
  - frontend
  - design
  - css
  - component
  - 界面
  - 样式
version: 1
preferred_tools:
  - read_file
  - list_directory
---

# design-system

1. **先读** 项目根 `DESIGN.md` 或 `.butler/design/DESIGN.md`（`read_file`），不要凭记忆写 token。
2. **迭代**：一次只改一个 `components.*` 或单一样式面；大段 CSS 分步提交。
3. **遵守** frontmatter / 正文中的 **Do's and Don'ts**、**Responsive Behavior**。
4. **引用**：Handoff / 审查时列出已核对的 token 名（如 `colors.primary`、`typography.body`）。
5. **禁止**：无 DESIGN.md 时声称「符合品牌」；禁止把整份 DESIGN 粘贴进对话。

可选：`project.yaml` 中 `design_preset: <slug>` 指向 `.butler/design/<slug>/DESIGN.md` 或
`BUTLER_DESIGN_PRESET_DIR` 下的参考标本（不打包进主仓库）。
