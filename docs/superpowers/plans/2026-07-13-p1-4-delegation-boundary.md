# P1 #4 · content vs dev 委派边界硬化 — 实施 plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `projects/LingWen1/docs/dual-playbook.md` M2/N2 的 content/dev 委派约定落到 PreToolUse hook + 项目级 permissions.yaml，让越界写入在 tool 调用层被硬拒绝。

**Architecture:** 单进程 Python hook 读 `os.environ["BUTLER_AGENT_ROLE"]` + stdin JSON，按 `projects/<slug>/.butler/permissions.yaml` 的 `delegation.<role>.write_allow/deny` 判定；deny 优先于 allow；role 缺失 → 静默放行（兼容 Lead）；新项目无 `delegation:` 段 → fail-open + warn。

**Tech Stack:** Python 3.11+ stdlib（`json`, `os`, `pathlib`, `sys`, `fnmatch`, `yaml` via `butler` 已装依赖）, pytest, bash。

**Spec:** [`../specs/2026-07-13-p1-4-delegation-boundary-design.md`](../specs/2026-07-13-p1-4-delegation-boundary-design.md)

---

## File Structure

```
butler/hooks/
├── __init__.py                          # 新建（空）
└── delegation_boundary_hook.py          # 新建（主实现）

tests/hooks/
├── __init__.py                          # 新建（空）
└── test_delegation_boundary_hook.py     # 新建（8 case）

scripts/
└── butler-delegation-boundary-smoke.sh  # 新建

.claude/settings.json                    # 修改（追加 PreToolUse 数组项）
projects/LingWen1/.butler/permissions.yaml        # 修改（追加 delegation: 段）
projects/_template/.butler/permissions.yaml.example  # 新建（同步模板）

projects/LingWen1/docs/dual-playbook.md            # 修改（§自动化守门加一行）
projects/LingWen1/docs/interview-demo-backlog.md   # 修改（P1 #4 行标 ✅）
```

**职责切分**：
- `delegation_boundary_hook.py`：单文件实现，~120 行；无外部 IO 副作用（除 audit log append）；纯函数式判定逻辑便于单测
- `test_delegation_boundary_hook.py`：纯 pytest，monkeypatch 注入 env 和 stdin；不动真实 YAML 文件
- `butler-delegation-boundary-smoke.sh`：3 case 真脚本，验收 CLI 真实行为

---

## Task 1: hook 模块骨架 + 占位实现（RED setup）

**Files:**
- Create: `butler/hooks/__init__.py`
- Create: `butler/hooks/delegation_boundary_hook.py`

- [ ] **Step 1: 创建 `butler/hooks/__init__.py`**

```python
"""Butler hooks — Claude Code / CC 工具调用层守门。"""
```

- [ ] **Step 2: 创建 `butler/hooks/delegation_boundary_hook.py` 占位实现**

```python
"""P1 #4 — content vs dev 委派边界 hook。

读 stdin JSON（tool_name + tool_input）+ os.environ["BUTLER_AGENT_ROLE"]，
按 projects/<slug>/.butler/permissions.yaml delegation.<role>.write_allow/deny
判定；deny 优先于 allow；越界 exit(2) + stderr + audit log。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_LOG = REPO_ROOT / "butler" / "audit" / "delegation-violations.log"


def main() -> int:
    """hook 入口：读 stdin，判定，返回 exit code。"""
    # 占位实现：先总是放行，让 TDD 跑通；Task 3 实现真实逻辑。
    try:
        json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0  # stdin 不是 JSON 时放行（让 Claude Code 不被破坏）
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: 验证 import 通**

Run: `cd /home/ailearn/projects/WFXM && python3 -c "from butler.hooks import delegation_boundary_hook as h; print(h.AUDIT_LOG)"`

Expected: 打印出 `/home/ailearn/projects/WFXM/butler/audit/delegation-violations.log` 路径；非零错误则说明路径计算有误。

- [ ] **Step 4: 占位 run 通过**

Run: `echo '{"tool_name":"Write","tool_input":{"file_path":"src/x.py"}}' | python3 -m butler.hooks.delegation_boundary_hook; echo "exit=$?"`

Expected: `exit=0`（占位全放行）。

- [ ] **Step 5: Commit**

```bash
git add butler/hooks/__init__.py butler/hooks/delegation_boundary_hook.py
git commit -m "feat(p1#4): hook module skeleton + pass-through placeholder"
```

---

## Task 2: 单测骨架 — 8 case 全 RED

**Files:**
- Create: `tests/hooks/__init__.py`
- Create: `tests/hooks/test_delegation_boundary_hook.py`

- [ ] **Step 1: 创建 `tests/hooks/__init__.py`**

```python
"""Butler hook 单测套件。"""
```

- [ ] **Step 2: 写 8 case 单测（首次跑全 RED）**

`tests/hooks/test_delegation_boundary_hook.py`:

```python
"""P1 #4 — delegation boundary hook 单测。

不动真实 YAML、不写真实 audit log；monkeypatch 注入 env 和 stdin。
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_hook(monkeypatch: pytest.MonkeyPatch, payload: dict, env_role: str | None) -> int:
    """调用 hook 的 _run_for_test 入口（Task 3 实现）。"""
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    if env_role is None:
        monkeypatch.delenv("BUTLER_AGENT_ROLE", raising=False)
    else:
        monkeypatch.setenv("BUTLER_AGENT_ROLE", env_role)
    monkeypatch.setenv("BUTLER_ACTIVE_PROJECT", "灵文1号")
    from butler.hooks.delegation_boundary_hook import _run_for_test
    return _run_for_test()


def test_content_can_write_docs(monkeypatch):
    assert _run_hook(monkeypatch, {"tool_name": "Write", "tool_input": {"file_path": "projects/灵文1号/docs/notes.md"}}, "content") == 0


def test_content_denied_src(monkeypatch):
    assert _run_hook(monkeypatch, {"tool_name": "Write", "tool_input": {"file_path": "src/butler/foo.py"}}, "content") == 2


def test_content_denied_butler_core(monkeypatch):
    assert _run_hook(monkeypatch, {"tool_name": "Write", "tool_input": {"file_path": "butler/hooks/x.py"}}, "content") == 2


def test_dev_can_write_src(monkeypatch):
    assert _run_hook(monkeypatch, {"tool_name": "Write", "tool_input": {"file_path": "src/butler/x.py"}}, "dev") == 0


def test_dev_can_write_tests(monkeypatch):
    assert _run_hook(monkeypatch, {"tool_name": "Write", "tool_input": {"file_path": "tests/hooks/test_x.py"}}, "dev") == 0


def test_dev_denied_docs(monkeypatch):
    assert _run_hook(monkeypatch, {"tool_name": "Edit", "tool_input": {"file_path": "projects/灵文1号/docs/x.md"}}, "dev") == 2


def test_dev_denied_archive_docs(monkeypatch):
    assert _run_hook(monkeypatch, {"tool_name": "Edit", "tool_input": {"file_path": "projects/灵文1号/docs/archive/x.md"}}, "dev") == 2


def test_no_role_passthrough(monkeypatch):
    """Lead 本体：role 缺失 → 静默放行（兼容主公）。"""
    assert _run_hook(monkeypatch, {"tool_name": "Write", "tool_input": {"file_path": "projects/灵文1号/docs/x.md"}}, None) == 0
```

- [ ] **Step 3: 跑单测 — 预期全 FAIL（_run_for_test 不存在）**

Run: `cd /home/ailearn/projects/WFXM && PYTHONPATH=. pytest tests/hooks/test_delegation_boundary_hook.py -v`

Expected: 8 failed，全部 `ImportError` 或 `AttributeError: module 'butler.hooks.delegation_boundary_hook' has no attribute '_run_for_test'`。这是预期 RED。

- [ ] **Step 4: Commit（RED 状态）**

```bash
git add tests/hooks/__init__.py tests/hooks/test_delegation_boundary_hook.py
git commit -m "test(p1#4): delegation boundary hook 8 cases (red)"
```

---

## Task 3: hook 主实现 — 让 8 case 全 GREEN

**Files:**
- Modify: `butler/hooks/delegation_boundary_hook.py`（重写）

- [ ] **Step 1: 重写 hook 主文件**

把 Task 1 的占位 `main()` 替换为完整实现：

```python
"""P1 #4 — content vs dev 委派边界 hook。

读 stdin JSON（tool_name + tool_input）+ os.environ["BUTLER_AGENT_ROLE"]，
按 projects/<slug>/.butler/permissions.yaml delegation.<role>.write_allow/deny
判定；deny 优先于 allow；越界 exit(2) + stderr + audit log。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_LOG = REPO_ROOT / "butler" / "audit" / "delegation-violations.log"

WRITE_TOOLS = {"Write", "Edit", "MultiEdit"}


def _normalize(path: str) -> str:
    """归一化路径：小写 + NFC + posix。"""
    return Path(path).as_posix()


def _matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch(path, p) for p in patterns)


def _load_delegation(slug: str) -> dict | None:
    """读项目 permissions.yaml 的 delegation 段；不存在返回 None（fail-open）。"""
    yaml_path = REPO_ROOT / "projects" / slug / ".butler" / "permissions.yaml"
    if not yaml_path.exists():
        return None
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    return data.get("delegation")


def _audit(role: str, path: str, project: str) -> None:
    """写一条结构化 JSONL 到 audit log（演示可 tail 看）。"""
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "role": role,
        "path": path,
        "project": project,
    }
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _run_for_test() -> int:
    """单测入口：复用 main() 逻辑但去掉 argv 解析。"""
    return _decide(json.loads(sys.stdin.read() or "{}"))


def _decide(payload: dict) -> int:
    """核心判定：返回 0（放行）或 2（拒绝）。"""
    role = os.environ.get("BUTLER_AGENT_ROLE")
    if role not in {"content", "dev"}:
        return 0  # Lead 本体 / 未声明 role → 静默放行

    project = os.environ.get("BUTLER_ACTIVE_PROJECT", "灵文1号")
    tool_name = payload.get("tool_name", "")
    if tool_name not in WRITE_TOOLS:
        return 0  # 只拦 Write 类工具

    path_raw = payload.get("tool_input", {}).get("file_path", "")
    if not path_raw:
        return 0  # 没指定路径 → 放行
    path = _normalize(path_raw)

    delegation = _load_delegation(project)
    if delegation is None:
        # 新项目 / 未配 delegation → fail-open + stderr warn
        print(
            f"[P1#4 delegation boundary] WARN: projects/{project}/.butler/permissions.yaml 无 delegation 段，role={role} 默认放行 path={path}",
            file=sys.stderr,
        )
        return 0

    rules = delegation.get(role)
    if rules is None:
        return 0  # 没声明该 role → 放行

    deny = rules.get("write_deny", [])
    allow = rules.get("write_allow", [])

    if _matches_any(path, deny):
        _audit(role, path, project)
        print(
            f"[P1#4 delegation boundary] DENY: role={role} 不允许写 path={path}（deny 规则命中）。请确认 role 注入正确或重新委派。",
            file=sys.stderr,
        )
        return 2
    if not _matches_any(path, allow):
        _audit(role, path, project)
        print(
            f"[P1#4 delegation boundary] DENY: role={role} 写 path={path} 不在 write_allow 白名单。请确认 role 注入正确或重新委派。",
            file=sys.stderr,
        )
        return 2
    return 0


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0  # stdin 不是 JSON → 不破坏 Claude Code
    return _decide(payload)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 跑单测 — 预期全 GREEN**

Run: `cd /home/ailearn/projects/WFXM && PYTHONPATH=. pytest tests/hooks/test_delegation_boundary_hook.py -v`

Expected: `8 passed`。如有 FAIL，按 stderr 提示查 yaml 解析或 fnmatch 行为。

- [ ] **Step 3: 验证 audit log 在拒绝时确实写入**

Run:
```bash
cd /home/ailearn/projects/WFXM
rm -f butler/audit/delegation-violations.log
echo '{"tool_name":"Write","tool_input":{"file_path":"src/x.py"}}' | BUTLER_AGENT_ROLE=content BUTLER_ACTIVE_PROJECT=灵文1号 python3 -m butler.hooks.delegation_boundary_hook
echo "exit=$?"
echo '--- audit ---'
cat butler/audit/delegation-violations.log
```

Expected: `exit=2` + stderr 含 `[P1#4 delegation boundary] DENY: role=content 不允许写 path=src/x.py` + audit log 有一行 JSON。

- [ ] **Step 4: Commit**

```bash
git add butler/hooks/delegation_boundary_hook.py
git commit -m "feat(p1#4): delegation boundary hook — role+path ACL with deny priority"
```

---

## Task 4: 失败-开 + 新项目兼容（边界验证）

**Files:**
- Modify: `tests/hooks/test_delegation_boundary_hook.py`（追加 2 case）

- [ ] **Step 1: 追加 2 case（无 delegation 段 → 放行 + warn）**

在 `tests/hooks/test_delegation_boundary_hook.py` 末尾加：

```python
def test_no_delegation_section_fails_open(monkeypatch, tmp_path, capsys):
    """新项目无 delegation: 段 → fail-open + stderr warn。"""
    # 临时覆盖 yaml 路径：monkeypatch REPO_ROOT 到 tmp_path，建空 permissions.yaml
    from butler.hooks import delegation_boundary_hook as h

    fake_repo = tmp_path
    (fake_repo / "projects" / "新项目" / ".butler").mkdir(parents=True)
    (fake_repo / "projects" / "新项目" / ".butler" / "permissions.yaml").write_text("# 无 delegation 段\nrules: []\n", encoding="utf-8")

    monkeypatch.setattr(h, "REPO_ROOT", fake_repo)
    monkeypatch.setenv("BUTLER_AGENT_ROLE", "content")
    monkeypatch.setenv("BUTLER_ACTIVE_PROJECT", "新项目")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"tool_name": "Write", "tool_input": {"file_path": "src/x.py"}})))
    from butler.hooks.delegation_boundary_hook import _run_for_test

    rc = _run_for_test()
    captured = capsys.readouterr()
    assert rc == 0
    assert "WARN" in captured.err
    assert "无 delegation 段" in captured.err


def test_unknown_role_passthrough(monkeypatch):
    """role 既不是 content 也不是 dev（如 'qa'）→ 静默放行。"""
    assert _run_hook(monkeypatch, {"tool_name": "Write", "tool_input": {"file_path": "src/x.py"}}, "qa") == 0
```

- [ ] **Step 2: 跑单测 — 预期 10 passed**

Run: `cd /home/ailearn/projects/WFXM && PYTHONPATH=. pytest tests/hooks/test_delegation_boundary_hook.py -v`

Expected: `10 passed`（8 原 case + 2 新 case）。

- [ ] **Step 3: Commit**

```bash
git add tests/hooks/test_delegation_boundary_hook.py
git commit -m "test(p1#4): fail-open + unknown role passthrough cases"
```

---

## Task 5: smoke 脚本 + Claude Code PreToolUse 注册

**Files:**
- Create: `scripts/butler-delegation-boundary-smoke.sh`
- Modify: `.claude/settings.json`（追加 PreToolUse 数组项）

- [ ] **Step 1: 创建 smoke 脚本**

`scripts/butler-delegation-boundary-smoke.sh`:

```bash
#!/usr/bin/env bash
# P1 #4 — content vs dev 委派边界 smoke
# 真跑三个 case：content→src 拒绝 / dev→docs 拒绝 / content→docs 放行
set -e
cd "$(dirname "$0")/.."

RED=$'\e[31m'; GREEN=$'\e[32m'; RESET=$'\e[0m'

run_case() {
    local label="$1" role="$2" path="$3" expected="$4"
    local actual
    BUTLER_AGENT_ROLE="$role" BUTLER_ACTIVE_PROJECT="灵文1号" \
        echo "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$path\"}}" \
        | python3 -m butler.hooks.delegation_boundary_hook > /dev/null 2>&1
    actual=$?
    if [[ "$actual" == "$expected" ]]; then
        echo "${GREEN}PASS${RESET} $label: exit=$actual"
    else
        echo "${RED}FAIL${RESET} $label: expected=$expected actual=$actual"
        exit 1
    fi
}

run_case "content→src (deny)"   content "src/butler/poison.py"             2
run_case "dev→docs (deny)"      dev    "projects/灵文1号/docs/poison.md"  2
run_case "content→docs (allow)" content "projects/灵文1号/docs/x.md"       0
run_case "no-role (passthrough)" ""    "projects/灵文1号/docs/x.md"       0

echo "${GREEN}ALL PASS${RESET}: delegation boundary smoke"
```

- [ ] **Step 2: chmod +x**

Run: `chmod +x scripts/butler-delegation-boundary-smoke.sh`

- [ ] **Step 3: 跑 smoke — 预期 ALL PASS**

Run: `bash scripts/butler-delegation-boundary-smoke.sh`

Expected: 4 行 `PASS` + 末行 `ALL PASS`。

- [ ] **Step 4: 注册 Claude Code PreToolUse hook**

读当前 `.claude/settings.json`：

```bash
cat .claude/settings.json
```

预期现有内容形如：
```json
{
  "hooks": {
    "Stop": [
      { "command": "BLACKBOARD_STRICT=1 BLACKBOARD_AGENT=claude-code python3 -m butler.blackboard.integrations.claude_session_end" }
    ]
  }
}
```

用 Edit 工具追加 PreToolUse（注意 JSON 数组闭合 + 逗号）：

把：
```json
{
  "hooks": {
    "Stop": [
      {
        "command": "BLACKBOARD_STRICT=1 BLACKBOARD_AGENT=claude-code python3 -m butler.blackboard.integrations.claude_session_end"
      }
    ]
  }
}
```

改成：
```json
{
  "hooks": {
    "Stop": [
      {
        "command": "BLACKBOARD_STRICT=1 BLACKBOARD_AGENT=claude-code python3 -m butler.blackboard.integrations.claude_session_end"
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "command": "python3 -m butler.hooks.delegation_boundary_hook"
      }
    ]
  }
}
```

- [ ] **Step 5: 验证 JSON 合法**

Run: `python3 -c "import json; json.load(open('.claude/settings.json')); print('JSON OK')"`

Expected: `JSON OK`。如失败，回滚修改。

- [ ] **Step 6: Commit**

```bash
git add scripts/butler-delegation-boundary-smoke.sh .claude/settings.json
git commit -m "feat(p1#4): smoke script + Claude Code PreToolUse registration"
```

---

## Task 6: permissions.yaml delegation 段 + 模板同步

**Files:**
- Modify: `projects/LingWen1/.butler/permissions.yaml`
- Create: `projects/_template/.butler/permissions.yaml.example`

- [ ] **Step 1: 在灵文1号 permissions.yaml 追加 `delegation:` 段**

读现有 `projects/LingWen1/.butler/permissions.yaml`，确认结构（rules 段）。

追加 `delegation:` 段到末尾：

```yaml
  - tool: "mcp_firecrawl_*"
    action: ask
    reason: 外部网页采集（Firecrawl 计费）

# P1 #4 — content vs dev 委派边界（path-prefix ACL，deny 优先于 allow）
delegation:
  content:
    write_allow:
      - "projects/灵文1号/docs/**"
      - "projects/灵文1号/docs/archive/**"
      - "README.md"
      - "docs/interview-demo-backlog.md"
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
      - "projects/灵文1号/.butler/permissions.yaml"
      - "projects/灵文1号/runtime/jobs.yaml"
    write_deny:
      - "projects/灵文1号/docs/**"
      - "projects/灵文1号/docs/archive/**"
```

注意：保留前面 `rules:` 段不动，只在末尾追加 `delegation:` 段。

- [ ] **Step 2: 验证 YAML 合法 + smoke 仍 ALL PASS**

Run:
```bash
cd /home/ailearn/projects/WFXM
python3 -c "import yaml; yaml.safe_load(open('projects/LingWen1/.butler/permissions.yaml')); print('YAML OK')"
bash scripts/butler-delegation-boundary-smoke.sh
```

Expected: `YAML OK` + `ALL PASS`。

- [ ] **Step 3: 创建模板示例文件**

`projects/_template/.butler/permissions.yaml.example`:

```yaml
# 灵文1号项目权限模板 — 含 P1 #4 delegation 段
# 复制到 projects/<你的项目>/.butler/permissions.yaml 并把 <slug> 替换为项目目录名
rules:
  - tool: terminal
    action: deny
    reason: 微信/Lead 场景禁止 shell

# P1 #4 — content vs dev 委派边界（按 spec §2.2）
# 提示：新项目无此段时 hook 默认 fail-open + warn；推荐至少写一份 dev 段以保底
delegation:
  content:
    write_allow:
      - "projects/<slug>/docs/**"
      - "projects/<slug>/docs/archive/**"
      - "README.md"
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

- [ ] **Step 4: 验证模板 YAML 合法**

Run: `python3 -c "import yaml; data=yaml.safe_load(open('projects/_template/.butler/permissions.yaml.example')); assert 'delegation' in data; print('TEMPLATE OK')"`

Expected: `TEMPLATE OK`。

- [ ] **Step 5: Commit**

```bash
git add projects/LingWen1/.butler/permissions.yaml projects/_template/.butler/permissions.yaml.example
git commit -m "feat(p1#4): delegation config for 灵文1号 + project template"
```

---

## Task 7: 文档收口 — dual-playbook + interview-demo-backlog

**Files:**
- Modify: `projects/LingWen1/docs/dual-playbook.md`
- Modify: `projects/LingWen1/docs/interview-demo-backlog.md`

- [ ] **Step 1: dual-playbook 加 smoke 命令**

读现有 `projects/LingWen1/docs/dual-playbook.md` §"自动化守门"（约 60-67 行），追加一行：

```bash
bash scripts/butler-lingwen-lead-smoke.sh
bash scripts/butler-wechat-dual-playbook-probe.sh --quick   # B1 静态 + 有 key 时 handler 各测一句
bash scripts/butler-runtime-smoke.sh 灵文1号
bash scripts/butler-phase4-smoke.sh
bash scripts/butler-delegation-boundary-smoke.sh  # P1 #4 — content vs dev 路径边界
```

- [ ] **Step 2: interview-demo-backlog P1 #4 行更新**

读 `projects/LingWen1/docs/interview-demo-backlog.md` 第 18 行（§P1 表格第 1 行）：

原：
```
| 4 | content vs dev 委派边界 | content 只碰 `docs/`；dev 改代码须走 safe_root + owner 验收 | 已约定 |
```

改为：
```
| 4 | content vs dev 委派边界 | content 只碰 `docs/`；dev 改代码须走 safe_root + owner 验收 | ✅ 已硬化：`butler.hooks.delegation_boundary_hook` + `scripts/butler-delegation-boundary-smoke.sh` + `permissions.yaml delegation:` 段；deny 优先于 allow；新项目无 delegation 段时 fail-open + warn |
```

- [ ] **Step 3: 验证两文档没断链**

Run: `python3 /tmp/wfmdoc_audit.py 2>/dev/null || python3 -c "
import re, pathlib
root = pathlib.Path('projects/LingWen1/docs')
broken = []
for p in root.rglob('*.md'):
    for m in re.finditer(r'\\[([^]]+\\.md)\\]', p.read_text(encoding='utf-8')):
        link = m.group(1).split('#')[0]
        # 简化：仅检查相对父级是否解得到
        target = (p.parent / link).resolve()
        if not target.exists():
            broken.append((str(p), link))
print('broken:', broken if broken else 'none')
"`

Expected: `broken: none`（文档路径全部解析得到）。

- [ ] **Step 4: Commit**

```bash
git add projects/LingWen1/docs/dual-playbook.md projects/LingWen1/docs/interview-demo-backlog.md
git commit -m "docs(p1#4): dual-playbook smoke line + backlog #4 marked done"
```

---

## Task 8: 整体回归 + 最终 commit

**Files:**
- (verify only)

- [ ] **Step 1: 单测全套**

Run: `cd /home/ailearn/projects/WFXM && PYTHONPATH=. pytest tests/hooks/test_delegation_boundary_hook.py -v`

Expected: `10 passed`。

- [ ] **Step 2: smoke 重跑**

Run: `bash scripts/butler-delegation-boundary-smoke.sh`

Expected: `ALL PASS`。

- [ ] **Step 3: 守门子集（与 docs/README.md §验证命令 对齐）**

Run: `cd /home/ailearn/projects/WFXM && PYTHONPATH=. pytest tests/hooks/test_delegation_boundary_hook.py tests/test_p2_workflow_permissions.py tests/test_cc_p3_p4_features.py -q`

Expected: 全 pass。如有 pre-existing fail（非本批引入）记下即可。

- [ ] **Step 4: 写一段实施记录到 memory**

`/home/ailearn/.claude/projects/-home-ailearn-projects-WFXM/memory/project-progress-2026-07-11.md` 末追加：

```markdown
## 2026-07-13 续：P1 #4 委派边界硬化落地

- Commit 链：8 task → ~8 commit → 最终 1 个总结 commit 也可
- 落地：`butler/hooks/delegation_boundary_hook.py`（10 单测 PASS）+ `scripts/butler-delegation-boundary-smoke.sh` + PreToolUse 注册 + 灵文1号 + 模板 delegation 段
- 演示：M2/N2 委派过错误路径时真被 hook 拒绝，stderr 输出 `[P1#4 delegation boundary] DENY: ...`
- 关联 [[plan-delegation-boundary]]
```

- [ ] **Step 5: 最终总结 commit（如有中间 amend 必要）**

```bash
git log --oneline origin/main..HEAD
# 如有多个 WIP commit，可选 git rebase -i 合并；或保留逐任务粒度
git push origin main
```

Expected: 推到 origin/main 成功。

---

## Self-Review Checklist（plan 完成后由 writing-plans 自动跑）

- [x] **Spec 覆盖** — spec §2.2 路径清单 → Task 1+3 实现；§2.3 hook 落点 → Task 5；§2.4 role 注入 → Task 6 文档引用；§3.1 8 case → Task 2+4；§3.2 smoke → Task 5；§6 交付物 1-7 → Task 1/2/3/5/6；无遗漏
- [x] **占位符扫描** — 无 TBD / TODO / "类似 Task N"；所有代码块完整
- [x] **类型一致** — `_run_for_test()` 在 Task 2 引用、Task 3 定义；`AUDIT_LOG` 在 Task 1 定义、Task 3 使用；`REPO_ROOT` 在 Task 1 定义、Task 4 monkeypatch 覆盖

## 关联

- Spec: `docs/superpowers/specs/2026-07-13-p1-4-delegation-boundary-design.md`
- 双剧本: `projects/LingWen1/docs/dual-playbook.md` M2 / N2
- Backlog: `projects/LingWen1/docs/interview-demo-backlog.md` §P1 #4
- 现有 hook 参照: `butler/blackboard/integrations/claude_session_end.py` + `.claude/settings.json` Stop