"""FastAPI dependency injection — provides the JarvisApplication instance
to endpoint handlers via request-scoped dependencies."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Request

from jarvis.app import JarvisApplication

logger = logging.getLogger("jarvis.api.dependencies")

# ---------------------------------------------------------------------------
# Module-level holder so the server module can inject the app without
# circular imports at module-load time.
# ---------------------------------------------------------------------------

_APP_INSTANCE: Optional[JarvisApplication] = None


def set_app(app: JarvisApplication) -> None:
    """Install the active JarvisApplication instance for dependency injection."""
    global _APP_INSTANCE
    _APP_INSTANCE = app
    logger.info("JarvisApplication installed for API dependencies")


def get_app() -> JarvisApplication:
    """Return the installed JarvisApplication instance.

    Raises
    ------
    RuntimeError
        If ``set_app()`` has not been called yet.
    """
    if _APP_INSTANCE is None:
        raise RuntimeError(
            "JarvisApplication has not been set in API dependencies. "
            "Call set_app() before starting the server."
        )
    return _APP_INSTANCE


# ---------------------------------------------------------------------------
# FastAPI dependency callable (used via ``Depends`` in route handlers)
# ---------------------------------------------------------------------------


async def get_app_from_request(request: Request) -> JarvisApplication:
    """FastAPI-compatible dependency that extracts the application instance.

    Usage in route handlers::

        @router.post("/plan")
        async def plan(text: str, app: JarvisApplication = Depends(get_app_from_request)):
            ...
    """
    # FastAPI stores per-request state; here we simply delegate to the
    # global holder, but could be swapped for a request-scoped container.
    return get_app()
