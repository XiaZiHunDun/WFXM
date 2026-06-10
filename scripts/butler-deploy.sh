#!/usr/bin/env bash
# Butler v4 — 统一部署入口
# 自动检测环境类型（全新 / 已有），支持 init/update/status/rollback/langfuse-only 五种模式。
#
# Usage:
#   bash scripts/butler-deploy.sh init        # 全新环境部署
#   bash scripts/butler-deploy.sh update      # 增量更新（git pull + deps + restart + verify）
#   bash scripts/butler-deploy.sh status      # 全栈状态检查
#   bash scripts/butler-deploy.sh rollback    # 回滚到上一版本
#   bash scripts/butler-deploy.sh langfuse    # 仅管理 LangFuse 栈
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUTLER_HOME="${BUTLER_HOME:-$HOME/.butler}"
COMPOSE_DIR="$ROOT/deploy/langfuse"
UNIT=butler-gateway.service
LOG="$ROOT/logs/butler-gateway.log"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

_info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
_ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
_err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

_usage() {
  cat <<EOF
Butler v4 统一部署工具

Usage: $(basename "$0") <command> [options]

Commands:
  init     [--systemd] [--skip-langfuse]   全新环境部署（venv + deps + config + dirs + LangFuse）
  update   [--skip-langfuse] [--skip-reindex] [--skip-benchmark]   增量更新（git pull + deps + restart + LangFuse + 基准回归）
  status                                    全栈状态（Butler + LangFuse + systemd）
  rollback [--steps N]                      回滚到上一版本（git + deps + restart）
  langfuse [up|down|status|logs|pull]       仅管理 LangFuse 栈

Examples:
  bash scripts/butler-deploy.sh init
  bash scripts/butler-deploy.sh update
  bash scripts/butler-deploy.sh status
  bash scripts/butler-deploy.sh rollback
  bash scripts/butler-deploy.sh langfuse up
  bash scripts/butler-deploy.sh langfuse pull   # 拉取新镜像并重启
EOF
}

# ─── LangFuse 管理 ───

_langfuse_is_running() {
  if command -v docker &>/dev/null; then
    local running
    running=$(docker compose -f "$COMPOSE_DIR/docker-compose.yml" ps --status running -q 2>/dev/null | wc -l)
    [[ "$running" -gt 0 ]]
  else
    return 1
  fi
}

_langfuse_health() {
  curl -sf http://localhost:3000/api/public/health > /dev/null 2>&1
}

_langfuse_up() {
  _info "启动 LangFuse 栈..."
  if ! command -v docker &>/dev/null; then
    _warn "未安装 Docker，跳过 LangFuse"
    return 1
  fi
  bash "$ROOT/scripts/langfuse-setup.sh"
}

_langfuse_down() {
  _info "停止 LangFuse 栈..."
  bash "$ROOT/scripts/langfuse-setup.sh" --down
}

_langfuse_pull() {
  _info "拉取 LangFuse 最新镜像并重启..."
  cd "$COMPOSE_DIR"
  docker compose pull
  docker compose up -d
  _ok "LangFuse 镜像已更新"
}

_observability_status() {
  echo "  === 观测演化 (L7) ==="
  local env_file="$ROOT/.env"
  if [[ -f "$env_file" ]]; then
    # shellcheck disable=SC1090
    set -a; source "$env_file" 2>/dev/null || true; set +a
  fi
  local lf="${BUTLER_LANGFUSE_ENABLED:-0}"
  local emb="${BUTLER_EMBEDDING_PROVIDER:-local}"
  local sem="${BUTLER_SEMANTIC_MEMORY:-0}"
  if [[ "$lf" == "1" || "$lf" == "true" ]]; then
    _ok "BUTLER_LANGFUSE_ENABLED=1"
  else
    _warn "BUTLER_LANGFUSE_ENABLED 未启用"
  fi
  echo "  Embedding: provider=$emb semantic=$sem"
  if PYTHONPATH="$ROOT" python3 -c "
from butler.ops.embedding_health import check_embedding_recall
r = check_embedding_recall(min_recall=0.5)
print(f'  Recall@3: {r.recall_at_3:.0%} ({r.hits}/{r.total}) — {r.message}')
import sys; sys.exit(0 if not r.degraded else 1)
" 2>/dev/null; then
    :
  else
    _warn "Embedder 可能已降级到 HashingEmbedder"
  fi
  echo ""
}

_langfuse_status() {
  if ! command -v docker &>/dev/null; then
    echo "  Docker: 未安装"
    return
  fi
  echo "  === LangFuse Stack ==="
  if _langfuse_is_running; then
    _ok "LangFuse 容器运行中"
    docker compose -f "$COMPOSE_DIR/docker-compose.yml" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || true
    if _langfuse_health; then
      _ok "LangFuse API 健康"
    else
      _warn "LangFuse API 未响应（可能正在启动）"
    fi
  else
    echo "  LangFuse: 未运行"
    echo "  启动: bash scripts/butler-deploy.sh langfuse up"
  fi
}

_langfuse_logs() {
  cd "$COMPOSE_DIR"
  docker compose logs -f --tail 50
}

# ─── Butler 状态 ───

_butler_status() {
  echo "  === Butler 进程 ==="
  local active
  active=$(systemctl --user is-active "$UNIT" 2>/dev/null || echo "inactive")
  if [[ "$active" == "active" ]]; then
    _ok "Gateway: active"
    systemctl --user --no-pager status "$UNIT" 2>&1 | head -8 || true
  else
    echo "  Gateway: $active"
  fi
  echo ""
  pgrep -af 'butler.main' 2>/dev/null || echo "  (无 Butler 进程)"
  echo ""

  echo "  === 版本信息 ==="
  local git_sha
  git_sha=$(cd "$ROOT" && git rev-parse --short HEAD 2>/dev/null || echo "unknown")
  echo "  Git HEAD: $git_sha"
  PYTHONPATH="$ROOT" python3 -c "
from butler import get_build_identity
info = get_build_identity()
print(f\"  Butler: v{info['version']} (commit={info['git_sha']}, python={info['python']})\")
" 2>/dev/null || echo "  Butler: (import failed)"
  echo ""

  echo "  === 数据目录 ==="
  if [[ -d "$BUTLER_HOME" ]]; then
    echo "  $BUTLER_HOME"
    du -sh "$BUTLER_HOME" 2>/dev/null | awk '{print "  总大小: " $1}'
  else
    echo "  $BUTLER_HOME: 不存在"
  fi
  echo ""

  echo "  === Python 环境 ==="
  echo "  venv: ${VIRTUAL_ENV:-none}"
  python3 --version 2>/dev/null || echo "  python3: not found"
  echo ""
}

# ─── Init（全新部署） ───

_cmd_init() {
  local install_systemd=0
  local skip_langfuse=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --systemd) install_systemd=1 ;;
      --skip-langfuse) skip_langfuse=1 ;;
      *) _err "Unknown init option: $1"; _usage; exit 1 ;;
    esac
    shift
  done

  echo ""
  echo "╔══════════════════════════════════════╗"
  echo "║    Butler v4 — 全新环境部署          ║"
  echo "╚══════════════════════════════════════╝"
  echo ""

  local extra_args=""
  [[ "$install_systemd" -eq 1 ]] && extra_args="$extra_args --systemd"
  [[ "$skip_langfuse" -eq 0 ]] && extra_args="$extra_args --langfuse"

  bash "$ROOT/scripts/deploy-new-env.sh" $extra_args

  if [[ "$skip_langfuse" -eq 0 ]]; then
    _info "配置观测演化生产默认值..."
    bash "$ROOT/scripts/butler-observability-provision.sh" 2>/dev/null || _warn "观测配置跳过"
    if [[ -f "$ROOT/scripts/install-butler-eval-sync-timer.sh" ]]; then
      bash "$ROOT/scripts/install-butler-eval-sync-timer.sh" --no-enable 2>/dev/null || true
    fi
  fi

  echo ""
  _ok "全新部署完成"
  echo ""
  echo "  下一步:"
  echo "  1. 编辑 $ROOT/.env 填入 API keys"
  echo "  2. 运行 bash scripts/butler-deploy.sh status 检查状态"
}

# ─── Update（增量更新） ───

_cmd_update() {
  local skip_langfuse=0
  local skip_reindex=0
  local skip_benchmark=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --skip-langfuse) skip_langfuse=1 ;;
      --skip-reindex) skip_reindex=1 ;;
      --skip-benchmark) skip_benchmark=1 ;;
      *) _err "Unknown update option: $1"; _usage; exit 1 ;;
    esac
    shift
  done

  echo ""
  echo "╔══════════════════════════════════════╗"
  echo "║    Butler v4 — 增量更新              ║"
  echo "╚══════════════════════════════════════╝"
  echo ""

  local prev_sha
  prev_sha=$(cd "$ROOT" && git rev-parse --short HEAD 2>/dev/null || echo "unknown")

  # Step 1: Git pull
  _info "[1/7] 拉取代码..."
  cd "$ROOT"
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git pull --ff-only 2>&1 || { _warn "git pull 失败（可能有本地修改）"; }
  else
    _warn "非 git 仓库，跳过 pull"
  fi
  local new_sha
  new_sha=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
  if [[ "$prev_sha" != "$new_sha" ]]; then
    _ok "代码更新: $prev_sha → $new_sha"
  else
    _info "代码无变化: $new_sha"
  fi

  # Step 2: Clean stale caches
  _info "[2/7] 清理 __pycache__..."
  find "$ROOT" -path '*/butler*/__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
  find "$ROOT" -path '*/tests*/__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true

  # Step 3: Sync dependencies
  _info "[3/7] 同步依赖..."
  if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    pip install -e "$ROOT[all]" --quiet 2>/dev/null || _warn "pip install 失败（非致命）"
  else
    if [[ -d "$ROOT/.venv" ]]; then
      source "$ROOT/.venv/bin/activate"
      pip install -e "$ROOT[all]" --quiet 2>/dev/null || _warn "pip install 失败（非致命）"
    else
      _warn "无 venv，跳过 pip install"
    fi
  fi

  # Step 4: Restart Butler gateway
  _info "[4/7] 重启 Butler 服务..."
  if systemctl --user is-active "$UNIT" >/dev/null 2>&1; then
    bash "$ROOT/scripts/install-butler-gateway-service.sh" 2>/dev/null || true
    bash "$ROOT/scripts/install-butler-ops-bundle.sh" --no-enable 2>/dev/null || true
    sleep 2
    _ok "Butler 服务已重启"
  else
    _info "Gateway 未运行，跳过重启"
  fi

  # Step 5: LangFuse update
  if [[ "$skip_langfuse" -eq 0 ]]; then
    _info "[5/7] 更新 LangFuse 栈..."
    if _langfuse_is_running; then
      cd "$COMPOSE_DIR"
      docker compose pull --quiet 2>/dev/null || true
      docker compose up -d 2>/dev/null || _warn "LangFuse 更新失败（非致命）"
      _ok "LangFuse 已更新"
    elif command -v docker &>/dev/null; then
      _info "LangFuse 未运行，启动中..."
      _langfuse_up || _warn "LangFuse 启动失败（非致命）"
    else
      _info "Docker 未安装，跳过 LangFuse"
    fi
  else
    _info "[5/7] 跳过 LangFuse（--skip-langfuse）"
  fi

  if [[ "$skip_langfuse" -eq 0 ]]; then
    _info "同步观测演化配置..."
    bash "$ROOT/scripts/butler-observability-provision.sh" 2>/dev/null || _warn "观测配置跳过"
  fi

  # Step 6: Benchmark regression gate (O7)
  if [[ "$skip_benchmark" -eq 0 ]]; then
    _info "[6/7] 基准回归门 (B1–B8 / MB1–MB7)..."
    local bench_args=""
    if [[ "$skip_langfuse" -eq 0 ]] && _langfuse_health 2>/dev/null; then
      bench_args="--sync-dataset"
    fi
    if bash "$ROOT/scripts/butler-eval-regression.sh" $bench_args 2>&1; then
      _ok "基准回归通过"
    else
      _warn "基准回归未完全通过（见上方输出）"
    fi
  else
    _info "[6/7] 跳过基准回归（--skip-benchmark）"
  fi

  # Step 7: Verify
  _info "[7/7] 部署验证..."
  cd "$ROOT"
  if systemctl --user is-active "$UNIT" >/dev/null 2>&1; then
    bash "$ROOT/scripts/butler-gateway-ops.sh" verify 2>&1 || _warn "验证不完全通过"
  else
    PYTHONPATH="$ROOT" python3 -c "
from butler import get_build_identity
info = get_build_identity()
print(f'  Butler v{info[\"version\"]} (commit={info[\"git_sha\"]})')
" 2>/dev/null || _warn "Butler import 验证失败"
  fi

  if [[ "$skip_reindex" -eq 0 ]]; then
    if [[ -f "$ROOT/scripts/butler-memory-reindex.sh" ]]; then
      bash "$ROOT/scripts/butler-memory-reindex.sh" --project "灵文1号" 2>/dev/null || true
    fi
  fi

  echo ""
  _ok "增量更新完成 ($prev_sha → $new_sha)"
}

# ─── Rollback ───

_cmd_rollback() {
  local steps=1
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --steps) steps="$2"; shift ;;
      *) _err "Unknown rollback option: $1"; exit 1 ;;
    esac
    shift
  done

  echo ""
  echo "╔══════════════════════════════════════╗"
  echo "║    Butler v4 — 回滚                  ║"
  echo "╚══════════════════════════════════════╝"
  echo ""

  cd "$ROOT"
  local current_sha
  current_sha=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
  _info "当前版本: $current_sha"

  _info "回滚 $steps 个提交..."
  git log --oneline -"$((steps + 1))" 2>/dev/null || true
  echo ""

  local target_sha
  target_sha=$(git rev-parse --short "HEAD~$steps" 2>/dev/null)
  if [[ -z "$target_sha" ]]; then
    _err "无法计算回滚目标"
    exit 1
  fi

  _warn "将回滚到: $target_sha"
  read -r -p "确认回滚? [y/N] " confirm
  if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "取消回滚"
    exit 0
  fi

  git checkout "$target_sha" -- . 2>/dev/null || {
    _err "git checkout 失败"
    exit 1
  }

  _info "同步依赖..."
  pip install -e "$ROOT[all]" --quiet 2>/dev/null || true

  if systemctl --user is-active "$UNIT" >/dev/null 2>&1; then
    _info "重启服务..."
    systemctl --user restart "$UNIT"
    sleep 2
  fi

  _ok "回滚完成: $current_sha → $target_sha"
  echo "  如需恢复: git checkout main"
}

# ─── Status ───

_cmd_status() {
  echo ""
  echo "╔══════════════════════════════════════╗"
  echo "║    Butler v4 — 全栈状态              ║"
  echo "╚══════════════════════════════════════╝"
  echo ""
  _butler_status
  _langfuse_status
  _observability_status
  echo ""

  echo "  === Systemd Timers ==="
  systemctl --user list-timers --all 2>/dev/null | grep -i butler || echo "  (无 Butler 定时器)"
  echo ""
}

# ─── Langfuse 子命令 ───

_cmd_langfuse() {
  local subcmd="${1:-status}"
  shift || true
  case "$subcmd" in
    up|start) _langfuse_up ;;
    down|stop) _langfuse_down ;;
    status) _langfuse_status ;;
    logs) _langfuse_logs ;;
    pull|upgrade) _langfuse_pull ;;
    *)
      _err "Unknown langfuse subcommand: $subcmd"
      echo "  Available: up, down, status, logs, pull"
      exit 1
      ;;
  esac
}

# ─── Main ───

main() {
  local cmd="${1:-}"
  shift || true
  case "$cmd" in
    init) _cmd_init "$@" ;;
    update|upgrade) _cmd_update "$@" ;;
    status) _cmd_status ;;
    rollback) _cmd_rollback "$@" ;;
    langfuse) _cmd_langfuse "$@" ;;
    -h|--help|help|"") _usage ;;
    *)
      _err "Unknown command: $cmd"
      _usage
      exit 1
      ;;
  esac
}

main "$@"
