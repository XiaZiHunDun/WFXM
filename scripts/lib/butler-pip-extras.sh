# Shared pip extra profile for Butler deploy scripts (source only).
# Usage: source scripts/lib/butler-pip-extras.sh
#        butler_pip_install_extras "$ROOT"

butler_resolve_pip_profile() {
  local profile="${BUTLER_DEPLOY_PROFILE:-}"
  if [[ -z "$profile" ]]; then
    if systemctl --user is-active butler-gateway.service >/dev/null 2>&1; then
      profile=gateway
    else
      profile=dev
    fi
  fi
  printf '%s' "$profile"
}

butler_pip_extra_spec() {
  local profile
  profile="$(butler_resolve_pip_profile)"
  case "$profile" in
    gateway) printf '%s' "gateway" ;;
    dev) printf '%s' "gateway,dev" ;;
    all) printf '%s' "all" ;;
    *) printf '%s' "$profile" ;;
  esac
}

butler_pip_install_extras() {
  local root="${1:?root required}"
  local spec
  spec="$(butler_pip_extra_spec)"
  pip install -e "$root[$spec]" --quiet 2>/dev/null
}
