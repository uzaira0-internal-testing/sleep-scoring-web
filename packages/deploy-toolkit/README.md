# deploy-toolkit

Zero-config FastAPI app factory for Traefik deployment.

## Features

- Auto-configures `root_path` from `APP_NAME` environment variable
- Standard health endpoints at `/api/health`
- CORS configuration
- Optional auth integration with `global-auth` package
- Sensible defaults for internal research tools

## Installation

```bash
pip install deploy-toolkit
```

## Usage

```python
from deploy_toolkit import create_app
from .config import Settings
from .api import files, markers

app = create_app(
    title="My API",
    settings=Settings(),
    routers=[
        (files.router, "/files"),
        (markers.router, "/markers"),
    ],
)
```

## Configuration

Set these environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `APP_NAME` | Yes | App identifier, used for path prefix (e.g., `sleep-scoring`) |
| `SITE_PASSWORD` | No | If set and `global-auth` installed, auth is auto-configured |

## How It Works

1. `APP_NAME=sleep-scoring` sets `root_path=/sleep-scoring`
2. All routers are mounted under `/api` prefix
3. Health check at `/api/health`
4. OpenAPI docs at `/api/docs`
5. If `SITE_PASSWORD` is set, auth endpoints auto-added at `/api/auth`

## With Traefik

The app expects Traefik to strip the path prefix:

```yaml
labels:
  - "traefik.http.routers.myapp-api.rule=PathPrefix(`/sleep-scoring/api`)"
  - "traefik.http.middlewares.myapp-strip.stripprefix.prefixes=/sleep-scoring"
  - "traefik.http.routers.myapp-api.middlewares=myapp-strip"
```
