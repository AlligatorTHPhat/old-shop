import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.concurrency import run_in_threadpool

from app.api.router import api_router
from app.core.config import settings
from app.core.database import ping_database
from app.core.exceptions import AppError
from app.core.logging import request_id_ctx, setup_logging
from app.services.mongo import ping_mongo
from app.services.storage import ensure_media_dirs, get_storage, ping_minio, validate_path

setup_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)
logger = logging.getLogger("app")

# Probes and scrapes would drown the access log.
QUIET_PATHS = {"/health", "/health/ready", "/metrics"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "%s %s started",
        settings.PROJECT_NAME,
        settings.PROJECT_VERSION,
        extra={"environment": settings.ENVIRONMENT, "docs": "/api/docs"},
    )
    yield
    logger.info("Shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.PROJECT_VERSION,
        description="Second-hand marketplace API: catalogue, cart, orders, PayPal checkout, moderation.",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            if request.url.path not in QUIET_PATHS:
                logger.info(
                    "%s %s %s",
                    request.method,
                    request.url.path,
                    response.status_code,
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "status": response.status_code,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                        "client_ip": request.headers.get("X-Real-IP")
                        or (request.client.host if request.client else None),
                    },
                )
            return response
        finally:
            request_id_ctx.reset(token)

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        detail = str(exc) if settings.DEBUG else "Internal server error"
        return JSONResponse(status_code=500, content={"detail": "Internal server error", "error": detail})

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="/api/docs")

    @app.get("/health", tags=["system"], summary="Liveness probe")
    async def health():
        return {"status": "ok", "service": settings.PROJECT_NAME, "version": settings.PROJECT_VERSION}

    @app.get("/ready", include_in_schema=False)
    @app.get("/health/ready", tags=["system"], summary="Readiness of PostgreSQL, MongoDB and image storage")
    async def ready():
        checks = {"database": "up" if await run_in_threadpool(ping_database) else "down"}
        if settings.MONGO_URI:
            checks["mongo"] = "up" if await run_in_threadpool(ping_mongo) else "down"
        if settings.STORAGE_BACKEND == "minio":
            checks["minio"] = "up" if await run_in_threadpool(ping_minio) else "down"
        available = all(value == "up" for value in checks.values())
        return JSONResponse(
            status_code=200 if available else 503, content={"status": "ok" if available else "unavailable", **checks}
        )

    app.include_router(api_router, prefix=settings.API_V1_STR)

    ensure_media_dirs()

    @app.api_route("/media/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def media(path: str, request: Request):
        return get_storage().response(validate_path(path), head=request.method == "HEAD")

    Instrumentator(excluded_handlers=["/health.*", "/metrics", "/media.*"]).instrument(app).expose(
        app, include_in_schema=False
    )
    return app


app = create_app()
