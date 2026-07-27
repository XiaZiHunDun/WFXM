# Butler Scripts — 脚本目录

> **层级**：脚本 / 工具  
> **父文档**：[`../AGENTS.md`](../AGENTS.md)  
> **架构参考**：[`../docs/architecture/v4-architecture.md`](../docs/architecture/v4-architecture.md) §7

## 目录结构

```
scripts/
├── README.md                      # 脚本索引文档
├── butler-pytest-fast-gate.sh     # 快速测试门禁
├── butler-mypy-strict-gate.sh     # mypy strict 门禁
├── butler-layer-import-gate.sh    # 层依赖门禁
├── butler-cc-harness-gate.sh      # CC 线束门禁
├── butler-domain-pytest.sh        # 按域测试
├── butler-five-reports-gate.sh    # 五报告门禁
├── p3j-env-hygiene-gate.sh        # 环境变量卫生门禁
├── p3j-env-audit.sh               # 环境变量审计
├── p3i-lazy-import-report.sh      # Lazy Import 报告
├── butler-pilot-dev-testing.sh    # 试点项目测试
└── （其他脚本）
```

## 脚本分类

| 类别 | 脚本 | 用途 |
|------|------|------|
| **测试门禁** | `butler-pytest-fast-gate.sh` | 快速门禁（smoke + 微信附件 + CC 线束 + mypy） |
| | `butler-mypy-strict-gate.sh` | mypy strict 门禁 |
| | `butler-layer-import-gate.sh` | 层依赖门禁（ENG-15） |
| | `butler-cc-harness-gate.sh` | CC 线束门禁 |
| | `butler-five-reports-gate.sh` | 五报告门禁（P5–P10） |
| **环境检查** | `p3j-env-hygiene-gate.sh` | 环境变量卫生检查 |
| | `p3j-env-audit.sh` | 环境变量差集审计 |
| **代码质量** | `p3i-lazy-import-report.sh` | Lazy Import 预算报告 |
| **测试运行** | `butler-domain-pytest.sh` | 按域运行测试 |
| | `butler-pilot-dev-testing.sh` | 试点项目开发测试 |

## 注意事项

1. **脚本索引**：`scripts/README.md` 是脚本的完整索引
2. **门禁优先级**：优先运行 `butler-pytest-fast-gate.sh` 快速检查
3. **配置检查**：改 `reference.md` 时运行 `check-dead-env.sh`

## 相关目录

- L9 运营：[`butler/ops/`](../butler/ops/)
