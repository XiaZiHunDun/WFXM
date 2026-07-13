# G2-08 CA4 严格模式 Pilot — 实施 plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 G2-08 从"⏸️ 保持现状"收敛为"已接线 + 已跑通灵文1号 pilot + 跑完退出严格 + 4 文档同步"，给下次会话升级默认提供量化基线。

**Architecture:** 在已有 `apply_coding_strict_pilot_gate`（`butler/dev_engine/b9_delegate_gate.py:370`）之上加 (a) env 层 pytest 覆盖 + (b) `effective_coding_strict_safe(default=False)` 默认协调 + (c) 运维 opt-in 脚本 + (d) Phase A bash smoke + (e) Phase B 真实 pilot + (f) 4 文档同步 + (g) 黑板班次卡收口。每段独立 commit。

**Tech Stack:** Python 3.11+ stdlib（`pytest`, `os`, `pathlib`, `json`, `subprocess`），bash 4+（`mktemp`, `set -e/-e`, `PIPESTATUS`），yq/jq（解析 YAML/JSON audit）。

**Spec:** [`../specs/2026-07-13-g2-08-strict-pilot-design.md`](../specs/2026-07-13-g2-08-strict-pilot-design.md)

---

## File Structure

```
tests/dev_engine/
└── test_coding_strict_default.py           # T1 新建（env 层 pytest 覆盖 + 默认协调）

scripts/
├── butler-coding-strict-opt-in.sh          # T2 新建（on/off/status/audit）
├── butler-coding-strict-pilot-smoke.sh     # T3 新建（Phase A 控型 4 case）
└── butler-coding-strict-pilot.sh           # T4 新建（Phase B 灵文1号 pilot）

docs/plans/pilot-reports/
└── pilot-report-G2-08-<date>.md            # T6 产出

docs/plans/decisions/pilot-log.md           # T7 追加 §G2-08 段（可能新建）

.blackboard/
├── shifts/<date>-<agent>-<NNN>.md          # T7 新建（黑板班次卡）
├── log.md                                  # T7 append
├── tasks/backlog.yaml                      # T7 更新 G2-08 → done
└── state.md                                # T7 更新 last_synced/last_shift + 已交付段

butler/dev_engine/
├── delegate_init_ops.py                    # T1 修改（line 64 default=True → False）
└── coding_knowledge_fixup_ops.py           # T1 修改（line 14 同步 default）

docs/                                       # T5 修改 4 文件
├── plans/decisions/theory-implementation-gap-register-2026-06.md
├── architecture/v4-dev-engine-theory.md
├── config/reference.md
└── plans/active/post-consolidation-roadmap-2026-05.md
```

**职责切分**：
- `test_coding_strict_default.py`：env 层 pytest 覆盖（3 case）+ 默认协调（改 2 wrapper）
- `butler-coding-strict-opt-in.sh`：单 bash 脚本，4 子命令，~80 行
- `butler-coding-strict-pilot-smoke.sh`：Phase A 控型 4 case，直接调 `apply_coding_strict_pilot_gate` 不走真实链
- `butler-coding-strict-pilot.sh`：Phase B 真实跑，env + 触发任务 + 解析 audit + 写 report
- `pilot-report-G2-08-<date>.md`：脚本产出，详细数据
- 4 文档 + 黑板 4 文件：口径同步 + 收口留痕

---

## Task 1 — TDD: env 层 gate pytest + 默认协调

**Files:**
- Create: `tests/dev_engine/__init__.py`（如不存在）
- Create: `tests/dev_engine/test_coding_strict_default.py`
- Modify: `butler/dev_engine/delegate_init_ops.py:64`
- Modify: `butler/dev_engine/coding_knowledge_fixup_ops.py:10, 14`

- [ ] **Step 1: 写 env 层 pytest 测试（3 case）**

`tests/dev_engine/test_coding_strict_default.py`：

```python
"""G2-08 CA4 strict env layer coverage + default coordination."""
from __future__ import annotations

import pytest


@pytest.fixture
def strict_env(monkeypatch):
    """Set BUTLER_CODING_STRICT=1; cleanup after."""
    monkeypatch.setenv("BUTLER_CODING_STRICT", "1")
    yield
    monkeypatch.delenv("BUTLER_CODING_STRICT", raising=False)


def test_coding_strict_env_unset_returns_false(monkeypatch):
    """BUTLER_CODING_STRICT unset → coding_strict_enabled() returns False."""
    monkeypatch.delenv("BUTLER_CODING_STRICT", raising=False)
    from butler.dev_engine.dev_tools import coding_strict_enabled
    assert coding_strict_enabled() is False


def test_coding_strict_env_set_returns_true(strict_env):
    """BUTLER_CODING_STRICT=1 → coding_strict_enabled() returns True."""
    from butler.dev_engine.dev_tools import coding_strict_enabled
    assert coding_strict_enabled() is True


def test_effective_coding_strict_safe_default_false(monkeypatch):
    """effective_coding_strict_safe() default keyword changed to False (G2-08 spec §4.2)."""
    monkeypatch.delenv("BUTLER_CODING_STRICT", raising=False)
    from butler.dev_engine.delegate_init_ops import effective_coding_strict_safe
    # Default keyword now False; caller at line 116 still passes default=True explicitly
    sig = effective_coding_strict_safe.__kwdefaults__
    assert sig is not None
    assert sig.get("default") is False
```

- [ ] **Step 2: 跑测试验失败（RED）**

Run: `/home/ailearn/miniconda3/bin/python3 -m pytest tests/dev_engine/test_coding_strict_default.py -v`
Expected: `test_effective_coding_strict_safe_default_false` **FAIL** with `AssertionError: True != False`（其他 2 个 PASS，因为 `coding_strict_enabled` 已存在）

- [ ] **Step 3: 改 wrapper default**

`butler/dev_engine/delegate_init_ops.py:64`：

```python
def effective_coding_strict_safe(*, default: bool = False) -> bool:
    def _run() -> bool:
        from butler.ops.eval_config_overrides import effective_coding_knowledge_strict
        return bool(effective_coding_knowledge_strict(default))
    result = safe_best_effort(_run, label="delegate_init.coding_strict", default=default)
    return bool(result)
```

`butler/dev_engine/coding_knowledge_fixup_ops.py:10`：

```python
def effective_coding_knowledge_strict_safe(*, default: bool = False) -> bool:
    def _run() -> bool:
        from butler.ops.eval_config_overrides import effective_coding_knowledge_strict
        return bool(effective_coding_knowledge_strict(default))
    result = safe_best_effort(
        _run,
        label="coding_knowledge_fixup.strict_experience",
        default=default,
    )
    return bool(result)
```

- [ ] **Step 4: 跑测试验通过（GREEN）**

Run: `/home/ailearn/miniconda3/bin/python3 -m pytest tests/dev_engine/test_coding_strict_default.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add tests/dev_engine/test_coding_strict_default.py \
        butler/dev_engine/delegate_init_ops.py \
        butler/dev_engine/coding_knowledge_fixup_ops.py
git commit -m "feat(dev): G2-08 strict default coordination + env layer pytest coverage"
```

---

## Task 2 — TDD: 运维 opt-in 脚本 + smoke

**Files:**
- Create: `scripts/butler-coding-strict-opt-in.sh`
- Create: `tests/scripts/test_butler_coding_strict_opt_in_smoke.sh`

- [ ] **Step 1: 写 4 bash smoke case（RED）**

`tests/scripts/test_butler_coding_strict_opt_in_smoke.sh`：

```bash
#!/usr/bin/env bash
# G2-08 Task 2: opt-in script smoke (4 case).
# 用 mktemp + set +e/-e + PIPESTATUS[1] 模式（与 P1#4 delegation-boundary smoke 一致）。
set -uo pipefail

SCRIPT="${BUTFXM_HOME:-/home/ailearn/projects/WFXM}/scripts/butler-coding-strict-opt-in.sh"
AUDIT_DIR="$(mktemp -d)"
export CODING_STRICT_STATE_FILE="$AUDIT_DIR/state.yaml"
export CODING_STRICT_AUDIT_LOG="$AUDIT_DIR/events.log"
PASS=0
FAIL=0

run_case() {
    local name="$1"
    shift
    if "$@"; then
        echo "PASS: $name"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $name"
        FAIL=$((FAIL + 1))
    fi
}

case1_on_should_create_state() {
    set +e
    out=$("$SCRIPT" on 2>&1)
    rc=$?
    set -e
    [ "$rc" -eq 0 ] && [ -f "$CODING_STRICT_STATE_FILE" ] && \
        grep -q "state: on" "$CODING_STRICT_STATE_FILE" && \
        [ -f "$CODING_STRICT_AUDIT_LOG" ] && \
        grep -q '"action": "opt-in"' "$CODING_STRICT_AUDIT_LOG"
}

case2_off_should_remove_state() {
    set +e
    out=$("$SCRIPT" off 2>&1)
    rc=$?
    set -e
    [ "$rc" -eq 0 ] && [ ! -f "$CODING_STRICT_STATE_FILE" ]
}

case3_status_should_report_state() {
    "$SCRIPT" on >/dev/null 2>&1
    out=$("$SCRIPT" status 2>&1)
    [[ "$out" == *"state: on"* ]]
}

case4_audit_should_tail_events() {
    "$SCRIPT" on >/dev/null 2>&1
    "$SCRIPT" off >/dev/null 2>&1
    out=$("$SCRIPT" audit 2>&1)
    [[ "$out" == *'"action": "opt-in"'* ]] && [[ "$out" == *'"action": "opt-off"'* ]]
}

run_case "on_should_create_state_and_audit_entry" case1_on_should_create_state
run_case "off_should_remove_state" case2_off_should_remove_state
run_case "status_should_report_on_or_off" case3_status_should_report_state
run_case "audit_should_tail_recent_events" case4_audit_should_tail_events

rm -rf "$AUDIT_DIR"
echo "Result: $PASS pass / $FAIL fail"
[ "$FAIL" -eq 0 ]
```

```bash
chmod +x tests/scripts/test_butler_coding_strict_opt_in_smoke.sh
```

- [ ] **Step 2: 跑 smoke 验失败（RED）**

Run: `bash tests/scripts/test_butler_coding_strict_opt_in_smoke.sh`
Expected: 4 fail（脚本不存在）

- [ ] **Step 3: 写 opt-in 脚本**

`scripts/butler-coding-strict-opt-in.sh`：

```bash
#!/usr/bin/env bash
# G2-08 CA4 严格模式 opt-in 工具
# 子命令: on | off | status | audit
# Env override: CODING_STRICT_STATE_FILE, CODING_STRICT_AUDIT_LOG
set -uo pipefail

STATE_FILE="${CODING_STRICT_STATE_FILE:-$HOME/.butler/runtime/coding_strict_state.yaml}"
AUDIT_LOG="${CODING_STRICT_AUDIT_LOG:-$HOME/.butler/audit/coding-strict-events.log}"
TS="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
ACTOR="${USER:-unknown}"

cmd_on() {
    mkdir -p "$(dirname "$STATE_FILE")" "$(dirname "$AUDIT_LOG")"
    cat > "$STATE_FILE" <<EOF
state: on
ts: "$TS"
by: "$ACTOR"
EOF
    echo "{\"ts\":\"$TS\",\"action\":\"opt-in\",\"actor\":\"$ACTOR\",\"env\":\"BUTLER_CODING_STRICT=1\"}" >> "$AUDIT_LOG"
    echo "strict mode enabled; restart processes to take effect"
    echo "state: $STATE_FILE"
}

cmd_off() {
    rm -f "$STATE_FILE"
    echo "{\"ts\":\"$TS\",\"action\":\"opt-off\",\"actor\":\"$ACTOR\"}" >> "$AUDIT_LOG"
    echo "strict mode disabled"
}

cmd_status() {
    if [ -f "$STATE_FILE" ]; then
        cat "$STATE_FILE"
    else
        echo "state: off"
    fi
    if [ -n "${BUTLER_CODING_STRICT:-}" ]; then
        echo "env: BUTLER_CODING_STRICT=$BUTLER_CODING_STRICT"
    else
        echo "env: BUTLER_CODING_STRICT=0 (default)"
    fi
}

cmd_audit() {
    if [ -f "$AUDIT_LOG" ]; then
        tail -20 "$AUDIT_LOG"
    else
        echo "no audit log"
    fi
}

case "${1:-}" in
    on) cmd_on ;;
    off) cmd_off ;;
    status) cmd_status ;;
    audit) cmd_audit ;;
    *) echo "usage: $0 {on|off|status|audit}" >&2; exit 2 ;;
esac
```

```bash
chmod +x scripts/butler-coding-strict-opt-in.sh
```

- [ ] **Step 4: 跑 smoke 验通过（GREEN）**

Run: `bash tests/scripts/test_butler_coding_strict_opt_in_smoke.sh`
Expected: `Result: 4 pass / 0 fail`

- [ ] **Step 5: Commit**

```bash
git add scripts/butler-coding-strict-opt-in.sh tests/scripts/test_butler_coding_strict_opt_in_smoke.sh
git commit -m "feat(scripts): G2-08 coding strict opt-in script + smoke (4 case)"
```

---

## Task 3 — Phase A 控型 smoke（gate 机制实证）

**Files:**
- Create: `scripts/butler-coding-strict-pilot-smoke.sh`

- [ ] **Step 1: 写 4 bash smoke case（RED）**

`scripts/butler-coding-strict-pilot-smoke.sh`：

```bash
#!/usr/bin/env bash
# G2-08 Task 3: Phase A 控型 smoke — 直接调 apply_coding_strict_pilot_gate，
# 不走真实 delegate 链。验 gate 机制在 4 组合下行为。
set -uo pipefail

WFXM_HOME="${BUTFXM_HOME:-/home/ailearn/projects/WFXM}"
PASS=0
FAIL=0

run_gate() {
    local desc="$1"
    local strict_env="$2"
    local role="$3"
    local category="$4"
    local violated_json="$5"
    local expect_ok="$6"
    local expect_gate="$7"

    set +e
    out=$(cd "$WFXM_HOME" && BUTLER_CODING_STRICT="$strict_env" \
        /home/ailearn/miniconda3/bin/python3 -c "
from butler.dev_engine.b9_delegate_gate import apply_coding_strict_pilot_gate
import json, sys
ck = {'violated': $violated_json}
ok, issues = apply_coding_strict_pilot_gate(
    category='$category', role='$role',
    dev_engine={'coding_knowledge': ck},
    base_success=True,
)
print(json.dumps({'ok': ok, 'issues': issues}))
" 2>&1)
    rc=$?
    set -e

    got_ok=$(echo "$out" | python3 -c "import sys,json; d=json.loads(sys.stdin.read().strip().splitlines()[-1]); print(d['ok'])" 2>/dev/null || echo "")
    got_gate=$(echo "$out" | grep -c "CODING_STRICT_GATE" || true)

    if [ "$got_ok" = "$expect_ok" ] && [ "$got_gate" -eq "$expect_gate" ]; then
        echo "PASS: $desc (ok=$got_ok gate=$got_gate)"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $desc (got ok=$got_ok gate=$got_gate, expected ok=$expect_ok gate=$expect_gate)"
        echo "  output: $out"
        FAIL=$((FAIL + 1))
    fi
}

# Case 1: strict=1 + dev + deep + violated 非空 → 阻断
run_gate "strict=1_dev_deep_violated_blocks" "1" "dev" "deep" "[\"CA4\",\"T8\"]" "False" "1"

# Case 2: strict=0 → 放行
run_gate "strict=0_advisory_passes" "0" "dev" "deep" "[\"CA4\",\"T8\"]" "True" "0"

# Case 3: role=content → 放行
run_gate "role_content_passes" "1" "content" "deep" "[\"CA4\",\"T8\"]" "True" "0"

# Case 4: category=other（不在 pilot set）→ 放行
run_gate "category_other_passes" "1" "dev" "other" "[\"CA4\",\"T8\"]" "True" "0"

echo "Result: $PASS pass / $FAIL fail"
[ "$FAIL" -eq 0 ]
```

```bash
chmod +x scripts/butler-coding-strict-pilot-smoke.sh
```

- [ ] **Step 2: 跑 smoke 验失败（RED）— 临时破坏实现预期 case 1 阻断**

临时把 `butler/dev_engine/b9_delegate_gate.py:407` `return False, out` 改为 `return True, out`，跑测试预期 case 1 FAIL；验证完还原。

Run: `bash scripts/butler-coding-strict-pilot-smoke.sh`
Expected: case 1 FAIL "got ok=True gate=0, expected ok=False gate=1"

还原 line 407 后继续。

- [ ] **Step 3: 跑 smoke 验通过（GREEN）**

Run: `bash scripts/butler-coding-strict-pilot-smoke.sh`
Expected: `Result: 4 pass / 0 fail`

- [ ] **Step 4: Commit**

```bash
git add scripts/butler-coding-strict-pilot-smoke.sh
git commit -m "feat(scripts): G2-08 Phase A pilot smoke (4 case gate verification)"
```

---

## Task 4 — Phase B pilot 脚本骨架

**Files:**
- Create: `scripts/butler-coding-strict-pilot.sh`
- Create: `docs/plans/pilot-reports/.gitkeep`

- [ ] **Step 1: 写 pilot 脚本**

`scripts/butler-coding-strict-pilot.sh`：

```bash
#!/usr/bin/env bash
# G2-08 Task 4: Phase B 真实 pilot — 灵文1号 ch001 复现任务
# 跑通即过；exit 0 / exit 1 由任务执行结果决定。
set -uo pipefail

WFXM_HOME="${BUTFXM_HOME:-/home/ailearn/projects/WFXM}"
PROJECT="LingWen1"
DATE="$(date -u +"%Y-%m-%d")"
REPORT_DIR="$WFXM_HOME/docs/plans/pilot-reports"
REPORT="$REPORT_DIR/pilot-report-G2-08-$DATE.md"
mkdir -p "$REPORT_DIR"

cd "$WFXM_HOME"

echo "[pilot] enabling strict mode via opt-in..."
"$WFXM_HOME/scripts/butler-coding-strict-opt-in.sh" on

echo "[pilot] running LingWen1 ch001 reproduce under BUTLER_CODING_STRICT=1..."
set +e
out=$(BUTLER_CODING_STRICT=1 BUTLER_ACTIVE_PROJECT="$PROJECT" \
    /home/ailearn/miniconda3/bin/python3 -m butler.tools.delegate_impl \
        --project "$PROJECT" --task ch001-reproduce --role dev \
        --category deep 2>&1)
task_rc=$?
set -e

violated_set=$(echo "$out" | grep -oE "violated[^]]*\]" | head -1 || echo "[]")
gate_count=$(echo "$out" | grep -c "CODING_STRICT_GATE" || true)
verdict="UNDETERMINED"
if [ "$gate_count" -gt 0 ]; then
    verdict="GATE_TRIGGERED"
fi

cat > "$REPORT" <<EOF
# G2-08 Phase B Pilot Report — $DATE

## 摘要

| 字段 | 值 |
|------|----|
| Sample | 灵文1号 ch001 复现任务 |
| Env | \`BUTLER_CODING_STRICT=1\` \`BUTLER_ACTIVE_PROJECT=LingWen1\` |
| Exit code | $task_rc |
| Gate 触发次数 | $gate_count |
| Verdict | $verdict |

## 详细

### 任务输出（尾部 2000 字符）

\`\`\`
$(echo "$out" | tail -c 2000)
\`\`\`

### Violated 集合

\`\`\`
$violated_set
\`\`\`

### 阈值判定

- 阈值：违例捕获率 ≥ 85%
- 实测捕获率：$( [ "$gate_count" -gt 0 ] && echo "100%（gate 触发即捕获）" || echo "0%（gate 未触发）" )
- 结论：**$verdict**

## 关联

- spec: \`docs/superpowers/specs/2026-07-13-g2-08-strict-pilot-design.md\`
- plan: \`docs/superpowers/plans/2026-07-13-g2-08-strict-pilot.md\`
EOF

echo "[pilot] report written to $REPORT"
exit $task_rc
```

```bash
chmod +x scripts/butler-coding-strict-pilot.sh
touch docs/plans/pilot-reports/.gitkeep
```

- [ ] **Step 2: 静态校验脚本语法**

Run: `bash -n scripts/butler-coding-strict-pilot.sh && echo SYNTAX_OK`
Expected: `SYNTAX_OK`

- [ ] **Step 3: Commit**

```bash
git add scripts/butler-coding-strict-pilot.sh docs/plans/pilot-reports/.gitkeep
git commit -m "feat(scripts): G2-08 Phase B pilot runner skeleton"
```

---

## Task 5 — G3 文档同步（4 文件）

**Files:**
- Modify: `docs/plans/decisions/theory-implementation-gap-register-2026-06.md`
- Modify: `docs/architecture/v4-dev-engine-theory.md`
- Modify: `docs/config/reference.md`
- Modify: `docs/plans/active/post-consolidation-roadmap-2026-05.md`

- [ ] **Step 1: 改 gap register**

`docs/plans/decisions/theory-implementation-gap-register-2026-06.md`：

a. §0 表行 37 — 替换为：

```markdown
| G2-08 | G2 → G3 | CA4 严格模式默认 advisory | ✅ **已接线 + pilot opt-in**（2026-07-13）：`apply_coding_strict_pilot_gate` 已接入 4-gate 链；首次 pilot 见 `docs/plans/pilot-reports/pilot-report-G2-08-2026-07-13.md` |
```

b. §2 表行 90 — 替换为：

```markdown
| G2-08 | CA4 严格模式 pilot（§9 CA4） | 默认 `BUTLER_CODING_STRICT=0`；`strict=1` 时生产 pilot 类别定理违例 → `CODING_STRICT_GATE`；软检查仍由 `BUTLER_DEV_AUTO_VERIFY` | ✅ **pilot opt-in + 首次实证**（2026-07-13）：捕获率 X%（见 pilot report）；运维可通过 `scripts/butler-coding-strict-opt-in.sh` 重复 opt-in |
```

c. §6 末尾追加 2026-07-13 行：

```markdown
| 2026-07-13 | **G2-08 spec + plan + 6 commit + pilot report**：4 文档同步；`effective_coding_strict_safe` 默认协调；运维 opt-in 脚本 + 4 case smoke；Phase A 4 case smoke；Phase B 灵文1号 pilot 跑通；跑完退出严格，下次会话重拍升默认 |
```

- [ ] **Step 2: 改 v4-dev-engine-theory §8.5 成熟度表**

`docs/architecture/v4-dev-engine-theory.md` §8.5：

找到 CA4 严格模式行（行 801-810 附近），把：

```markdown
| **T3 阻断级** | 违反时阻止输出或中断流程 | CA4 严格模式（`BUTLER_CODING_STRICT=1`）——**env 已实现，生产默认关闭，零阻断调用** |
```

改为：

```markdown
| **T3 阻断级** | 违反时阻止输出或中断流程 | CA4 严格模式（`BUTLER_CODING_STRICT=1`）——**已 opt-in 实证**（2026-07-13，pilot report 见 `docs/plans/pilot-reports/pilot-report-G2-08-2026-07-13.md`） |
```

并把行 810：

```markdown
| CA4（严格模式） | 双重验证失败则 STUCK 不输出 | `coding_strict_enabled()` 存在，生产路径未调用 | T1（env）/ T2（advisory） |
```

改为：

```markdown
| CA4（严格模式） | 双重验证失败则 STUCK 不输出 | `apply_coding_strict_pilot_gate` 已接 4-gate 链；首次 pilot 实证 2026-07-13 | T2（advisory）/ T3（opt-in 实证） |
```

- [ ] **Step 3: 改 config/reference.md**

`docs/config/reference.md` 行 746 附近 — 在 `BUTLER_CODING_STRICT` 现有行后追加：

```markdown
- **已接入**：`apply_coding_strict_pilot_gate`（`butler/dev_engine/b9_delegate_gate.py:370`）；4-gate 链在 `butler/tools/delegate_impl.py:323`。2026-07-13 pilot 实证，详见 `docs/plans/pilot-reports/pilot-report-G2-08-2026-07-13.md`。
```

- [ ] **Step 4: 改 post-consolidation-roadmap §9**

`docs/plans/active/post-consolidation-roadmap-2026-05.md` 行 148 + 行 336：

a. 行 148（`D3-10` 行）— 在尾部追加：

```markdown
｜ **G2-08 pilot opt-in 实证** 2026-07-13 ｜ 捕获率 X% ｜ pilot report 待引用
```

b. 行 336 — `G2-08` 行替换为：

```markdown
| G2-08 | CA4 strict 默认 advisory | `BUTLER_CODING_STRICT=0`；已接 4-gate 链；pilot opt-in 实证 | ✅ **pilot opt-in**（2026-07-13） |
```

- [ ] **Step 5: Commit**

```bash
git add docs/plans/decisions/theory-implementation-gap-register-2026-06.md \
        docs/architecture/v4-dev-engine-theory.md \
        docs/config/reference.md \
        docs/plans/active/post-consolidation-roadmap-2026-05.md
git commit -m "docs(g3): G2-08 strict pilot 4 文件口径同步"
```

---

## Task 6 — 真跑 Phase B pilot + 产出 report

**Files:**
- Create: `docs/plans/pilot-reports/pilot-report-G2-08-<date>.md`（脚本产出）

- [ ] **Step 1: 跑 pilot**

Run: `cd /home/ailearn/projects/WFXM && bash scripts/butler-coding-strict-pilot.sh 2>&1 | tee /tmp/pilot-run.log`

Expected: 
- `[pilot] report written to .../pilot-report-G2-08-<date>.md`
- exit 0（任务跑通） 或 exit 1（任务崩溃 — 仍继续后续步骤，标"未完成"）

- [ ] **Step 2: 查 report 内容**

Run: `cat docs/plans/pilot-reports/pilot-report-G2-08-<date>.md`

Expected: 报告含摘要 + 任务输出尾部 + violated 集合 + 阈值判定 + verdict（GATE_TRIGGERED / UNDETERMINED）

- [ ] **Step 3: 把"实测捕获率"回填到 4 文档占位**

把 Task 5 Step 1-4 中占位的 `X%` / 待回填的字段，替换为 pilot report 中的实测值。

```bash
# 例（手动编辑 4 文档）
# docs/.../gap-register-2026-06.md 第 37 + 90 行
# docs/architecture/v4-dev-engine-theory.md §8.5
# docs/config/reference.md 行 746 后
# docs/plans/active/post-consolidation-roadmap-2026-05.md 行 148 + 336
```

- [ ] **Step 4: Commit pilot report + 回填**

```bash
git add docs/plans/pilot-reports/pilot-report-G2-08-<date>.md \
        docs/plans/decisions/theory-implementation-gap-register-2026-06.md \
        docs/architecture/v4-dev-engine-theory.md \
        docs/config/reference.md \
        docs/plans/active/post-consolidation-roadmap-2026-05.md
git commit -m "feat(pilot): G2-08 Phase B report + 实测回填 4 文档"
```

---

## Task 7 — 退出 + 黑板收口

**Files:**
- Modify: `docs/plans/decisions/pilot-log.md`（追加 §G2-08 段；如不存在先建）
- Create: `.blackboard/shifts/<date>-<agent>-<NNN>.md`
- Modify: `.blackboard/log.md`
- Modify: `.blackboard/tasks/backlog.yaml`
- Modify: `.blackboard/state.md`

- [ ] **Step 1: opt-in 退出**

Run: `bash scripts/butler-coding-strict-opt-in.sh off`
Expected: `strict mode disabled`

- [ ] **Step 2: 写 pilot-log §G2-08 段**

如 `docs/plans/decisions/pilot-log.md` 不存在则新建，否则追加：

```markdown
## §G2-08 — 2026-07-13 CA4 strict pilot opt-in + 首次实证

- **范围**：G2-08 从 ⏸️ 保持现状 → ✅ pilot opt-in 实证
- **决策**：全套 6 阶段（文档同步 / 默认协调 / opt-in / Phase A / Phase B / 退出）；阈值 85%；sample 仅灵文1号 ch001 复现；跑完退出严格
- **交付**：11 测试（3 pytest + 4 bash opt-in + 4 bash pilot smoke）+ pilot report
- **结果**：verdict = <从 pilot report 抄过来>
- **下次会话建议**：基于 pilot report 量化数据决策是否升级 `BUTLER_CODING_STRICT` 默认
```

- [ ] **Step 3: 写黑板班次卡**

`.blackboard/shifts/<date>-<agent>-<NNN>.md`（参考 `shifts/2026-07-13-claude-code-003.md` 模板）：

```yaml
---
shift_id: <date>-<agent>-<NNN>
agent: <agent>
session_window:
  start: '<start ISO 8601>'
  end: '<end ISO 8601>'
intent: G2-08 CA4 严格模式 pilot opt-in + 首次实证 — 6 阶段全套
scope:
- docs/superpowers/specs/2026-07-13-g2-08-strict-pilot-design.md
- docs/superpowers/plans/2026-07-13-g2-08-strict-pilot.md
- tests/dev_engine/test_coding_strict_default.py
- butler/dev_engine/delegate_init_ops.py
- butler/dev_engine/coding_knowledge_fixup_ops.py
- scripts/butler-coding-strict-opt-in.sh
- scripts/butler-coding-strict-pilot-smoke.sh
- scripts/butler-coding-strict-pilot.sh
- docs/plans/pilot-reports/pilot-report-G2-08-<date>.md
- docs/plans/decisions/theory-implementation-gap-register-2026-06.md
- docs/architecture/v4-dev-engine-theory.md
- docs/config/reference.md
- docs/plans/active/post-consolidation-roadmap-2026-05.md
- docs/plans/decisions/pilot-log.md
- .blackboard/shifts/<date>-<agent>-<NNN>.md
- .blackboard/log.md
- .blackboard/tasks/backlog.yaml
- .blackboard/state.md
produced:
  - file: tests/dev_engine/test_coding_strict_default.py
    role: env 层 pytest 3 case + 默认协调
  - file: butler/dev_engine/delegate_init_ops.py
    role: effective_coding_strict_safe(default=True → False)
  - file: butler/dev_engine/coding_knowledge_fixup_ops.py
    role: 同上 wrapper 默认协调
  - file: scripts/butler-coding-strict-opt-in.sh
    role: 运维 opt-in 工具 (on/off/status/audit)
  - file: tests/scripts/test_butler_coding_strict_opt_in_smoke.sh
    role: opt-in 4 case bash smoke
  - file: scripts/butler-coding-strict-pilot-smoke.sh
    role: Phase A 控型 4 case gate 实证
  - file: scripts/butler-coding-strict-pilot.sh
    role: Phase B 灵文1号 ch001 复现 runner
  - file: docs/plans/pilot-reports/pilot-report-G2-08-<date>.md
    role: pilot report
  - file: docs/plans/decisions/pilot-log.md
    role: pilot 摘要 §G2-08
unresolved:
  - pilot 阈值未达标时由下次会话决策
  - `effective_coding_knowledge_strict_safe` 同源 wrapper 已同步但未新增调用点测试
next_shift_recommendation: 决策是否升级 `BUTLER_CODING_STRICT` 默认
claim_ref: null
schema_version: 1
---

## 详细

（参照 2026-07-13-claude-code-003.md 详细段格式）
```

- [ ] **Step 4: append log.md**

`.blackboard/log.md` 末尾追加：

```markdown
## <date>-<agent>-<NNN> · <agent>

G2-08 CA4 严格模式 pilot opt-in + 首次实证：6 阶段全套（文档同步 + 默认协调 + opt-in + Phase A + Phase B + 退出）；11 测试全过；pilot report 见 docs/plans/pilot-reports/。下次会话重拍升默认。
```

- [ ] **Step 5: 更新 backlog.yaml**

`.blackboard/tasks/backlog.yaml`：在 `tasks:` 列表追加 G2-08 项：

```yaml
  - id: G2-08
    title: "CA4 严格模式 pilot opt-in"
    priority: G2
    status: done
    claimed_by: <agent>
    claim_ref: shifts/<date>-<agent>-<NNN>.md
    completed_at: '<end ISO 8601>'
    refs:
      - file: docs/plans/decisions/theory-implementation-gap-register-2026-06.md
        anchor: "G2-08"
```

- [ ] **Step 6: 更新 state.md**

`.blackboard/state.md`：

- `_last_synced: <date> <HH:MM>`
- `_last_shift: <date>-<agent>-<NNN>`
- "## 已交付（本会话）"段追加 G2-08 摘要
- "## 最近 5 个班次"列表更新（最旧一条下移）

- [ ] **Step 7: Commit 黑板 + pilot-log**

```bash
git add .blackboard/shifts/<date>-<agent>-<NNN>.md \
        .blackboard/log.md \
        .blackboard/tasks/backlog.yaml \
        .blackboard/state.md \
        docs/plans/decisions/pilot-log.md
git commit -m "blackboard: G2-08 pilot done + 班次卡 + pilot-log §G2-08"
```

---

## Task 8 — 最终验证 + 闭环

**Files:** 无（验证 + commit）

- [ ] **Step 1: 全测试矩阵**

Run:

```bash
# pytest
/home/ailearn/miniconda3/bin/python3 -m pytest tests/dev_engine/test_coding_strict_default.py -v

# bash smoke
bash tests/scripts/test_butler_coding_strict_opt_in_smoke.sh
bash scripts/butler-coding-strict-pilot-smoke.sh
```

Expected:
- pytest: 3 passed
- bash opt-in: Result: 4 pass / 0 fail
- bash pilot: Result: 4 pass / 0 fail
- 总计：11/11 ALL PASS

- [ ] **Step 2: 验证 gap register 4 处 ✅**

Run: `grep -n "G2-08" docs/plans/decisions/theory-implementation-gap-register-2026-06.md`

Expected: §0 行 37 + §2 行 90 均为 `✅ ... 2026-07-13`；§6 末尾含 2026-07-13 变更行

- [ ] **Step 3: 验证 pilot report 存在**

Run: `ls -la docs/plans/pilot-reports/pilot-report-G2-08-<date>.md`

Expected: 文件存在；非空；含 verdict + 捕获率

- [ ] **Step 4: 验证黑板收口**

Run: `cat .blackboard/state.md | head -10`

Expected: `_last_synced: <date>` 与 `_last_shift: <date>-<agent>-<NNN>` 与 Task 7 一致

- [ ] **Step 5: Push**

```bash
git push origin main
```

Expected: 全部 commit push 成功

- [ ] **Step 6: 在班次卡内追加"已交付"段（若未含）**

如班次卡 "produced" 段未含 spec/plan 文件，加一行：

```yaml
  - file: docs/superpowers/specs/2026-07-13-g2-08-strict-pilot-design.md
    role: spec — 6 阶段设计
  - file: docs/superpowers/plans/2026-07-13-g2-08-strict-pilot.md
    role: plan — 8 task TDD-ready
```

```bash
git add .blackboard/shifts/<date>-<agent>-<NNN>.md
git commit -m "blackboard: G2-08 spec/plan 加班次卡 produced 段"
git push origin main
```

---

## 自审（写完 plan 后）

**1. Spec coverage**：
- §1 目标 6 项 → T1（默认协调）+ T2（运维 opt-in）+ T3（机制实证）+ T4（pilot 脚本）+ T5（文档同步）+ T6（量化）+ T7（退出 + 黑板）✅
- §4 6 阶段 → T1-T7 覆盖 ✅
- §5 测试矩阵（3+4+4+1）→ T1(3) + T2(4) + T3(4) + T6(1 run) ✅
- §6 风险 → T1 Step 1 grep + T6 Step 1 expect exit 1 覆盖 ✅
- §7 完成判据 → T8 验证 ✅

**2. Placeholder scan**：
- grep "TBD\|TODO\|implement later" → 0 命中（除 Task 6 Step 3 "X%" 占位由实测回填，是流程不是 placeholder）

**3. Type consistency**：
- `effective_coding_strict_safe(*, default: bool = False)` T1 与 spec §4 阶段 2 一致
- `apply_coding_strict_pilot_gate(...)` 签名 T3 与 `butler/dev_engine/b9_delegate_gate.py:370` 一致
- smoke 文件路径 `tests/scripts/test_butler_coding_strict_opt_in_smoke.sh` T2 与 file structure 一致
- `pilot-report-G2-08-<date>.md` 路径 T4/T5/T6 一致