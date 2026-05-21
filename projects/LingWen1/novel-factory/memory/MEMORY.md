# 灵文 · 主控 Agent 记忆

## 项目状态
- 当前项目：星陨纪元（✅ 已完成）
- 阶段：✅ PHASE_7_CLOSE 归档闭环完成
- 总章节数：360章
- 版本：v3.0（发布于2026-05-15）

## 关键文件
- 主控人设：`CLAUDE.md`
- 工作流状态：`workflow_state.json`
- 执行脚本：`tools/workflow/run_workflow.sh`

## 调度命令
- 启动Agent：`./run_workflow.sh launch <task> <agent> <desc>`
- 查看任务：`./run_workflow.sh tasks`
- 查看状态：`./run_workflow.sh status`

## 部门结构
- 灵感部门(3) + 作家部门(10) + 审核部门(10) + 读者部门(20) + 汇总部门(3) = 46 Agent
- 状态机驱动 + 人工重大决策

## 已完成优化
- [x] 章节文件命名校验脚本
- [x] 章节文件修复脚本
- [x] 汇总部门 merge 命令
- [x] 仓库重组（03/07/08职责划分）

## 新项目启动流程
1. `./run_workflow.sh init <项目名> <章节数>`  - 初始化工作流
2. 更新 `01_灵感库/` 创建项目文件夹
3. `./run_workflow.sh launch` 启动灵感生成
4. 工作流自动推进，25步闭环
