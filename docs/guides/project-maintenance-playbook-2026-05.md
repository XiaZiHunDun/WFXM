# 项目整理与维护手册（代码 / 文档 / 结构 / 配置 / 测试）

> 更新：2026-05-28  
> 适用范围：Butler v4 仓库日常维护、发版前整理、问题排查复核

## 1) 目录结构整理基线

以以下目录作为长期稳定边界：

- `butler/`：产品主代码（Loop、Gateway、Tools、Memory、Runtime）
- `docs/`：架构/指南/规划/运维文档
- `tests/`：单测、集成测、语料测试、拟人对话测试
- `scripts/`：部署、运维、守门、体检脚本
- `projects/`：业务项目工作区（如灵文）
- `archive/`：归档
- `reference/`：外部对照区（非实现事实来源）

整理时原则：

- 运行时代码只放在 `butler/`
- 测试辅助只放在 `tests/`
- 运维脚本只放在 `scripts/`
- 新增配置项必须同步 `.env.example` 与 `docs/config/reference.md`

## 2) 文档整理基线

以以下三份作为文档入口：

- `README.md`：对外总览
- `docs/README.md`：文档导航
- `docs/DOCUMENTATION.md`：文档分层与维护规则

新增或变更功能时，至少同步：

1. 架构变化：`docs/architecture/v4-architecture.md`
2. 配置变化：`.env.example` + `docs/config/reference.md`
3. 运维变化：`docs/guides/*` 对应文档
4. 测试变化：`tests/README.md`

## 3) 配置整理基线

所有可配置能力遵循：

- 环境变量命名统一 `BUTLER_*`
- 默认值写在 `.env.example`
- 行为说明写在 `docs/config/reference.md`
- 运行时可改项优先走 `butler/config_service.py` 白名单

重点能力开关（建议定期复核）：

- `BUTLER_ENABLE_WEB_SEARCH`
- `BUTLER_WEB_SEARCH_TIMEOUT`
- `BUTLER_ENABLE_WEB_FETCH`
- `BUTLER_POST_SESSION_LAYERED`
- `BUTLER_IMAGE_GENERATION`
- `BUTLER_TTS`

## 4) 测试整理基线

日常检查分两层：

- 快速层（PR/日常）：核心守门 + 工具层 + 对话测试收集验证
- 完整层（发版前）：加跑 `tests/corpus` 与五报告守门脚本

统一入口：

```bash
bash scripts/project-health-check.sh quick
bash scripts/project-health-check.sh full
```

## 5) 代码整理基线

推荐每轮改动后的最小清单：

1. 语法与导入检查
2. 新增文件 lint 检查（`ruff check --select E,F`）
3. 相关测试子集通过
4. 文档同步完成
5. 关键命令可回放（写入 `scripts/README.md` 或 `tests/README.md`）

## 6) 发版前整理流程（建议）

```bash
# 1) 项目健康检查（full）
bash scripts/project-health-check.sh full

# 2) 网关 preflight / smoke（按需）
bash scripts/butler-pre-release-smoke.sh

# 3) 真机检查（微信）
# 见 docs/guides/wechat-daily-smoke-checklist.md
```

## 7) 常见“看起来像故障”的情况

- 测试中断伴随 TLS/socket 报错：通常是会话网络中断，不代表代码失败
- 全量测试超时：优先按域分批执行，不要直接判定回归
- 单测单跑通过、全量失败：优先排查环境变量污染（`monkeypatch` 缺失）

## 8) 维护目标

- 结构清晰：新人 10 分钟内定位模块入口
- 配置一致：新增能力无“只改代码不改文档”的漂移
- 测试可执行：有统一入口且能分层回放
- 文档可追溯：任意功能都能从 README -> docs -> tests 找到依据
