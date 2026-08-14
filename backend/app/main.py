"""FastAPI application entrypoint (mvp-spec Epic 01)."""

import asyncio
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import settings
from app.core.errors import StudioError
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Generation worker (Stage C) + WebSocket event gateway (Stage C)
    from app.events.ws import start_gateway
    from app.generations.worker import worker_loop

    start_gateway()
    worker_task = asyncio.create_task(worker_loop())
    logger.info("startup: generation worker + ws event gateway active")
    yield
    worker_task.cancel()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_logging(request: Request, call_next):  # noqa: ANN001
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "http %s %s -> %s (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(StudioError)
    async def studio_error_handler(request: Request, exc: StudioError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.warning(
            "studio error %s on %s %s: %s",
            exc.code,
            request.method,
            request.url.path,
            exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "request_id": request_id,
                }
            },
        )

    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
