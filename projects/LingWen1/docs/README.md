# 灵文1号 · 项目总览

> 灵文1号是 AI 辅助小说创作平台，集成创作流程管理、技能系统与自动化运行时，支持从灵感触发到完整作品发布的全链路管理。

## 目录结构

| 目录 | 用途 |
|------|------|
| `LingWen1/` | 灵文项目核心代码（厂长模式、流水线） |
| `novel-factory/` | 小说工厂流水线（灵感库→作家工作室→各创作阶段→发布） |
| `docs/` | 项目文档（本文档及验收/规范文档） |
| `skills/` | Butler 技能定义（厂长模式等 Skill 配置） |
| `runtime/` | 运行时任务注册表（jobs.yaml 自动化任务） |
| `MagicMock/` | 外部依赖模拟/测试桩 |
| `demo/` | 演示与示例文件 |

## 核心工作流

novel-factory 流水线分为 4 大阶段、25 个步骤：

1. **灵感库** — 收集素材、设定、主题种子
2. **作家工作室** — 大纲、人物卡、境界体系
3. **各创作阶段** — 初稿→修订→精修→终稿
4. **发布** — 格式化输出、发布检查清单

当前状态：`PHASE_COMPLETE / STEP_25`（主流程已完结，进入维护态）

- 查看进度：`run_workflow novel-factory-status`
- 批量推进：`run_workflow novel-factory [补充说明]`

## 技能体系

`skills/lingwen-project-lead.md` 定义厂长模式：

- 读 `workflow_state.json` 获取当前阶段/步骤
- 委派 dev / content / review 执行具体任务
- 遵守只读探路、委派执行、禁止直接 patch 的工作边界

## 运行时任务

`runtime/jobs.yaml` 注册自动化任务（如 G1 周打卡等），通过 Butler Runtime 定时或手动触发：

```bash
butler runtime run <job-id> --project 灵文1号
```

## 快速开始

1. **查看进度**
   - 命令行：`run_workflow novel-factory-status`
   - 或直接读 `novel-factory/workflow_state.json`

2. **启动新书流水线**
   - 确认「新书立项」
   - 指引 init 脚本初始化 `workflow_state.json`

3. **查看文档**
   - 本项目总览：docs/README.md（本文）
   - 验收规范：docs/ 目录下的验收文档
   - 创作参考：novel-factory/references/ 目录

## 相关文档

- 根目录 README.md：项目入口与快速链接
- novel-factory/workflow_state.json：当前流水线状态（只读）
- skills/lingwen-project-lead.md：厂长 Skill 完整说明
