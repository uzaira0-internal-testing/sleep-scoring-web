# Sleep Scoring Web - Frontend Dockerfile
# Build context: repo root (needs access to packages/sleep-scoring-wasm for WASM build)
# Multi-stage build: Rust for WASM, Bun for build, nginx for serve

# =============================================================================
# WASM build stage — compile Rust algorithms to WebAssembly
# =============================================================================
FROM rust:1-slim-bookworm AS wasm-builder

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN curl https://rustwasm.github.io/wasm-pack/installer/init.sh -sSf | sh

WORKDIR /wasm
COPY packages/sleep-scoring-wasm/Cargo.toml ./
COPY packages/sleep-scoring-wasm/crates ./crates

RUN wasm-pack build --target web --out-dir /wasm/pkg crates/algorithms

# =============================================================================
# Frontend build stage
# =============================================================================
FROM oven/bun:1-alpine AS builder

WORKDIR /app

# Copy package files first (for better layer caching)
COPY frontend/package.json frontend/bun.lock* ./

# Install dependencies
RUN bun install

# Copy source code (excluding node_modules via .dockerignore)
COPY frontend/src ./src
COPY frontend/server ./server
COPY frontend/public ./public
COPY frontend/index.html ./
COPY frontend/vite.config.ts ./
COPY frontend/tsconfig.json ./
COPY frontend/tsconfig.app.json ./
COPY frontend/tsconfig.node.json ./
COPY frontend/bunfig.toml ./
COPY frontend/eslint.config.js ./

# Copy WASM build output into the expected location
COPY --from=wasm-builder /wasm/pkg ./src/wasm/pkg

# Build the application using Vite
RUN bun run build

# =============================================================================
# Production stage
# =============================================================================
FROM nginx:alpine

# Copy built assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Install curl for healthcheck
RUN apk add --no-cache curl

# Copy nginx configuration
COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Copy entrypoint script for BASE_PATH injection
COPY docker/frontend/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost/health || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
