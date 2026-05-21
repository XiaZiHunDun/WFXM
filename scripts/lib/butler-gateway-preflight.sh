# Shared preflight for Butler WeChat gateway (source, do not execute directly).
# Usage: ROOT=... source scripts/lib/butler-gateway-preflight.sh
#        butler_gateway_preflight

butler_gateway_preflight() {
  local root="${ROOT:?ROOT not set}"
  local errors=0
  local warns=0

  _bg_ok() { printf '  [ok] %s\n' "$1"; }
  _bg_warn() { printf '  [warn] %s\n' "$1"; warns=$((warns + 1)); }
  _bg_fail() { printf '  [fail] %s\n' "$1"; errors=$((errors + 1)); }

  echo "Butler gateway preflight ($root)"

  if ! command -v python3 >/dev/null 2>&1; then
    _bg_fail "python3 not in PATH"
  else
    _bg_ok "python3: $(command -v python3)"
  fi

  if [[ ! -f "$root/.env" ]]; then
    _bg_fail "missing $root/.env (cp .env.example .env)"
  else
    _bg_ok ".env present"
    # shellcheck disable=SC1090
    set -a && source "$root/.env" && set +a
    if [[ -z "${MINIMAX_API_KEY:-}" && -z "${MINIMAX_CN_API_KEY:-}" ]]; then
      _bg_warn "MINIMAX_API_KEY not set in .env (gateway LLM may fail)"
    else
      _bg_ok "MiniMax API key configured"
    fi
  fi

  if ! PYTHONPATH="$root" python3 -c "
from butler.gateway.platforms.wechat import check_wechat_requirements
import sys
sys.exit(0 if check_wechat_requirements() else 1)
" 2>/dev/null; then
    _bg_fail 'wechat extras missing: pip install -e ".[wechat]"'
  else
    _bg_ok "wechat Python deps"
  fi

  local butler_home="${BUTLER_HOME:-$HOME/.butler}"
  local accounts_dir="$butler_home/wechat/accounts"
  if [[ ! -d "$accounts_dir" ]] || [[ -z "$(find "$accounts_dir" -maxdepth 1 -name '*.json' 2>/dev/null | head -1)" ]]; then
    _bg_warn "no WeChat account in $accounts_dir — run: butler wechat-setup"
  else
    local n
    n="$(find "$accounts_dir" -maxdepth 1 -name '*.json' 2>/dev/null | wc -l)"
    _bg_ok "WeChat accounts: $n file(s) under $accounts_dir"
  fi

  if command -v loginctl >/dev/null 2>&1; then
    local linger
    linger="$(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null || echo no)"
    if [[ "$linger" != "yes" ]]; then
      _bg_warn "linger=no — user systemd stops at logout; run: sudo loginctl enable-linger $(id -un)"
    else
      _bg_ok "linger=yes (survives reboot without login)"
    fi
  fi

  if systemctl --user cat hermes-gateway.service >/dev/null 2>&1; then
    if systemctl --user is-active hermes-gateway.service >/dev/null 2>&1; then
      _bg_warn "hermes-gateway.service is active — stop/disable to avoid Bot conflicts"
    else
      _bg_ok "hermes-gateway.service not running"
    fi
  fi

  mkdir -p "$root/logs"
  _bg_ok "logs dir: $root/logs"

  local dm_policy="${WECHAT_DM_POLICY:-open}"
  if [[ "$dm_policy" == "open" ]]; then
    _bg_warn "WECHAT_DM_POLICY=open — set allowlist + WECHAT_ALLOWED_USERS before exposing the Bot"
  elif [[ "$dm_policy" == "allowlist" ]]; then
    if [[ -z "${WECHAT_ALLOWED_USERS:-}" ]]; then
      _bg_warn "WECHAT_DM_POLICY=allowlist but WECHAT_ALLOWED_USERS is empty"
    else
      _bg_ok "WeChat DM allowlist configured"
    fi
  else
    _bg_ok "WeChat DM policy: $dm_policy"
  fi

  if [[ -z "${BUTLER_TOOL_SAFE_ROOT:-}" ]]; then
    _bg_warn "BUTLER_TOOL_SAFE_ROOT unset — tools may fall back to process cwd without a project"
  else
    _bg_ok "BUTLER_TOOL_SAFE_ROOT set"
  fi

  if [[ -z "${BUTLER_DEFAULT_PROJECT:-}" ]]; then
    _bg_warn "BUTLER_DEFAULT_PROJECT unset — new chats need /切换 before tool use"
  else
    _bg_ok "BUTLER_DEFAULT_PROJECT=${BUTLER_DEFAULT_PROJECT}"
  fi

  local inbound_media="${BUTLER_WECHAT_INBOUND_MEDIA:-1}"
  if [[ "$inbound_media" =~ ^(1|true|yes|on)$ ]]; then
    if [[ -z "${MINIMAX_API_KEY:-}" && -z "${MINIMAX_CN_API_KEY:-}" ]]; then
      _bg_warn "入站识图需 MINIMAX_API_KEY（BUTLER_WECHAT_INBOUND_MEDIA=1）"
    fi
    if [[ "${BUTLER_WECHAT_STT_PROVIDER:-local}" == "local" ]]; then
      if ! command -v ffmpeg >/dev/null 2>&1; then
        _bg_warn "无 ffmpeg — 纯 .silk 语音无法转写（iLink 自带转写仍可用）"
      else
        _bg_ok "ffmpeg present (silk STT)"
      fi
    fi
  fi

  if [[ "$errors" -gt 0 ]]; then
    echo "Preflight: $errors error(s), $warns warning(s)"
    return 1
  fi
  echo "Preflight: ok ($warns warning(s))"
  return 0
}
