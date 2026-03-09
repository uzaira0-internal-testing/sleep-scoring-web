"""Zero-config FastAPI app factory for Traefik deployment.

Example usage:
    from deploy_toolkit import create_app, DeploySettings

    class Settings(DeploySettings):
        DATABASE_URL: str

    app = create_app(
        title="My API",
        settings=Settings(),
        routers=[
            (files.router, "/files"),
            (markers.router, "/markers"),
        ],
    )
"""

from __future__ import annotations

from .factory import create_app
from .health import HealthCheck, HealthResponse, create_health_router
from .settings import DeploySettings

__all__ = [
    "create_app",
    "create_health_router",
    "DeploySettings",
    "HealthCheck",
    "HealthResponse",
]

__version__ = "0.1.0"
