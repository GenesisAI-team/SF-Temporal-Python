"""FastAPI application factory."""

from fastapi import FastAPI

from super_factory.api.routes.health import router as health_router
from super_factory.api.webhooks.linear import router as linear_router


def create_app() -> FastAPI:
    """Build the Super Factory API application."""
    app = FastAPI(
        title="Super Factory",
        version="0.1.0",
        description="Software Factory orchestration API (GEN-17 bootstrap).",
    )
    app.include_router(health_router)
    app.include_router(linear_router)
    return app
