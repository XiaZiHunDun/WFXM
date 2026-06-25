# project.yaml `dev` 命令模板（VERIFY 驱动）

> **用途**：让 `butler/dev_engine/verify.py` 与微信 `/测试` 使用项目声明的验证命令，减少 LLM 猜测。  
> **SSOT**：[`butler/dev_engine/verify.py`](../../butler/dev_engine/verify.py) · [`dev-capability-ceiling-vs-cc-cli-2026-06.md`](../plans/decisions/dev-capability-ceiling-vs-cc-cli-2026-06.md)

## 何时需要

- 项目 workspace 下有可执行代码树（`preflight` 会 WARN `dev_test_command_missing`）
- 使用 dev 委派、`/测试`、或 `BUTLER_DEV_AUTO_VERIFY=1` 自动验证

## 可复制段

在 `projects/<slug>/project.yaml` 末尾追加（按仓库调整路径）：

```yaml
dev:
  # 必填（有代码树时）：pytest 或其它测试入口
  test_command: "python3 -m pytest ../../tests/test_foo.py -q --tb=short"
  # 推荐：静态检查 / 语法检查
  lint_command: "python3 -m py_compile ../../butler/main.py"
  # 可选：构建探针；无构建系统可写 true
  build_command: "true"
  # 可选：git 主分支名、源码目录（coding_knowledge / 经验挖掘）
  main_branch: main
  source_dirs:
    - butler/
    - tests/
```

### 路径说明

- **cwd**：委派 workspace 根（例 `projects/DemoPilot`）
- **PYTHONPATH**：自动注入 Butler 仓库根（与 `/测试` 一致）
- 试点项目常用 `../../tests/...`、`../../butler/...` 指向 WFXM 主仓

## 试点示例

| 项目 | `test_command` 要点 |
|------|---------------------|
| 演示试点 | `tests/test_owner_surface.py` 等轻量冒烟 |
| 灵文1号 | `tests/dev_engine/test_verify_layered.py` 等 |

见 [`projects/DemoPilot/project.yaml`](../../projects/DemoPilot/project.yaml)、[`projects/LingWen1/project.yaml`](../../projects/LingWen1/project.yaml)。

## 验证

```bash
# 单测：project.yaml → verify
PYTHONPATH=. pytest tests/dev_engine/test_verify_layered.py -q

# 试点探针（两项目命中 project.yaml）
bash scripts/butler-dev-live-flywheel-checklist.sh --probe

# 全 pilot gate（含 dev-delegate + lead-readonly sim）
bash scripts/butler-pilot-dev-testing.sh
```

## Lead 只读门控（相关）

Lead 项目在用户表达「只读 / 不要改 / 不要委派」时，默认拦截 `delegate_task`（`LEAD_READONLY_NO_DELEGATE`）。开关：`BUTLER_LEAD_READONLY_GATE`（默认 `1`）。见 [`butler/tools/delegate_role_guard.py`](../../butler/tools/delegate_role_guard.py)。
