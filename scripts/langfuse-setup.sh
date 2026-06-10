#!/usr/bin/env bash
# LangFuse one-click setup for Butler observability.
# Usage:
#   ./scripts/langfuse-setup.sh                        # Start LangFuse stack
#   ./scripts/langfuse-setup.sh --down                 # Stop LangFuse stack
#   ./scripts/langfuse-setup.sh --create-project NAME  # Create a new LangFuse project
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_DIR="$SCRIPT_DIR/../deploy/langfuse"
ENV_FILE="$COMPOSE_DIR/.env"

if [[ "${1:-}" == "--down" ]]; then
    echo "Stopping LangFuse stack..."
    cd "$COMPOSE_DIR" && docker compose down
    exit 0
fi

if [[ "${1:-}" == "--create-project" ]]; then
    PROJECT_NAME="${2:-}"
    if [[ -z "$PROJECT_NAME" ]]; then
        echo "Usage: $0 --create-project <project-name>" >&2
        exit 1
    fi
    echo "Creating LangFuse project: $PROJECT_NAME"

    LANGFUSE_HOST="${LANGFUSE_HOST:-http://localhost:3000}"

    if ! curl -sf "$LANGFUSE_HOST/api/public/health" > /dev/null 2>&1; then
        echo "ERROR: LangFuse is not running at $LANGFUSE_HOST" >&2
        echo "Start it first: $0" >&2
        exit 1
    fi

    PROJECT_ID=$(echo "$PROJECT_NAME" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
    PK="pk-${PROJECT_ID}"
    SK="sk-${PROJECT_ID}-$(openssl rand -hex 8)"

    CONFIG_DIR="${BUTLER_HOME:-$HOME/.butler}/projects/$PROJECT_ID"
    mkdir -p "$CONFIG_DIR"
    cat > "$CONFIG_DIR/langfuse.json" <<CONF
{
  "project_name": "$PROJECT_NAME",
  "project_id": "$PROJECT_ID",
  "langfuse_host": "$LANGFUSE_HOST",
  "langfuse_public_key": "$PK",
  "langfuse_secret_key": "$SK"
}
CONF

    echo ""
    echo "=== Project Created ==="
    echo "  Name:       $PROJECT_NAME"
    echo "  ID:         $PROJECT_ID"
    echo "  Public Key: $PK"
    echo "  Secret Key: $SK"
    echo "  Config:     $CONFIG_DIR/langfuse.json"
    echo ""
    echo "NOTE: You need to create this project in the LangFuse UI as well:"
    echo "  1. Open $LANGFUSE_HOST"
    echo "  2. Settings → API Keys → Create"
    echo "  3. Use the public/secret keys above"
    echo ""
    exit 0
fi

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Generating secrets..."
    NEXTAUTH_SECRET=$(openssl rand -base64 32)
    SALT=$(openssl rand -base64 16)
    ENCRYPTION_KEY=$(openssl rand -hex 32)
    cat > "$ENV_FILE" <<EOF
NEXTAUTH_SECRET=$NEXTAUTH_SECRET
SALT=$SALT
ENCRYPTION_KEY=$ENCRYPTION_KEY
LANGFUSE_ADMIN_PASSWORD=butler_admin_2026
EOF
    echo "Created $ENV_FILE with generated secrets."
else
    echo "Using existing $ENV_FILE"
fi

echo ""
echo "Starting LangFuse stack (5 services: langfuse, postgres, clickhouse, redis, minio)..."
cd "$COMPOSE_DIR" && docker compose up -d

echo ""
echo "Waiting for LangFuse to be ready..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:3000/api/public/health > /dev/null 2>&1; then
        VERSION=$(curl -sf http://localhost:3000/api/public/health 2>&1 | python3 -c "import sys,json; print(json.load(sys.stdin).get('version','?'))" 2>/dev/null || echo "?")
        echo "LangFuse v$VERSION is ready!"
        break
    fi
    if [[ $i -eq 60 ]]; then
        echo "Warning: LangFuse not yet responding after 120s."
        echo "Check logs: cd $COMPOSE_DIR && docker compose logs langfuse"
    fi
    sleep 2
done

echo ""
echo "=============================="
echo " LangFuse Setup Complete"
echo "=============================="
echo ""
echo " UI:         http://localhost:3000"
echo " Login:      admin@butler.local"
echo " Password:   (see $ENV_FILE)"
echo ""
echo " Butler .env configuration:"
echo "   BUTLER_LANGFUSE_ENABLED=1"
echo "   LANGFUSE_HOST=http://localhost:3000"
echo "   LANGFUSE_PUBLIC_KEY=pk-butler-dev"
echo "   LANGFUSE_SECRET_KEY=sk-butler-dev"
echo ""
echo " To stop:    $0 --down"
echo " Logs:       cd $COMPOSE_DIR && docker compose logs -f"
