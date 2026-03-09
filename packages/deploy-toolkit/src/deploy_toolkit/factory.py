"""FastAPI application factory."""

from __future__ import annotations

import warnings
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, TypeVar

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .health import HealthCheck, create_health_router

T = TypeVar("T")


def create_app(
    *,
    title: str,
    settings: Any,
    version: str = "1.0.0",
    description: str = "",
    routers: list[tuple[APIRouter, str]] | None = None,
    lifespan: Callable[[FastAPI], Any] | None = None,
    health_checks: list[HealthCheck] | None = None,
) -> FastAPI:
    """Create a FastAPI application with zero-config deployment setup.

    Args:
        title: Application title for OpenAPI docs
        settings: Settings object (should inherit from DeploySettings or have same attributes)
        version: Application version
        description: Application description for OpenAPI docs
        routers: List of (router, prefix) tuples to mount under /api
        lifespan: Application lifespan context manager
        health_checks: List of async health check functions

    Returns:
        Configured FastAPI application

    Example:
        app = create_app(
            title="Sleep Scoring API",
            settings=Settings(),
            routers=[
                (files.router, "/files"),
                (markers.router, "/markers"),
            ],
            health_checks=[check_database],
        )
    """
    # Extract settings (support both object and callable)
    s = settings() if callable(settings) else settings

    # Get configuration from settings (duck-typed)
    app_name = getattr(s, "app_name", "") or getattr(s, "APP_NAME", "")
    root_path = getattr(s, "root_path", "") or (f"/{app_name}" if app_name else "")
    debug = getattr(s, "DEBUG", False) or getattr(s, "debug", False)

    # Create the FastAPI app
    app = FastAPI(
        title=title,
        version=version,
        description=description,
        root_path=root_path,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
        debug=debug,
    )

    # Configure CORS
    _configure_cors(app, s)

    # Add health endpoints
    health_router = create_health_router(health_checks, version)
    app.include_router(health_router, prefix="/api")

    # Add root endpoint
    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "name": title,
            "version": version,
            "docs": f"{root_path}/api/docs",
            "health": f"{root_path}/api/health",
        }

    # Register application routers
    for router, prefix in routers or []:
        app.include_router(router, prefix=f"/api{prefix}")

    # Try to auto-configure auth if global_auth is available
    _try_configure_auth(app, s)

    # Try to auto-configure error handlers
    _try_configure_errors(app, s)

    return app


def _configure_cors(app: FastAPI, settings: Any) -> None:
    """Configure CORS middleware."""
    # Get origins from settings
    cors_origins = getattr(settings, "cors_origins_list", None)
    if cors_origins is None:
        cors_origins_str = getattr(settings, "CORS_ORIGINS", "*")
        if cors_origins_str == "*":
            cors_origins = ["*"]
        else:
            cors_origins = [o.strip() for o in cors_origins_str.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _try_configure_auth(app: FastAPI, settings: Any) -> None:
    """Try to configure auth if global_auth is available and SITE_PASSWORD is set."""
    site_password = getattr(settings, "SITE_PASSWORD", "") or getattr(settings, "site_password", "")

    if not site_password:
        return  # No auth needed

    try:
        from global_auth import create_auth_router

        # Create settings getter
        get_settings = lambda: settings

        router = create_auth_router(get_settings)
        app.include_router(router, prefix="/api/auth", tags=["auth"])

    except ImportError:
        warnings.warn(
            "SITE_PASSWORD is set but 'global-auth' package is not installed. "
            "Auth endpoints will not be available. "
            "Install with: pip install global-pass-honor-username-auth",
            stacklevel=2,
        )


def _try_configure_errors(app: FastAPI, settings: Any) -> None:
    """Try to configure standard error handlers if fastapi_errors is available."""
    try:
        from fastapi_errors import setup_error_handlers

        debug = getattr(settings, "DEBUG", False) or getattr(settings, "debug", False)
        setup_error_handlers(app, debug=debug)

    except ImportError:
        pass  # fastapi-errors not installed, skip silently
