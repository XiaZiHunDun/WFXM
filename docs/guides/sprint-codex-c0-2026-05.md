# Sprint Codex-C0（2026-05）

> 总索引：[codex-butler-comparison-2026-05.md](../plans/codex-butler-comparison-2026-05.md)

## 已落地

| 项 | 文件 | 环境变量 |
|----|------|----------|
| C0-3 命令归一化 | `butler/tools/command_canonicalize.py` | — |
| C0-1 压缩相位 | `butler/core/compaction_phase.py` | `BUTLER_MID_TURN_COMPACT=1` |
| C0-2 Execpolicy | `butler/execpolicy/` | `BUTLER_EXECPOLICY=1` |
| C0-4 自动审批 | `butler/core/auto_review.py` | `BUTLER_AUTO_REVIEW=0` |

## 内置工作流

无新增；与 [sprint-roadmap-2026-05.md](./sprint-roadmap-2026-05.md) 正交。

## Execpolicy 配置

`~/.butler/execpolicy.yaml` 或项目 `.butler/execpolicy.yaml`：

```yaml
rules:
  - pattern: ["git", "status"]
    decision: allow
    match: ["git status"]
  - pattern: ["rm", "-rf"]
    decision: forbidden
    justification: "禁止递归删除"
```

## 验收

```bash
PYTHONPATH=. pytest tests/test_sprint_codex_c0.py -q
```

## 后续 C1

已迁移至 [sprint-codex-c1-2026-05.md](./sprint-codex-c1-2026-05.md)。
