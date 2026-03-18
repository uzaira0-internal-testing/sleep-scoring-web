#!/usr/bin/env bash
# Autoresearch: Docker image size benchmark
set -euo pipefail
cd "$(dirname "$0")/../.."

METRIC_NAME="image_mb"

echo "=== Building backend image ==="
cd docker
docker compose -f docker-compose.local.yml build backend 2>&1 | tail -5

# Get image size
IMAGE_NAME=$(docker compose -f docker-compose.local.yml config --images | grep backend | head -1)
if [ -z "$IMAGE_NAME" ]; then
  IMAGE_NAME="docker-backend"
fi

SIZE_BYTES=$(docker image inspect "$IMAGE_NAME" --format='{{.Size}}' 2>/dev/null || echo "0")
if [ "$SIZE_BYTES" = "0" ]; then
  echo "FATAL: could not inspect image"
  exit 1
fi

SIZE_MB=$(echo "scale=1; $SIZE_BYTES / 1048576" | bc)

echo ""
echo "Image: $IMAGE_NAME"
echo "Size: ${SIZE_MB} MB"
echo ""
echo "METRIC ${METRIC_NAME}=${SIZE_MB}"
