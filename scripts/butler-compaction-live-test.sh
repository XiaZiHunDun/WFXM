#!/usr/bin/env bash
# Temporarily lower compaction threshold for WeChat live testing (restore after).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"
BACKUP="$ROOT/.env.compaction-live-test.bak"
MARK_BEGIN="# >>> compaction-live-test (auto) >>>"
MARK_END="# <<< compaction-live-test (auto) <<<"
RESERVE_TEST="${BUTLER_COMPACTION_LIVE_RESERVE:-5000}"
RESERVE_DEFAULT=13000

_usage() {
  cat <<EOF
Usage: $(basename "$0") <command>

Commands:
  enable     Set BUTLER_CONTEXT_COMPACT_RESERVE=$RESERVE_TEST in .env and restart gateway
  disable    Remove test override (restore default $RESERVE_DEFAULT) and restart gateway
  status     Show current compact reserve in .env and running gateway hint
  checklist  Print WeChat live test steps (no changes)

Test reserve override: BUTLER_COMPACTION_LIVE_RESERVE (default $RESERVE_TEST)

See: docs/guides/context-compaction-smoke-checklist.md
EOF
}

_ensure_env() {
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "missing $ENV_FILE — cp .env.example .env first" >&2
    exit 1
  fi
}

_has_block() {
  grep -qF "$MARK_BEGIN" "$ENV_FILE" 2>/dev/null
}

_remove_block() {
  local tmp
  tmp="$(mktemp)"
  awk -v begin="$MARK_BEGIN" -v end="$MARK_END" '
    $0 == begin { skip=1; next }
    $0 == end { skip=0; next }
    !skip { print }
  ' "$ENV_FILE" >"$tmp"
  mv "$tmp" "$ENV_FILE"
}

_append_block() {
  {
    echo ""
    echo "$MARK_BEGIN"
    echo "BUTLER_CONTEXT_COMPACT_RESERVE=$RESERVE_TEST"
    echo "$MARK_END"
  } >>"$ENV_FILE"
}

_cmd_enable() {
  _ensure_env
  if _has_block; then
    _remove_block
  else
    cp -a "$ENV_FILE" "$BACKUP"
    echo "backup: $BACKUP"
  fi
  _append_block
  echo "enabled BUTLER_CONTEXT_COMPACT_RESERVE=$RESERVE_TEST"
  bash "$ROOT/scripts/butler-gateway-ops.sh" restart
  echo ""
  echo "Next: send /new on WeChat, then follow:"
  _cmd_checklist
}

_cmd_disable() {
  _ensure_env
  if _has_block; then
    _remove_block
    echo "removed compaction-live-test block from .env"
  else
    echo "no compaction-live-test block in .env (nothing to remove)"
  fi
  if [[ -f "$BACKUP" ]]; then
    echo "backup kept at $BACKUP (delete manually if unneeded)"
  fi
  bash "$ROOT/scripts/butler-gateway-ops.sh" restart
  echo "restored to default BUTLER_CONTEXT_COMPACT_RESERVE=$RESERVE_DEFAULT (unless set elsewhere in .env)"
}

_cmd_status() {
  _ensure_env
  echo "=== compaction live test status ==="
  if _has_block; then
    echo "mode: ENABLED (marker block present)"
    grep -A1 "$MARK_BEGIN" "$ENV_FILE" | tail -1 || true
  else
    echo "mode: normal (no marker block)"
    if grep -q '^BUTLER_CONTEXT_COMPACT_RESERVE=' "$ENV_FILE" 2>/dev/null; then
      grep '^BUTLER_CONTEXT_COMPACT_RESERVE=' "$ENV_FILE"
    else
      echo "BUTLER_CONTEXT_COMPACT_RESERVE=(unset in .env, default $RESERVE_DEFAULT)"
    fi
  fi
  echo ""
  bash "$ROOT/scripts/butler-gateway-ops.sh" status 2>&1 | head -12 || true
}

_cmd_checklist() {
  cat <<'EOF'
WeChat live compaction test:
  1. /new
  2. 请连续 read_file 读取 docs 下 5 个文件并各用一句话总结
  3. 再搜一下项目里所有 test_ 开头的文件
  4. 把我们刚才读过哪些文件列个清单  （应只列 read_file 的 5 条路径，不含搜文件）
  5. /诊断  （压缩需 ~37k tokens 才触发；15k 时仍为「压缩: 否」属正常）
  6. 若未压缩：请 read_file 读完 docs 剩下 4 个文件各 3 句总结，并复述前 5 个各 3 句 → 再 /诊断
  7. 测完运行: bash scripts/butler-compaction-live-test.sh disable
EOF
}

cmd="${1:-}"
case "$cmd" in
  enable) _cmd_enable ;;
  disable) _cmd_disable ;;
  status) _cmd_status ;;
  checklist) _cmd_checklist ;;
  -h|--help|help|"") _usage ;;
  *)
    echo "unknown command: $cmd" >&2
    _usage
    exit 1
    ;;
esac
