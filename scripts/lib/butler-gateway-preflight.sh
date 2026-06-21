# Shared preflight for Butler WeChat gateway (source, do not execute directly).
# Usage: ROOT=... source scripts/lib/butler-gateway-preflight.sh
#        butler_gateway_preflight

# shellcheck source=scripts/lib/butler-source-env.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/butler-source-env.sh"

butler_gateway_preflight() {
  local root="${ROOT:?ROOT not set}"
  local errors=0
  local warns=0

  _bg_ok() { printf '  [ok] %s\n' "$1"; }
  _bg_warn() { printf '  [warn] %s\n' "$1"; warns=$((warns + 1)); }
  _bg_fail() { printf '  [fail] %s\n' "$1"; errors=$((errors + 1)); }
  _bg_compact() {
    printf '%s' "${1:-}" | tr -d '[:space:]'
  }

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
    butler_source_env "$root/.env" || {
      _bg_fail "failed to source $root/.env (check unset vars under set -u, e.g. use \${LD_LIBRARY_PATH:-})"
      errors=$((errors + 1))
    }
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
    _bg_fail 'wechat extras missing: pip install -e ".[gateway]"'
  else
    _bg_ok "wechat Python deps"
  fi

  local _gw_extra_ok=1
  PYTHONPATH="$root" python3 -c "import mcp" 2>/dev/null || _gw_extra_ok=0
  if [[ "$_gw_extra_ok" -eq 0 ]]; then
    _bg_fail 'mcp extra missing: pip install -e ".[gateway]"'
  else
    _bg_ok "mcp Python deps"
  fi
  _gw_extra_ok=1
  PYTHONPATH="$root" python3 -c "import fastembed" 2>/dev/null || _gw_extra_ok=0
  if [[ "$_gw_extra_ok" -eq 0 ]]; then
    _bg_warn "fastembed missing — semantic memory degraded: pip install -e \".[gateway]\""
  else
    _bg_ok "fastembed (embeddings)"
  fi
  _gw_extra_ok=1
  PYTHONPATH="$root" python3 -c "import chromadb" 2>/dev/null || _gw_extra_ok=0
  if [[ "$_gw_extra_ok" -eq 0 ]]; then
    _bg_warn "chromadb missing — vector store degraded: pip install -e \".[gateway]\""
  else
    _bg_ok "chromadb (vectors)"
  fi
  _gw_extra_ok=1
  PYTHONPATH="$root" python3 -c "import trafilatura" 2>/dev/null || _gw_extra_ok=0
  if [[ "$_gw_extra_ok" -eq 0 ]]; then
    _bg_warn "trafilatura missing — web_fetch uses regex fallback: pip install -e \".[gateway]\""
  else
    _bg_ok "trafilatura (web_fetch)"
  fi

  if [[ "${BUTLER_MCP_ENABLED:-0}" =~ ^(1|true|yes|on)$ ]]; then
    if ! command -v npx >/dev/null 2>&1; then
      _bg_warn "BUTLER_MCP_ENABLED=1 but npx not in PATH (Firecrawl MCP needs Node 18+)"
    else
      _bg_ok "npx present (MCP stdio)"
    fi
  fi

  local butler_home="${BUTLER_HOME:-$HOME/.butler}"
  if [[ ! -f "$butler_home/config.yaml" ]]; then
    _bg_warn "~/.butler/config.yaml 缺失 — 可复制 docs/config/config.yaml.example"
  else
    _bg_ok "config.yaml present ($butler_home/config.yaml)"
  fi

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
  dm_policy="${dm_policy,,}"
  local dm_allow_compact
  dm_allow_compact="$(_bg_compact "${WECHAT_ALLOWED_USERS:-}")"
  if [[ "$dm_policy" == "open" ]]; then
    _bg_warn "WECHAT_DM_POLICY=open — set allowlist + WECHAT_ALLOWED_USERS before exposing the Bot"
  elif [[ "$dm_policy" == "allowlist" ]]; then
    if [[ -z "$dm_allow_compact" ]]; then
      _bg_warn "WECHAT_DM_POLICY=allowlist but WECHAT_ALLOWED_USERS is empty"
    else
      _bg_ok "WeChat DM allowlist configured"
    fi
  else
    _bg_ok "WeChat DM policy: $dm_policy"
  fi

  local group_policy="${WECHAT_GROUP_POLICY:-disabled}"
  group_policy="${group_policy,,}"
  local group_allow_compact
  group_allow_compact="$(_bg_compact "${WECHAT_GROUP_ALLOWED_USERS:-}")"
  if [[ "$group_policy" == "open" ]]; then
    _bg_warn "WECHAT_GROUP_POLICY=open — group ingress is fully exposed; prefer disabled or allowlist"
  elif [[ "$group_policy" == "allowlist" ]]; then
    if [[ -z "$group_allow_compact" ]]; then
      _bg_warn "WECHAT_GROUP_POLICY=allowlist but WECHAT_GROUP_ALLOWED_USERS is empty"
    else
      _bg_warn "WECHAT_GROUP_POLICY=allowlist — confirm WECHAT_GROUP_ALLOWED_USERS is minimal"
    fi
  else
    _bg_ok "WeChat group policy: $group_policy"
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

  local owner_compact gateway_allow_compact
  owner_compact="$(_bg_compact "${BUTLER_OWNER_WECHAT_ID:-}")"
  gateway_allow_compact="$(_bg_compact "${BUTLER_GATEWAY_ALLOWLIST:-}")"
  if [[ -z "$owner_compact" && -z "$gateway_allow_compact" && -z "$dm_allow_compact" ]]; then
    _bg_warn "未配置 BUTLER_OWNER_WECHAT_ID / BUTLER_GATEWAY_ALLOWLIST / WECHAT_ALLOWED_USERS — 运行 butler doctor 或补 .env"
  else
    _bg_ok "Gateway owner/allowlist configured"
  fi

  local inbound_media="${BUTLER_WECHAT_INBOUND_MEDIA:-1}"
  if [[ "$inbound_media" =~ ^(1|true|yes|on)$ ]]; then
    if [[ -z "${MINIMAX_API_KEY:-}" && -z "${MINIMAX_CN_API_KEY:-}" ]]; then
      _bg_warn "入站识图需 MINIMAX_API_KEY（BUTLER_WECHAT_INBOUND_MEDIA=1）"
    fi
    local vf="${BUTLER_WECHAT_VISION_FALLBACK:-openai,ocr}"
    if [[ "$vf" == *ocr* ]]; then
      if ! PYTHONPATH="$root" python3 -c "import pytesseract" 2>/dev/null; then
        _bg_warn "VISION_FALLBACK 含 ocr 但未安装 — pip install -e \".[wechat-ocr]\"（及系统 tesseract）"
      else
        _bg_ok "pytesseract available (vision OCR fallback)"
      fi
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
