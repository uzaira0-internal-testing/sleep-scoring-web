"""Health check endpoints and utilities."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str  # "healthy" or "unhealthy"
    checks: dict[str, str] = {}  # Individual check results
    version: str = ""


# Type alias for health check functions
# Returns (check_name, is_healthy, optional_message)
HealthCheck = Callable[[], Awaitable[tuple[str, bool, str | None]]]


def create_health_router(
    health_checks: list[HealthCheck] | None = None,
    version: str = "1.0.0",
) -> APIRouter:
    """Create a health check router.

    Args:
        health_checks: List of async functions that return (name, is_healthy, message)
        version: Application version to include in response

    Returns:
        APIRouter with /health endpoint
    """
    router = APIRouter(tags=["health"])

    @router.get("/health", response_model=HealthResponse)
    async def health_check() -> HealthResponse:
        """Comprehensive health check endpoint."""
        checks: dict[str, str] = {}
        all_healthy = True

        for check_fn in health_checks or []:
            try:
                name, is_healthy, message = await check_fn()
                if is_healthy:
                    checks[name] = message or "ok"
                else:
                    checks[name] = message or "unhealthy"
                    all_healthy = False
            except Exception as e:
                # If check itself fails, mark as unhealthy
                checks[check_fn.__name__] = f"error: {e}"
                all_healthy = False

        return HealthResponse(
            status="healthy" if all_healthy else "unhealthy",
            checks=checks,
            version=version,
        )

    @router.get("/ready")
    async def readiness_check() -> dict[str, str]:
        """Simple readiness probe for Kubernetes/Docker."""
        return {"status": "ready"}

    @router.get("/live")
    async def liveness_check() -> dict[str, str]:
        """Simple liveness probe for Kubernetes/Docker."""
        return {"status": "alive"}

    return router
