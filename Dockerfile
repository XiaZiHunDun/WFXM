# syntax=docker/dockerfile:1.7
# ---------- Stage 1: deps (pnpm fetch + install) ----------
FROM node:20-bookworm-slim AS deps
WORKDIR /repo

# system deps for pnpm + native modules
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates python3 build-essential \
    && rm -rf /var/lib/apt/lists/*

# Enable corepack for pnpm@9.15.0 (matches butler-v5 packageManager)
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate

# Copy workspace files first (cache pnpm install)
COPY pnpm-workspace.yaml package.json ./
COPY apps packages cli ./apps ./packages ./cli
# pnpm fetch uses content-hash, so deps lockfile alone is enough
ENV NODE_ENV=production
RUN pnpm fetch --frozen-lockfile
RUN pnpm install --frozen-lockfile --offline --ignore-scripts


# ---------- Stage 2: build (compile TypeScript) ----------
FROM deps AS build
WORKDIR /repo

# Copy source (changes more often than deps)
COPY . .

# Build all packages
RUN pnpm -r build


# ---------- Stage 3: runtime (minimal final image) ----------
FROM node:20-bookworm-slim AS runtime
WORKDIR /app

# Runtime system deps (postgres-client for healthcheck, tini for signal handling)
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client tini ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1001 butler \
    && useradd --system --uid 1001 --gid butler --no-create-home butler

ENV NODE_ENV=production \
    PNPM_HOME=/usr/local/share/pnpm \
    PATH=/usr/local/share/pnpm:$PATH

# Copy only the built artifacts + node_modules (not full source tree)
COPY --from=build --chown=butler:butler /repo/apps /app/apps
COPY --from=build --chown=butler:butler /repo/packages /app/packages
COPY --from=build --chown=butler:butler /repo/cli /app/cli
COPY --from=build --chown=butler:butler /repo/node_modules /app/node_modules
COPY --from=build --chown=butler:butler /repo/package.json /app/package.json
COPY --from=build --chown=butler:butler /repo/pnpm-workspace.yaml /app/pnpm-workspace.yaml

USER butler

# Health check (matches butler app's /health endpoint)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD pg_isready -h "${DB_HOST:-postgres}" -p "${DB_PORT:-5432}" -U "${DB_USER:-butler}" \
   && node -e "fetch('http://127.0.0.1:' + (process.env.PORT||3000) + '/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))" \
  || exit 1

EXPOSE 3000

# tini for proper signal handling (SIGTERM → app shutdown)
ENTRYPOINT ["/usr/bin/tini", "--"]

# Default cmd — implementer must verify correct entry point path
# against butler-v5 `pnpm -r build` output (likely apps/api/dist/main.js
# or cli/dist/index.js depending on package being primary)
CMD ["node", "apps/api/dist/main.js"]
