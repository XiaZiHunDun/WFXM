#!/usr/bin/env bash
# Butler v4 — 新环境一键部署
# Usage: bash scripts/deploy-new-env.sh [--extras EXTRA1,EXTRA2] [--lock] [--systemd]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUTLER_HOME="${BUTLER_HOME:-$HOME/.butler}"
EXTRAS=""
USE_LOCK=0
INSTALL_SYSTEMD=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --extras) EXTRAS="$2"; shift ;;
    --lock) USE_LOCK=1 ;;
    --systemd) INSTALL_SYSTEMD=1 ;;
    -h|--help)
      cat <<HELP
Butler v4 新环境部署

Usage:
  bash scripts/deploy-new-env.sh [OPTIONS]

Options:
  --extras EXTRA1,EXTRA2   安装额外的 optional extras（如 mcp,vectors,embeddings）
  --lock                   使用 requirements.lock 锁定版本安装
  --systemd                安装 systemd 用户服务（网关 + runtime timer）
  -h, --help               显示此帮助

Examples:
  bash scripts/deploy-new-env.sh
  bash scripts/deploy-new-env.sh --extras mcp,vectors --systemd
  bash scripts/deploy-new-env.sh --lock
HELP
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

echo "=== Butler v4 部署 ==="
echo "项目根: $ROOT"
echo "数据目录: $BUTLER_HOME"
echo ""

# --- Step 1: Python 版本检查 ---
echo "[1/7] 检查 Python 版本..."
PYTHON="$(command -v python3 || true)"
if [[ -z "$PYTHON" ]]; then
  echo "ERROR: 未找到 python3" >&2
  exit 1
fi
PY_VER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$("$PYTHON" -c "import sys; print(sys.version_info.major)")
PY_MINOR=$("$PYTHON" -c "import sys; print(sys.version_info.minor)")
if [[ "$PY_MAJOR" -lt 3 ]] || [[ "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 11 ]]; then
  echo "ERROR: 需要 Python >= 3.11，当前 $PY_VER" >&2
  exit 1
fi
echo "  Python $PY_VER ✓"

# --- Step 2: 虚拟环境 ---
echo "[2/7] 检查虚拟环境..."
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  if [[ -d "$ROOT/.venv" ]]; then
    echo "  激活已有 .venv"
    source "$ROOT/.venv/bin/activate"
  else
    echo "  创建 .venv..."
    "$PYTHON" -m venv "$ROOT/.venv"
    source "$ROOT/.venv/bin/activate"
  fi
fi
echo "  venv: $VIRTUAL_ENV ✓"

# --- Step 3: 安装依赖 ---
echo "[3/7] 安装依赖..."
pip install --upgrade pip -q

if [[ "$USE_LOCK" -eq 1 ]] && [[ -f "$ROOT/requirements.lock" ]]; then
  echo "  使用 requirements.lock 锁定版本..."
  pip install -r "$ROOT/requirements.lock" -q
  pip install -e "$ROOT" -q
else
  pip install -e "$ROOT[all]" -q
fi

if [[ -n "$EXTRAS" ]]; then
  IFS=',' read -ra EXTRA_LIST <<< "$EXTRAS"
  for extra in "${EXTRA_LIST[@]}"; do
    echo "  安装 extra: $extra"
    pip install -e "$ROOT[$extra]" -q
  done
fi
echo "  依赖安装完成 ✓"

# --- Step 4: 配置文件 ---
echo "[4/7] 初始化配置..."
mkdir -p "$BUTLER_HOME"

if [[ ! -f "$ROOT/.env" ]]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "  已创建 .env（请编辑填入 API keys）"
else
  echo "  .env 已存在 ✓"
fi

if [[ -f "$ROOT/scripts/setup-butler-config.sh" ]]; then
  bash "$ROOT/scripts/setup-butler-config.sh"
fi

# --- Step 5: 数据目录结构 ---
echo "[5/7] 初始化数据目录..."
mkdir -p "$BUTLER_HOME"/{sessions,runtime,skills,wechat,exports,gateway}
mkdir -p "$BUTLER_HOME"/gateway/{outbox/pending,outbox/sent,outbox/failed}
echo "  $BUTLER_HOME 结构就绪 ✓"

# --- Step 6: 健康检查 ---
echo "[6/7] 运行健康检查..."
if python3 -m butler doctor 2>/dev/null; then
  echo "  butler doctor ✓"
else
  butler doctor 2>/dev/null || echo "  WARNING: butler doctor 返回非零（检查 .env 配置）"
fi

# --- Step 7: systemd 服务（可选） ---
if [[ "$INSTALL_SYSTEMD" -eq 1 ]]; then
  echo "[7/7] 安装 systemd 服务..."
  if [[ -f "$ROOT/scripts/install-butler-gateway-service.sh" ]]; then
    bash "$ROOT/scripts/install-butler-gateway-service.sh" --no-restart
  fi
  if [[ -f "$ROOT/scripts/install-butler-ops-bundle.sh" ]]; then
    bash "$ROOT/scripts/install-butler-ops-bundle.sh" --no-restart
  fi
  echo "  systemd 服务已安装 ✓"
else
  echo "[7/7] 跳过 systemd（使用 --systemd 启用）"
fi

echo ""
echo "=== 部署完成 ==="
echo ""
echo "后续步骤:"
echo "  1. 编辑 $ROOT/.env 填入 API keys"
echo "  2. 编辑 $BUTLER_HOME/config.yaml 调整模型配置"
echo "  3. 启动 CLI:    butler"
echo "  4. 启动网关:    butler wechat serve"
echo "  5. 快速冒烟:    PYTHONPATH=. pytest tests/test_cc_p3_p4_features.py -q"
echo ""
echo "如需迁移旧数据: bash scripts/restore-butler-data.sh <backup.tar.gz>"
