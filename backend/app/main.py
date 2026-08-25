"""FastAPI application entry point.

Run locally:
    uvicorn app.main:app --reload
"""

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request

from app.api.v1.router import api_router
from app.api.v1.endpoints.ws import router as ws_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger, request_id_ctx, user_id_ctx
from app.db.session import engine

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("%s starting in %s mode", settings.APP_NAME, settings.ENVIRONMENT)
    live_loop = None
    if settings.MARKET_DATA_PROVIDER == "demo" and settings.LIVE_DEMO_ENABLED:
        from app.websocket.live_demo import LiveDemoLoop

        live_loop = LiveDemoLoop()
        try:
            await live_loop.start()
        except Exception:
            logger.exception("live demo loop failed to start â€” continuing without it")
            live_loop = None
    yield
    if live_loop is not None:
        await live_loop.stop()
    await engine.dispose()
    logger.info("%s shut down", settings.APP_NAME)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        description=(
            "Backend for the BOF Edge market scanner.\n\n"
            "Successful responses use `{\"success\": true, \"data\": â€¦}`; errors use "
            "`{\"success\": false, \"error\": {\"code\", \"message\"}}`."
        ),
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    if settings.CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):  # noqa: ANN001
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request_id_ctx.set(rid)
        user_id_ctx.set("-")
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        # Access log: method, path, status, duration only â€” never bodies/headers.
        logger.info(
            "%s %s -> %s (%.1f ms)", request.method, request.url.path,
            response.status_code, elapsed_ms,
        )
        response.headers["x-request-id"] = rid
        return response

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # noqa: ANN001
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if settings.ENVIRONMENT == "production":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response
    register_exception_handlers(app)

    @app.get("/healthz", tags=["health"], summary="Liveness probe")
    async def liveness() -> dict:
        return {"status": "ok"}

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    app.include_router(ws_router)  # /ws/market â€” realtime feed (Phase 4)
    return app


app = create_app()

