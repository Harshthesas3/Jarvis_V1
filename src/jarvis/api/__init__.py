"""REST API package for JARVIS — exposes core capabilities over HTTP."""

from jarvis.api.server import (
    create_app,
    run_server,
)

__all__ = [
    "create_app",
    "run_server",
]
