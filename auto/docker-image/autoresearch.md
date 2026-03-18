# Autoresearch: Docker Image Size

## Objective
Reduce backend Docker image size by removing unused dependencies (scikit-learn, polars suspected dead), optimizing layers, and trimming unnecessary files.

## Stopping Condition
Stop when improvement is <5% after 3 consecutive cycles.

## Metrics
- **Primary (optimization target)**: `image_mb` (MB, lower is better)
- **Secondary**: build time

## How to Run
`./auto/docker-image/autoresearch.sh`

## Files in Scope
- `docker/backend/Dockerfile` — Backend Docker build
- `docker/frontend/Dockerfile` — Frontend Docker build
- `docker/docker-compose.local.yml` — Compose config
- `pyproject.toml` — Python dependencies
- `sleep_scoring_web/` — Check for actual dependency usage

## Off Limits
- `tests/` — Do not modify tests
- `auto/` — Autoresearch infrastructure
- Application logic (only dependency/build changes)

## Constraints
- Backend must start and pass health check after changes
- All existing tests must pass
- No functionality regression

## What's Been Tried
(nothing yet)
