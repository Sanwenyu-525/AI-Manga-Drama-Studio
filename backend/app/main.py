"""FastAPI application entrypoint (mvp-spec Epic 01)."""

import asyncio
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.core.config import settings, validate_startup_config
from app.core.errors import StudioError
from app.core.logging import configure_logging, get_logger


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict | None = None,
) -> JSONResponse:
    """Unified error envelope (api-event-contract §6). request_id comes from the
    request-logging middleware (X-Request-ID header or generated), so every error
    response is traceable (P1-E4-T01)."""
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "request_id": request_id,
            }
        },
    )

configure_logging()
logger = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # P1-E5-T01: fail closed in production — refuse to boot with fake-content providers.
    validate_startup_config(settings)
    # Generation worker (Stage C) + WebSocket event gateway (Stage C)
    from app.events.ws import start_gateway, stop_gateway
    from app.generations.worker import worker_loop
    from app.jobs.scheduler import scheduler_loop

    start_gateway()
    worker_task = asyncio.create_task(worker_loop())
    scheduler_task = asyncio.create_task(scheduler_loop())
    logger.info("startup: generation worker + job scheduler + ws event gateway active")
    yield
    worker_task.cancel()
    scheduler_task.cancel()
    await stop_gateway()  # P1-E4-T02: unsubscribe + no dangling gateway tasks


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def local_session_auth(request: Request, call_next):
        """P1-E5-T02: enforce the local session token when one is configured.

        The Tauri shell spawns the backend with STUDIO_SESSION_TOKEN and the
        frontend sends X-Session-Token. Only the shell-initiated flow knows the
        token, so a random local process or malicious web page on the fixed port
        is rejected. /health + /system/info are exempt — the shell needs a
        token-less handshake to identify the backend before it can present one.
        Registered before CORS/logging so 401s still carry CORS + X-Request-ID.
        """
        token = settings.session_token
        if token is not None:
            exempt = (f"{settings.api_prefix}/health", f"{settings.api_prefix}/system/info")
            if request.url.path not in exempt and request.headers.get("X-Session-Token") != token:
                logger.warning("local session auth rejected %s %s", request.method, request.url.path)
                return _error_response(
                    request,
                    status_code=401,
                    code="UNAUTHORIZED",
                    message="Missing or invalid local session token.",
                )
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_logging(request: Request, call_next):
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
        logger.warning(
            "studio error %s on %s %s: %s",
            exc.code,
            request.method,
            request.url.path,
            exc.message,
        )
        return _error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """422 envelope (P1-E4-T01). Sanitized: never echo the raw input body or
        non-JSON-serializable ctx (could contain secrets or whole source_text)."""
        details = []
        for err in exc.errors():
            loc = [str(part) for part in err.get("loc", [])]
            details.append({"loc": loc, "type": err.get("type"), "msg": err.get("msg")})
        logger.warning("validation error on %s %s: %s", request.method, request.url.path, details)
        return _error_response(
            request,
            status_code=422,
            code="VALIDATION_ERROR",
            message="Request validation failed.",
            details={"errors": details},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """HTTP-level errors (unknown route 404, method not allowed 405, ...) use the
        same envelope (P1-E4-T01)."""
        code = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            409: "CONFLICT",
        }.get(exc.status_code, "HTTP_ERROR")
        message = str(exc.detail) or "HTTP error."
        logger.warning("http error %s on %s %s: %s", exc.status_code, request.method, request.url.path, message)
        return _error_response(request, status_code=exc.status_code, code=code, message=message)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Last-resort 500 envelope (P1-E4-T01): full detail is logged server-side
        only — the response never leaks stacks, absolute paths or secrets."""
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return _error_response(
            request,
            status_code=500,
            code="INTERNAL_ERROR",
            message="Internal server error.",
        )

    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
