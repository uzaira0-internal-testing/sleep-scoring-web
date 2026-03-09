# Sleep Scoring Web - Backend Dockerfile
# Installs shared packages from GitHub Releases
# Build context: repo root

FROM python:3.12-slim AS builder

# Build arguments for package versions
ARG PACKAGES_VERSION=0.1.0
ARG GITHUB_REPO=your-org/sleep-scoring-web

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /build

# Copy app-specific dependency files
COPY pyproject.toml ./
COPY uv.lock ./

# Create virtual environment
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install shared packages from GitHub Releases
# These are built and published by the publish-python-packages workflow
ENV PACKAGES_URL=https://github.com/${GITHUB_REPO}/releases/download/packages-v${PACKAGES_VERSION}
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install \
    "${PACKAGES_URL}/fastapi_errors-0.1.0-py3-none-any.whl" \
    "${PACKAGES_URL}/fastapi_files-0.1.0-py3-none-any.whl" \
    "${PACKAGES_URL}/fastapi_logging-0.1.0-py3-none-any.whl" \
    "${PACKAGES_URL}/fastapi_pagination-0.1.0-py3-none-any.whl" \
    "${PACKAGES_URL}/db_toolkit-0.1.0-py3-none-any.whl" \
    "${PACKAGES_URL}/deploy_toolkit-0.1.0-py3-none-any.whl" \
    "${PACKAGES_URL}/global_pass_honor_username_auth-0.1.0-py3-none-any.whl"

# Install app dependencies (excluding workspace packages which are already installed)
# Use pip instead of uv sync since we're not in a workspace context
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.32.0" \
    "pydantic>=2.0.0" \
    "pydantic-settings>=2.0.0" \
    "sqlalchemy[asyncio]>=2.0.0" \
    "asyncpg>=0.29.0" \
    "aiofiles>=24.0.0" \
    "python-multipart>=0.0.9" \
    "watchdog>=4.0.0" \
    "polars>=1.0.0" \
    "numpy>=2.0.0" \
    "pandas>=2.0.0" \
    "scikit-learn>=1.5.0"

# =============================================================================
# Production stage
# =============================================================================
FROM python:3.12-slim

# Install runtime dependencies (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY sleep_scoring_web ./sleep_scoring_web
COPY sleep_scoring_app/__init__.py ./sleep_scoring_app/__init__.py
COPY sleep_scoring_app/core ./sleep_scoring_app/core
# Replace the desktop algorithms __init__.py (which imports io/preprocessing not available in Docker)
# with a minimal version that only exports what the web app needs
RUN echo '"""Sleep scoring algorithms (web-minimal)."""' > ./sleep_scoring_app/core/algorithms/__init__.py

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command (use python -m to avoid hardcoded shebang paths)
CMD ["python", "-m", "uvicorn", "sleep_scoring_web.main:app", "--host", "0.0.0.0", "--port", "8000"]
