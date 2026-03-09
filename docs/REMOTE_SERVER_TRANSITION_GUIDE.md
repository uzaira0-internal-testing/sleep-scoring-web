# Remote Server Deployment Transition Guide

Complete guide for transitioning a monorepo package to remote server deployment with GitHub Actions auto-deployment, Docker Compose, and Traefik reverse proxy.

---

## Overview

This guide covers deploying a package from a monorepo to a standalone remote server using:
- **Git subtree push** for clean deployment without monorepo path prefixes
- **GitHub Actions** with self-hosted runner for auto-deployment on push
- **Docker Compose** for multi-container production stack (Postgres, Redis, backend, frontend)
- **Traefik** reverse proxy for path-based routing (e.g., `/flash`, `/screenshot`)
- **Global site password** for simple authentication gating
- **OpenAPI/Pydantic** as single source of truth for frontend-backend contracts
- **Vite environment variables** for configurable API paths

---

## 1. Git Subtree Push (CRITICAL)

### Problem

When a package lives in a monorepo (e.g., `apps/flash-processing/`), pushing directly from inside that folder includes the monorepo path prefix in all file paths, breaking the standalone deployment.

### Wrong Approach

```bash
# NEVER do this from inside a package folder
cd apps/flash-processing
git push flash-processing-standalone HEAD:main  # BROKEN!
# Results in paths like: apps/flash-processing/src/... on the remote
```

### Correct Approach

```bash
# ALWAYS use git subtree from monorepo root
cd /path/to/monorepo

# Normal push
git subtree push --prefix=apps/flash-processing flash-processing-standalone main

# If subtree push fails (non-fast-forward), split and force push:
git subtree split --prefix=apps/flash-processing -b temp-split
git push flash-processing-standalone temp-split:main --force
git branch -D temp-split
```

### Setup Remote Once

```bash
# Add the standalone repo as a remote
git remote add flash-processing-standalone git@github.com:user/flash-processing.git
```

---

## 2. GitHub Actions Auto-Deployment

### Architecture

```
Developer pushes via git subtree
        ↓
GitHub standalone repo receives push
        ↓
GitHub Actions workflow triggered
        ↓
Self-hosted runner on server executes:
    1. Checkout code
    2. docker compose build (backend, frontend)
    3. docker compose up -d --no-deps
        ↓
New containers running with zero downtime
```

### Workflow File

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Server

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: self-hosted

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Build and deploy
        working-directory: docker
        run: |
          # Use .env file from server (NOT in repo), only rebuild app containers
          docker compose -p flash-processing --env-file /opt/flash-processing/docker/.env build backend frontend
          docker compose -p flash-processing --env-file /opt/flash-processing/docker/.env up -d --no-deps backend frontend

      - name: Cleanup old images
        run: docker image prune -f
```

**Key Points:**
- `runs-on: self-hosted` - Uses runner installed on the deployment server
- `--env-file /opt/flash-processing/docker/.env` - Secrets stay on server, not in repo
- `--no-deps` - Only rebuild app containers, not database/redis
- `-p flash-processing` - Explicit project name for consistency

### Self-Hosted Runner Setup

On the deployment server:

```bash
# 1. Create directory for runner
mkdir -p /opt/actions-runner && cd /opt/actions-runner

# 2. Download runner (check GitHub for latest version)
curl -o actions-runner-linux-x64-2.311.0.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-linux-x64-2.311.0.tar.gz
tar xzf ./actions-runner-linux-x64-2.311.0.tar.gz

# 3. Configure (get token from GitHub repo Settings → Actions → Runners → New self-hosted runner)
./config.sh --url https://github.com/user/flash-processing --token YOUR_TOKEN

# 4. Install as service
sudo ./svc.sh install
sudo ./svc.sh start

# 5. Verify running
sudo ./svc.sh status
```

The runner user needs:
- Docker group membership: `sudo usermod -aG docker runner-user`
- Read access to `/opt/flash-processing/docker/.env`

---

## 3. Docker Configuration

### Project Structure

```
project/
├── docker/
│   ├── docker-compose.yml    # Production stack
│   ├── Dockerfile            # Backend container
│   └── .env.production.example
├── frontend/
│   ├── Dockerfile            # Frontend container (Bun + Nginx)
│   └── nginx.conf
├── src/
│   └── app_name/
└── pyproject.toml
```

### Backend Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

# Install uv for faster package installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN uv pip install --system -e ".[web]"

USER appuser
EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

CMD ["uvicorn", "app_name.web.app:app", "--host", "0.0.0.0", "--port", "8001"]
```

### Frontend Dockerfile (Bun + Nginx)

```dockerfile
# Stage 1: Build with Bun
FROM oven/bun:1-alpine AS build
WORKDIR /app

ARG APP_PATH_PREFIX=/flash
ENV VITE_API_BASE_URL=${APP_PATH_PREFIX}/api/v1
ENV VITE_BASE_PATH=${APP_PATH_PREFIX}

COPY package.json bun.lock* package-lock.json* ./
RUN bun install
COPY . .
RUN bun run build

# Stage 2: Serve with Nginx
FROM nginx:alpine AS production
RUN apk add --no-cache curl
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
```

### Docker Compose (Key Services)

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?required}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready"]
    networks:
      - internal

  redis:
    image: redis:7-alpine
    networks:
      - internal

  backend:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    environment:
      DATABASE_URL: postgresql://postgres:${POSTGRES_PASSWORD}@postgres:5432/app_db
      SITE_PASSWORD: ${SITE_PASSWORD:?required}
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - internal
      - traefik-local
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.flash-api.rule=PathPrefix(`/flash/api`)"
      - "traefik.http.services.flash-api.loadbalancer.server.port=8001"
      - "traefik.http.middlewares.flash-api-strip.stripprefix.prefixes=/flash"
      - "traefik.http.routers.flash-api.middlewares=flash-api-strip"

  frontend:
    build:
      context: ../frontend
      args:
        APP_PATH_PREFIX: /flash
    networks:
      - traefik-local
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.flash-fe.rule=PathPrefix(`/flash`)"
      - "traefik.http.services.flash-fe.loadbalancer.server.port=80"
      - "traefik.http.middlewares.flash-fe-strip.stripprefix.prefixes=/flash"
      - "traefik.http.routers.flash-fe.middlewares=flash-fe-strip"
      - "traefik.http.routers.flash-fe.priority=1"

networks:
  internal:
  traefik-local:
    external: true

volumes:
  postgres-data:
```

### Environment File (Server Only)

Create `/opt/flash-processing/docker/.env` on the server:

```bash
POSTGRES_PASSWORD=your-secure-password-here
SECRET_KEY=your-long-random-secret-key-here
UPLOAD_API_KEY=your-api-key-for-pipeline-uploads
SITE_PASSWORD=shared-password-for-all-users
```

**NEVER commit .env files to the repository.**

---

## 4. Traefik Path-Based Routing

### Architecture

```
Internet → Traefik (port 80/443)
    ↓ PathPrefix routing
├── /flash/api/* → backend (port 8001) [priority 2]
├── /flash/*     → frontend (port 80)  [priority 1]
└── /other/*     → other services
```

### Key Traefik Labels

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.flash-api.rule=PathPrefix(`/flash/api`)"
  - "traefik.http.services.flash-api.loadbalancer.server.port=8001"
  - "traefik.http.middlewares.flash-api-strip.stripprefix.prefixes=/flash"
  - "traefik.http.routers.flash-api.middlewares=flash-api-strip"
  - "traefik.http.routers.flash-api.priority=2"
```

### Backend: FastAPI Root Path

```python
import os
from fastapi import FastAPI

app = FastAPI(
    root_path=os.getenv("ROOT_PATH", "/flash"),
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
)
```

---

## 5. Global Site Password Authentication

For internal tools that need simple access control without user management.

### Frontend: Password Gate (authStore.ts)

```typescript
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface AuthState {
  isAuthenticated: boolean;
  username: string;  // For audit logging, not authentication
  login: (password: string, username: string) => Promise<boolean>;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      isAuthenticated: false,
      username: '',

      login: async (password: string, username: string) => {
        const response = await fetch('/api/v1/auth/verify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password }),
        });

        if (response.ok) {
          set({ isAuthenticated: true, username });
          localStorage.setItem('sitePassword', password);
          return true;
        }
        return false;
      },

      logout: () => {
        localStorage.removeItem('sitePassword');
        set({ isAuthenticated: false, username: '' });
      },
    }),
    { name: 'auth-storage' }
  )
);
```

### Frontend: API Client with Password Header

```typescript
import createClient from 'openapi-fetch';
import type { paths } from './schema';

export const apiClient = createClient<paths>({
  baseUrl: import.meta.env.VITE_BASE_PATH || ''
});

apiClient.use({
  onRequest({ request }) {
    const password = localStorage.getItem('sitePassword');
    if (password) {
      request.headers.set('X-Site-Password', password);
    }
    const username = localStorage.getItem('username');
    if (username) {
      request.headers.set('X-Username', username);
    }
    return request;
  },
});
```

### Backend: Password Verification

```python
import os
from typing import Annotated
from fastapi import Header, HTTPException

SITE_PASSWORD = os.getenv("SITE_PASSWORD", "")

def verify_site_password(
    x_site_password: Annotated[str | None, Header()] = None,
) -> str:
    if not SITE_PASSWORD:
        return ""  # No password configured, allow access
    if x_site_password != SITE_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid site password")
    return x_site_password
```

### Backend: Verification Endpoint

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class PasswordCheck(BaseModel):
    password: str

@router.post("/auth/verify")
async def verify_password(data: PasswordCheck) -> dict:
    if data.password == os.getenv("SITE_PASSWORD", ""):
        return {"valid": True}
    raise HTTPException(status_code=401, detail="Invalid password")
```

---

## 6. OpenAPI/Pydantic as Single Source of Truth

**The backend Pydantic schemas ARE the API contract.** The frontend generates TypeScript types from the OpenAPI spec.

### Generate OpenAPI Schema

```python
# scripts/generate_openapi.py
import json
from app_name.web.app import app

with open("frontend/openapi.json", "w") as f:
    json.dump(app.openapi(), f, indent=2)
```

### Generate TypeScript Types

```bash
cd frontend
npx openapi-typescript openapi.json -o src/api/schema.ts
```

### Workflow

1. Make API changes in backend (Pydantic models, endpoints)
2. Run `uv run python scripts/generate_openapi.py`
3. Run `cd frontend && npm run generate-types`
4. TypeScript will flag any breaking changes

---

## 7. Vite Environment Variables

### Define Types (vite-env.d.ts)

```typescript
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BASE_PATH: string;      // App prefix: "/flash"
  readonly VITE_API_BASE_URL: string;   // Full API path: "/flash/api/v1"
}
```

### Environment Files

```bash
# frontend/.env.development (local dev)
VITE_BASE_PATH=
VITE_API_BASE_URL=/api/v1

# Production: Set via Dockerfile ARG, not .env file
```

---

## 8. Deployment Checklist

### Initial Server Setup

- [ ] Install Docker and Docker Compose
- [ ] Start Traefik: `cd /opt/traefik && docker-compose up -d`
- [ ] Create app directory: `mkdir -p /opt/flash-processing/docker`
- [ ] Create `.env` file with secrets
- [ ] Install GitHub Actions self-hosted runner
- [ ] Add runner user to docker group

### For Each Deploy

1. Commit all changes in monorepo
2. If API changed: regenerate OpenAPI schema and TypeScript types
3. Push: `git subtree push --prefix=apps/flash-processing flash-processing-standalone main`
4. GitHub Actions auto-deploys to server
5. Verify: `curl https://server.com/flash/api/v1/health`

---

## 9. Troubleshooting

### 405 Method Not Allowed on New Endpoint

**Cause:** Server doesn't have the new code yet.
**Fix:** Deploy changes via git subtree push and wait for GitHub Actions.

### 404 on API Calls

- Check `VITE_BASE_PATH` matches Traefik PathPrefix
- Verify stripprefix middleware is configured
- Check router priority (API should be higher than frontend)

### 401 Unauthorized

- Verify `SITE_PASSWORD` is set in server `.env`
- Check frontend is sending `X-Site-Password` header

### Git Subtree Push Fails

```bash
git subtree split --prefix=apps/flash-processing -b temp-split
git push flash-processing-standalone temp-split:main --force
git branch -D temp-split
```

### Container Won't Start

```bash
docker logs flash-processing-backend
# Common: Missing env vars, port in use, health check failing
```

### GitHub Actions Runner Offline

```bash
cd /opt/actions-runner
sudo ./svc.sh status
sudo ./svc.sh restart
```

---

## Related Documentation

- [GitHub Actions Self-Hosted Runners](https://docs.github.com/en/actions/hosting-your-own-runners)
- [Docker Compose](https://docs.docker.com/compose/)
- [Traefik PathPrefix Router](https://doc.traefik.io/traefik/routing/routers/)
- [FastAPI Root Path](https://fastapi.tiangolo.com/advanced/behind-a-proxy/)
- [openapi-fetch Documentation](https://openapi-ts.pages.dev/openapi-fetch/)
- [Vite Environment Variables](https://vitejs.dev/guide/env-and-mode.html)
