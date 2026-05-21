# 开发操作工具运维

> 设计全文：[`docs/architecture/dev-ops-tools-design.md`](../architecture/dev-ops-tools-design.md)

## 快速启用（WFXM 本机开发）

```bash
# .env
BUTLER_ENABLE_TERMINAL=1
BUTLER_TERMINAL_PROFILE=dev
BUTLER_ENABLE_GIT=1
BUTLER_ENABLE_GIT_WRITE=1    # 仅本机；生产微信网关建议 0
BUTLER_TOOL_SAFE_ROOT=/path/to/WFXM
```

## 生产 / 微信网关（灵文试点）

```bash
BUTLER_ENABLE_TERMINAL=1
BUTLER_TERMINAL_PROFILE=pilot   # python3 + bash，跑 novel-factory
BUTLER_ENABLE_GIT=0             # 或 1 只读，不写
BUTLER_ENABLE_GIT_WRITE=0
BUTLER_TOOL_SAFE_ROOT=/path/to/workspace
```

## 工具一览

| 工具 | 需 env | 说明 |
|------|--------|------|
| `patch` | — | 精确替换；多匹配返回行号提示 |
| `terminal` | `BUTLER_ENABLE_TERMINAL=1` | argv 白名单 + profile |
| `git_status` / `git_diff` / `git_log` | `BUTLER_ENABLE_GIT=1` | 只读 |
| `git_add` / `git_commit` | `+ GIT_WRITE=1` | 工作区内提交 |
| `git_branch` | list→GIT；改分支→GIT_WRITE | 无 push/pull |

## 与 Runtime 分工

| 任务 | 用 |
|------|-----|
| 改代码 + pytest | `delegate_task` → dev_agent + `patch` + `terminal` |
| 看改动 | `git_status` / `git_diff` |
| 批量流水线 | `/运行` / `butler runtime due` |
| 发版提交 | 本机可 `git_*`；远程网关建议人工 git |

## P2 能力

| 工具 / 配置 | 说明 |
|-------------|------|
| `list_runtime_jobs` | 列出当前项目 `jobs.yaml` 任务（Lead / 管家线程可用） |
| `run_runtime_job` | 执行 **readonly** 任务（等同 `/运行`）；返回 `summary`、`report_paths`、`outcome`；mutating 须 `/批准运行` |

**Lead 常用**：`publish-preflight`、`factory-status-daily`、`consistency-weekly`（后两者较慢）。需 `BUTLER_RUNTIME_ENABLED=1`。
| `download_file` | `BUTLER_ENABLE_DOWNLOAD=1`，HTTPS + 域名白名单 |
| `BUTLER_TOOL_AUDIT_JSONL=1` | 工具审计追加到 JSONL |

## 开发实战冒烟

```bash
bash scripts/butler-dev-tools-smoke.sh
```

覆盖：`patch` → `terminal`（跑检查脚本）→ `git_status` → `git_add` → `git_commit`（隔离临时 git 仓库）。

## 验收

```bash
bash scripts/butler-dev-tools-smoke.sh
pytest tests/test_git_tools.py tests/test_dev_ops_p2.py tests/test_tools_registry.py -q
```
