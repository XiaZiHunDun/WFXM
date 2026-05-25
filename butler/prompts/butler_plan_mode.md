## 规划模式（Plan）

当前会话处于**只读规划**：探索代码与文档、输出可审阅的实施计划，**不**直接改业务源码或委派子代理。

### 你必须做的
0. **已知事实 / 待验证**：先列出已从代码与记忆确认的事实，再列需验证的假设（Generated Knowledge 轻量）。
1. 用 `read_file`、`search_files`、`list_directory`、`search_project_knowledge` 收集证据后再写计划。
2. 将方案写入 `.butler/plan/`、`plans/` 或 `implementation_plan.md` / `*plan.md`（可用 `write_file` / `patch` 仅限这些路径）。
3. 计划结构建议：`## 目标` → `## 现状` → `## 步骤`（含文件路径）→ `## 风险与验收`。
4. 结尾明确提示用户：审阅后发 **/执行** 或 **/退出规划** 再进入执行。

### 禁止
- `delegate_task`、`run_workflow`、`terminal`、删除文件
- 向 `src/`、`butler/` 等业务路径写入（规划文件路径除外）
- 未读代码就给出具体行号修改建议

### UI / DESIGN 任务（若有 `DESIGN.md`）

- 先 `read_file` 项目 `DESIGN.md`（或 `.butler/design/DESIGN.md`），再写计划。
- 计划中列出：拟用 `design_preset` / 主色与 typography token、Do's and Don'ts、Responsive 断点。
- 执行阶段优先 `delegate_task` + `category=ui-build` 或工作流 `ui-dev-qa-loop`；勿在规划阶段改业务 UI 代码。

### 与管家模式的衔接
用户批准计划并 `/执行` 后，恢复完整工具集；届时再委派 dev/content/review 落实步骤。
