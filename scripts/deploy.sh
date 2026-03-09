#!/bin/bash
# Sleep Scoring Web Deployment Script

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/sleep-scoring-web}"
COMPOSE_FILE="${COMPOSE_FILE:-${APP_DIR}/docker/docker-compose.local.yml}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
REGISTRY="ghcr.io"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

error() {
    log "ERROR: $1" >&2
    exit 1
}

check_prerequisites() {
    log "Checking prerequisites..."
    command -v docker >/dev/null 2>&1 || error "Docker is not installed"
    docker compose version >/dev/null 2>&1 || error "Docker Compose is not installed"
    [ -f "$COMPOSE_FILE" ] || error "Compose file not found: $COMPOSE_FILE"
    [ -f "${APP_DIR}/docker/.env" ] || error ".env file not found at ${APP_DIR}/docker/.env"
    log "Prerequisites OK"
}

pull_images() {
    log "Pulling images (tag: ${IMAGE_TAG})..."
    cd "${APP_DIR}/docker"

    if [ -n "${GITHUB_REPOSITORY:-}" ]; then
        export BACKEND_IMAGE="${REGISTRY}/${GITHUB_REPOSITORY}/sleep-scoring-backend:${IMAGE_TAG}"
        export FRONTEND_IMAGE="${REGISTRY}/${GITHUB_REPOSITORY}/sleep-scoring-frontend:${IMAGE_TAG}"
        docker pull "${BACKEND_IMAGE}" || log "WARNING: Backend pull failed"
        docker pull "${FRONTEND_IMAGE}" || log "WARNING: Frontend pull failed"
    else
        log "GITHUB_REPOSITORY not set, building locally"
    fi
}

restart_services() {
    log "Restarting services..."
    cd "${APP_DIR}/docker"
    # Ensure postgres is running first (don't recreate — preserves data)
    docker compose -f "$(basename "$COMPOSE_FILE")" up -d postgres
    sleep 5
    # Force recreate backend + frontend with new images
    docker compose -f "$(basename "$COMPOSE_FILE")" up -d --force-recreate backend frontend
    log "Services restarted"
}

health_check() {
    log "Running health check..."
    local health_url="${HEALTH_URL:-http://localhost:8500/health}"

    for i in $(seq 1 10); do
        if curl -sf "$health_url" >/dev/null 2>&1; then
            log "Health check passed"
            return 0
        fi
        log "Attempt $i/10 failed, retrying..."
        sleep 10
    done

    error "Health check failed after 10 attempts"
}

main() {
    log "=========================================="
    log "Sleep Scoring Web Deployment"
    log "=========================================="

    check_prerequisites
    pull_images
    restart_services
    sleep 10
    health_check

    log "=========================================="
    log "Deployment Complete"
    log "=========================================="
    cd "${APP_DIR}/docker"
    docker compose -f "$(basename "$COMPOSE_FILE")" ps
}

main "$@"
