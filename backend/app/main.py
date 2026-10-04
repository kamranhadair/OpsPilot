"""FastAPI application assembly.

Assembly only: no business logic, no schema creation.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.request_context import REQUEST_ID_HEADER, RequestContextMiddleware


def create_app() -> FastAPI:
    """Build the OpsPilot FastAPI application."""
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(
        title="OpsPilot API",
        description="AI Support Operations Command Center",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )
    # Added last, so it is outermost: every response (including CORS) gets a request ID.
    app.add_middleware(RequestContextMiddleware)

    app.include_router(api_router, prefix=settings.api_prefix)

    return app


app = create_app()
