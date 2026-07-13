# P1 #4 · content vs dev 委派边界硬化 — 设计 spec

> **For agentic workers:** 配套实施计划见 `docs/superpowers/plans/2026-07-13-p1-4-delegation-boundary.md`（plan 阶段产出）。  
> **背景**：P1 #4 在 `projects/LingWen1/docs/interview-demo-backlog.md` 标"已约定"，但**未工具强制**。本 spec 把 `docs/dual-playbook.md` M2/N2 的约定落到 PreToolUse hook + 配置层。  
> **优先级**：P1（演示前 backlog 剩余硬骨头）；**影响面**：跨项目生效（hook 全局 + 每项目 permissions.yaml 配）。

---

## 1. 目标

让"content agent 写文案、dev agent 改代码"的分工从文档约束变成**实时拦截**：

- content agent 写到代码路径（`src/`、`tests/`、`butler/`、`scripts/`）→ hook 拒绝
- dev agent 写到剧本/正文路径（`projects/<slug>/docs/`、runtime jobs.yaml 描述字段）→ hook 拒绝
- 演示时 M2/N2 委派**真的过不了错误路径**，而不是靠人工记得

## 2. 设计

### 2.1 边界语义

**路径前缀 + agent role 二维 ACL**（沿用 brainstorming 决定）。

| 维度 | 取值 | 来源 |
|------|------|------|
| agent role | `content` / `dev` | `os.environ["BUTLER_AGENT_ROLE"]`（dispatcher 注入） |
| tool action | `write` / `edit`（仅这两个走 hook） | `tool_name` in {`Write`, `Edit`} |
| path target | 文件相对仓根 | `tool_input.file_path` |

### 2.2 默认路径清单

写到 `projects/<slug>/.butler/permissions.yaml` 的 `delegation:` 段（沿用 brainstorming 决定 — 复用 permissions.yaml）：

```yaml
delegation:
  content:
    write_allow:
      - "projects/<slug>/docs/**"
      - "projects/<slug>/docs/archive/**"
      - "README.md"
      - "docs/interview-demo-backlog.md"        # 项目本档
    write_deny:
      - "src/**"
      - "tests/**"
      - "butler/**"
      - "scripts/**"
      - "pyproject.toml"
      - ".pre-commit-config.yaml"
  dev:
    write_allow:
      - "src/**"
      - "tests/**"
      - "scripts/**"
      - "butler/**"
      - "pyproject.toml"
      - ".pre-commit-config.yaml"
      - "projects/<slug>/.butler/permissions.yaml"
      - "projects/<slug>/runtime/jobs.yaml"
    write_deny:
      - "projects/<slug>/docs/**"
      - "projects/<slug>/docs/archive/**"
```

> 规则合并顺序：**deny 优先于 allow**（demos 拒绝胜出，避免放行被绕）。  
> 占位符 `<slug>` 在 hook 内替换为 `BUTLER_ACTIVE_PROJECT` 的值。

### 2.3 Hook 落点

**全局 PreToolUse**（沿用 brainstorming 决定）：

文件：`butler/hooks/delegation_boundary_hook.py`

注册：`.claude/settings.json` → `hooks.PreToolUse[].command` 加：

```json
{
  "matcher": "Write|Edit|MultiEdit",
  "command": "python3 -m butler.hooks.delegation_boundary_hook"
}
```

读取 stdin JSON `{tool_name, tool_input}`；判定逻辑：

```
role = os.environ.get("BUTLER_AGENT_ROLE")  # None → 跳过（兼容 Lead 本体）
if role not in {"content", "dev"}: exit(0)

project = os.environ.get("BUTLER_ACTIVE_PROJECT", "灵文1号")
path = normalize(tool_input.file_path)  # 相对仓根
rules = load_yaml(f"projects/{slug}/.butler/permissions.yaml")["delegation"][role]
if matches_any(path, rules["write_deny"]): exit(2)  # stderr 输出 "[P1#4] ..."
if not matches_any(path, rules["write_allow"]): exit(2)
exit(0)
```

**越界响应**（沿用 brainstorming 决定 — 硬拒绝）：

- `exit code 2`（Claude Code PreToolUse 阻断语义）
- stderr 一行：`[P1#4 delegation boundary] role=<role> 不允许写 path=<path>；dev/content 委派边界拒绝。请确认 role 注入正确或重新委派。`
- 写一条结构化 `butler/audit/delegation-violations.log`（便于演示打印）

### 2.4 role 注入路径

`BUTLER_AGENT_ROLE` 由委派 dispatcher 在调用 `subprocess`/新会话前 `os.environ` 设置：

- 内容委派：`bash scripts/butler-delegate-content.sh <task>` → 内置 `export BUTLER_AGENT_ROLE=content`
- 开发委派：`bash scripts/butler-delegate-dev.sh <task>` → 内置 `export BUTLER_AGENT_ROLE=dev`
- Lead 本体：不设（hook 跳过）

> 现有 `scripts/butler-dev-delegate-smoke.sh` 等作为参照；本 spec 新增 `butler-delegate-content.sh`（如缺）。

### 2.5 不变式 / 反例

- **不**拦 `Read` / `Bash` / `Grep` / `Glob`：只拦 Write 类工具（`Write` / `Edit` / `MultiEdit`）
- **不**拦 Lead 本体：role 缺失时静默放行（避免误伤主公）
- **不**拦 demo 演示脚本（`scripts/butler-demo-*.sh` 自身）：脚本本身可调 `unset BUTLER_AGENT_ROLE` 走 Lead 语义
- **不**改现有 `permissions.yaml` 的 `rules:`（tool-level ACL）— 这是新维度，与 tool deny/ask 正交

## 3. 测试 / 验收

双轨（沿用 brainstorming 决定）：

### 3.1 pytest 单测 — `tests/hooks/test_delegation_boundary_hook.py`

至少 8 个 case：

| Case | role | path | 期望 |
|------|------|------|------|
| `test_content_can_write_docs` | content | `projects/灵文1号/docs/notes.md` | exit 0 |
| `test_content_denied_src` | content | `src/butler/foo.py` | exit 2 |
| `test_content_denied_butler_core` | content | `butler/hooks/x.py` | exit 2 |
| `test_dev_can_write_src` | dev | `src/butler/x.py` | exit 0 |
| `test_dev_can_write_tests` | dev | `tests/hooks/test_x.py` | exit 0 |
| `test_dev_denied_docs` | dev | `projects/灵文1号/docs/x.md` | exit 2 |
| `test_dev_denied_archive_docs` | dev | `projects/灵文1号/docs/archive/x.md` | exit 2 |
| `test_no_role_passthrough` | (无) | 任意 | exit 0（兼容 Lead） |

mock 用 `monkeypatch` 注入 `os.environ` 和 `sys.stdin` JSON。

### 3.2 真机 smoke — `scripts/butler-delegation-boundary-smoke.sh`

模拟两次真实委派：

```bash
#!/usr/bin/env bash
# smoke：跑两个 mock 委派，验证 hook 拒绝方向正确
set -e
cd "$(dirname "$0")/.."

# 1) content agent 试写 src/ → 应被拒
BUTLER_AGENT_ROLE=content python3 -m butler.hooks.delegation_boundary_hook <<'EOF'
{"tool_name":"Write","tool_input":{"file_path":"src/butler/poison.py"}}
EOF
test $? -eq 2 || { echo "FAIL: content should be denied src/"; exit 1; }

# 2) dev agent 试写 docs/ → 应被拒
BUTLER_AGENT_ROLE=dev python3 -m butler.hooks.delegation_boundary_hook <<'EOF'
{"tool_name":"Edit","tool_input":{"file_path":"projects/灵文1号/docs/poison.md"}}
EOF
test $? -eq 2 || { echo "FAIL: dev should be denied docs/"; exit 1; }

# 3) 正常路径 → 应放行
BUTLER_AGENT_ROLE=content python3 -m butler.hooks.delegation_boundary_hook <<'EOF'
{"tool_name":"Write","tool_input":{"file_path":"projects/灵文1号/docs/interview-demo-backlog.md"}}
EOF
test $? -eq 0 || { echo "FAIL: content allowed docs/"; exit 1; }

echo "PASS: delegation boundary smoke"
```

## 4. 边界 / 非目标

- **不**做三级及以上权限（project / role / domain）；本 spec 是 L1 强制
- **不**做 run-time 重配置（动态改 ACL）；如需，开 P2 #10+ follow-up
- **不**拦截 multi-agent 跨会话行为（Lead ↔ subagent 中间层）；只防 subagent 自身 tool 调用
- **不**改 dispatcher 内部逻辑；role 注入只走 env，dispatcher 自带的角色决定（如有）外部设环境变量即可
- **不**兼容旧式 `agent_type: content` 元数据流（被 env 取代）

## 5. 风险 / 缓解

| 风险 | 缓解 |
|------|------|
| dispatcher 漏设 env → content 越权写代码 | smoke + 单测覆盖；CI 跑 `butler-delegate-content.sh --dry-run` 验证 env 是否真的注入 |
| 用户手动 `unset` env 绕过 | 文档明示这是演示用 P1 边界；L2 强化要做应走 ACL 模块（spec 边界外） |
| 中文路径 / slug normalize 出错 | hook 内 `pathlib.PurePath.as_posix()` + lowercase + NFC 归一；单测覆盖 `灵文1号` |
| `.claude/settings.json` 改坏影响其他 hook | 仅追加 PreToolUse 数组项；不改现有 Stop hook |
| 新项目（DemoPilot 等）默认未配 `delegation:` 段 | hook 检测不到 `delegation.<role>` 时**默认放行**（fail-open）+ stderr warn（避免 P1 #4 阻断其他项目演示） |

## 6. 交付物清单

1. `butler/hooks/__init__.py`（如缺）+ `butler/hooks/delegation_boundary_hook.py`
2. `tests/hooks/__init__.py`（如缺）+ `tests/hooks/test_delegation_boundary_hook.py`（8 case）
3. `scripts/butler-delegation-boundary-smoke.sh`
4. `.claude/settings.json` 增加 PreToolUse 数组项
5. `projects/LingWen1/.butler/permissions.yaml` 增加 `delegation:` 段
6. `projects/_template/.butler/permissions.yaml.example`（同步给新项目）
7. `projects/LingWen1/docs/dual-playbook.md` §"自动化守门" 加 `bash scripts/butler-delegation-boundary-smoke.sh`
8. `projects/LingWen1/docs/interview-demo-backlog.md` P1 #4 行更新为 ✅ 已实现（hook + smoke）
9. 演示用法：M2/N2 委派脚本里手动改 `delegation-content` → `src/` 验证拒绝
10. plan：`docs/superpowers/plans/2026-07-13-p1-4-delegation-boundary.md`

## 7. 关联

- 现状：`projects/LingWen1/docs/dual-playbook.md` M2 / N2
- backlog：`projects/LingWen1/docs/interview-demo-backlog.md` §P1 #4
- 现有 hook 参照：`butler/blackboard/integrations/claude_session_end.py` + `.claude/settings.json` Stop
- 权限框架：`projects/LingWen1/.butler/permissions.yaml` `rules:` 段（tool-level）
- 文档层：`docs/superpowers/README.md`（spec/plan 命名约定）

## 8. 变更记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-07-13 | v1 | 初版 spec（brainstorming 收口 8 问） |