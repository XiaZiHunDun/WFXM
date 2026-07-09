#!/usr/bin/env bash
# Dev live flywheel checklist — gateway env, project.yaml VERIFY commands, optional probe.
#
# Rhythm (ops):
#   Monthly: bash scripts/butler-dev-flywheel-monthly.sh
#            + WeChat manual: docs/guides/dev-flywheel-monthly.md
#   Weekly:  bash scripts/butler-prod-delta-observe.sh
#            bash scripts/butler-lingwen-live-capture-checklist.sh
#
# Usage:
#   bash scripts/butler-dev-live-flywheel-checklist.sh           # read-only env + yaml
#   bash scripts/butler-dev-live-flywheel-checklist.sh --probe   # + verify_lint/test on pilots
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

PROBE=0
for arg in "$@"; do
  case "$arg" in
    --probe) PROBE=1 ;;
    -h|--help)
      sed -n '1,12p' "$0"
      exit 0
      ;;
  esac
done

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck source=scripts/lib/butler-source-env.sh
  source "$ROOT/scripts/lib/butler-source-env.sh"
  butler_source_env "$ROOT/.env" 2>/dev/null || true
fi

export BUTLER_DEV_FLYWHEEL_PROBE="$PROBE"
exec python3 - <<'PY'
import os
import sys
from pathlib import Path

from butler.dev_engine.dev_tools import dev_engine_enabled
from butler.env_parse import env_truthy
from butler.project.manager import get_project_manager

ROOT = Path(os.environ.get("PYTHONPATH", ".")).resolve()
PROBE = os.environ.get("BUTLER_DEV_FLYWHEEL_PROBE", "0").strip() in ("1", "true", "yes", "on")
warn = 0
fail = 0


def _truthy(name: str) -> bool:
    return env_truthy(name)


def check(name: str, ok: bool, *, action: str = "", hard: bool = False) -> None:
    global warn, fail
    tag = "PASS" if ok else ("FAIL" if hard else "WARN")
    line = f"  [{tag}] {name}"
    if action and not ok:
        line += f" — ACTION: {action}"
    print(line)
    if ok:
        return
    if hard:
        fail += 1
    else:
        warn += 1


print("=== Dev live flywheel checklist ===")
print()

de = dev_engine_enabled()
term = _truthy("BUTLER_ENABLE_TERMINAL")
profile = (os.getenv("BUTLER_TERMINAL_PROFILE") or "").strip() or "(unset)"
env_profile = (os.getenv("BUTLER_ENV_PROFILE") or "").strip() or "(unset)"
sandbox = _truthy("BUTLER_TERMINAL_SANDBOX")
capture = (os.getenv("BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES") or "").strip() or "(unset)"
bwrap = Path("/usr/bin/bwrap").is_file() or Path("/bin/bwrap").is_file()

print("1. Gateway env (production dev delegate)")
check("BUTLER_DEV_ENGINE on", de, action="set BUTLER_DEV_ENGINE=1 in .env")
check("BUTLER_ENABLE_TERMINAL on", term, action="set BUTLER_ENABLE_TERMINAL=1 in .env")
check(
    "BUTLER_TERMINAL_PROFILE=dev",
    profile == "dev",
    action="set BUTLER_TERMINAL_PROFILE=dev for pytest/git in terminal whitelist",
)
check(
    "BUTLER_ENV_PROFILE (dev-remote|dev-gateway|dev-local)",
    env_profile in ("dev-remote", "dev-gateway", "dev-local"),
    action="apply: python3 scripts/apply-butler-env-profile.py dev-remote",
)
if sandbox:
    check(
        "bubblewrap (bwrap) for terminal sandbox",
        bwrap,
        action="install bubblewrap (apt install bubblewrap)",
        hard=True,
    )
check(
    "BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES",
    capture in ("1", "true", "yes", "on", "all"),
    action="set BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES=1 (or all) for live failure audit",
)
print(
    f"   values: dev_engine={de} terminal={term} term_profile={profile}"
    f" env_profile={env_profile} sandbox={sandbox} bwrap={bwrap} capture={capture}"
)
print()

print("2. project.yaml dev commands (VERIFY + /测试)")
pm = get_project_manager()
for name in ("灵文1号", "普通试点项目"):
    proj = pm.get_project(name)
    ws = getattr(proj, "workspace", None) if proj else None
    dev = dict(getattr(proj, "dev", None) or {}) if proj else {}
    lint = str(dev.get("lint_command") or "").strip()
    test = str(dev.get("test_command") or "").strip()
    build = str(dev.get("build_command") or "").strip()
    ok = bool(ws and Path(ws).is_dir() and lint and test)
    check(
        f"{name} dev lint+test",
        ok,
        action=f"fix workspace or dev.*_command in {ws}/project.yaml" if not ok else "",
        hard=not ws or not Path(ws).is_dir(),
    )
    if ws:
        print(f"   {name}: ws={ws}")
        print(f"     lint={lint or '(missing)'}")
        print(f"     test={test or '(missing)'}")
        if build:
            print(f"     build={build}")
print()

if PROBE:
    from butler.dev_engine.dev_state import VerifyStatus
    from butler.dev_engine.verify import verify_lint, verify_test

    print("3. VERIFY probe (--probe)")
    for name in ("普通试点项目", "灵文1号"):
        proj = pm.get_project(name)
        ws = getattr(proj, "workspace", None) if proj else None
        if not ws or not Path(ws).is_dir():
            check(f"{name} workspace", False, hard=True)
            continue
        ws_path = Path(ws)
        lint_r = verify_lint(ws_path, timeout=120)
        test_r = verify_test(ws_path, timeout=300)
        check(
            f"{name} verify_lint",
            lint_r.status in (VerifyStatus.PASS, VerifyStatus.SKIP),
            action=f"lint failed: {lint_r.command} exit={lint_r.exit_code}",
            hard=lint_r.status == VerifyStatus.FAIL,
        )
        check(
            f"{name} verify_test",
            test_r.status in (VerifyStatus.PASS, VerifyStatus.SKIP),
            action=f"test failed: {test_r.command} exit={test_r.exit_code}",
            hard=test_r.status == VerifyStatus.FAIL,
        )
        print(f"   {name}: lint={lint_r.status.value} test={test_r.status.value}")
    print()
else:
    print("3. VERIFY probe skipped (use --probe to run verify_lint/test on pilots)")
    print()

print("=== Ops rhythm ===")
print("  Monthly: bash scripts/butler-dev-flywheel-monthly.sh")
print("           docs/guides/dev-flywheel-monthly.md (WeChat manual)")
print("  Weekly:  bash scripts/butler-prod-delta-observe.sh")
print("           bash scripts/butler-lingwen-live-capture-checklist.sh")
print("  Daily:   bash scripts/butler-ops-followup-check.sh  # includes dev sim --quick
  Weekly:  bash scripts/butler-g1-04-weekly-checkin.sh --log")
print()
print(f"summary: fail={fail} warn={warn} probe={'on' if PROBE else 'off'}")
if fail:
    sys.exit(1)
if warn:
    sys.exit(2)
print("OK: dev flywheel checklist")
PY
