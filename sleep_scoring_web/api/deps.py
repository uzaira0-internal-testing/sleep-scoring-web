"""
FastAPI dependencies for injection.

Provides database sessions and site password authentication using shared packages.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from global_auth import create_verify_site_password, get_username_optional
from sqlalchemy.ext.asyncio import AsyncSession

from sleep_scoring_web.config import get_settings
from sleep_scoring_web.db.session import get_async_session

# Database session dependency from db-toolkit
get_db = get_async_session

# Site password verification from global-auth
verify_site_password = create_verify_site_password(get_settings)


def verify_api_key(x_api_key: Annotated[str, Header()]) -> str:
    """Verify the API key header for programmatic/pipeline uploads."""
    settings = get_settings()
    if not settings.upload_api_key:
        raise HTTPException(status_code=501, detail="Upload API key not configured")
    if not secrets.compare_digest(x_api_key.encode("utf-8"), settings.upload_api_key.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


# Type aliases for cleaner dependency injection
DbSession = Annotated[AsyncSession, Depends(get_db)]
SitePassword = Annotated[str, Depends(verify_site_password)]
VerifiedPassword = SitePassword  # Alias for consistency with existing code
Username = Annotated[str, Depends(get_username_optional)]
ApiKey = Annotated[str, Depends(verify_api_key)]
