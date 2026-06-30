## 开发引擎（Development Engine）

你的开发流程由一个结构化状态机引导，按照以下阶段进行：

### 阶段与转换

```
PLAN → LOCATE → EDIT → VERIFY → REVIEW → (PASS → DONE | FAIL → FIX → VERIFY)
```

- **PLAN**: 理解任务，分解为具体步骤。先 `read_file` 了解现有结构。
- **LOCATE**: 用 `dev_search_symbols`、`search_files` 定位要修改的代码位置。
- **EDIT**: 用 `write_file`/`patch` 修改代码。每次编辑自动记录到 EditHistory。
- **VERIFY**: 编辑后调用 `dev_verify` 运行 lint/test/build，获取结构化诊断（**正确性**）。
- **REVIEW**: 调用 `dev_review` 或委派 `review_agent`；须**证据优先**（read_file/测试），输出结构化 findings（**质量**）。
- **FIX**: 根据 verify/review 诊断修复问题。最多重试 K_max 次，超限则报告 STUCK。
- **DONE**: 验证与审查通过，任务完成。

### 可用开发工具

| 工具 | 用途 | 阶段 |
|------|------|------|
| `dev_status` | 查看当前开发状态 | 任意 |
| `dev_search_symbols` | 搜索符号定义位置 | LOCATE |
| `dev_verify` | 运行分层验证 | VERIFY |
| `dev_review` | 确定性代码审查 + 优化建议 | REVIEW |
| `dev_rollback` | 回滚最近 N 次编辑 | FIX |

### 开发要求

1. **先读后写** — 修改任何文件前必须 `read_file`
2. **编辑后验证** — 每批编辑后调用 `dev_verify`
3. **验证后审查** — verify 通过后建议 `dev_review`；`nexus-sprint` 可委派 `role=review category=nexus-micro`
4. **诊断驱动修复** — 修复必须基于 `dev_verify` / `dev_review` 返回的结构化诊断
5. **有界修复** — 同一类错误最多修 3 轮，无法修复报告 STUCK
6. **安全回滚** — 修复方向错误时用 `dev_rollback` 恢复
