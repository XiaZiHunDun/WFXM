# 仓库深度整理 Checklist（2026-05）

> 目标：把“结构漂移、配置漂移、测试漂移”变成可重复检查流程。

## 每周例行（建议）

1. 运行健康检查（quick）

```bash
bash scripts/project-health-check.sh quick
```

2. 生成健康报告（可留档）

```bash
bash scripts/project-health-report.sh quick
```

3. 运行仓库清理审计

```bash
bash scripts/repo-cleanup-audit.sh
```

输出默认在 `logs/maintenance/`。

## 发版前（建议）

1. 全量健康检查

```bash
bash scripts/project-health-check.sh full
```

2. 产出发版前报告

```bash
bash scripts/project-health-report.sh full
```

3. 真机与网关检查

- `bash scripts/butler-pre-release-smoke.sh`
- 参考 `docs/guides/wechat-daily-smoke-checklist.md`

## 核对项

- **代码**：语法通过、关键模块可导入、关键文件 lint clean
- **配置**：`.env.example` 与 `docs/config/reference.md` 键项一致
- **测试**：core gate、工具层、对话 collect、full 模式下 corpus + 五报告守门
- **结构**：root 无异常漂移；大文件无意外入库
- **文档**：README / docs 索引 / tests / scripts 入口同步

## 常见处理策略

- root 出现未知目录：先判断是否临时产物，确认后加入 `.gitignore` 或迁移到 `logs/maintenance/`
- 全量测试超时：优先跑 `project-health-check.sh quick`，再分域补测
- 单测全量失败但单跑通过：优先排查 env 污染与 fixture 隔离
