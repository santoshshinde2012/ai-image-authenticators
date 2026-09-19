"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ai_image_authenticator.container import AppContainer, create_container
from ai_image_authenticator.core.config import Settings, get_settings
from ai_image_authenticator.core.logging import configure_logging
from ai_image_authenticator.interfaces.http.middleware import (
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
)
from ai_image_authenticator.interfaces.http.v1.routes import router as v1_router


def resolve_frontend_dist(settings: Settings) -> Path | None:
    """Locate SPA build for both src-layout and installed/Docker layouts."""
    if settings.frontend_dist:
        path = Path(settings.frontend_dist)
        if path.is_dir() and (path / "index.html").exists():
            return path
        return None
    # Editable / src: apps/api/src/ai_image_authenticator/main.py → repo root
    src_layout = Path(__file__).resolve().parents[4] / "apps" / "web" / "dist"
    if src_layout.is_dir() and (src_layout / "index.html").exists():
        return src_layout
    cwd_dist = Path.cwd() / "apps" / "web" / "dist"
    if cwd_dist.is_dir() and (cwd_dist / "index.html").exists():
        return cwd_dist
    return None


def _error_body(request: Request, status_code: int, detail: object) -> dict:
    request_id = getattr(request.state, "request_id", None)
    return {
        "error": True,
        "status_code": status_code,
        "detail": detail,
        "request_id": request_id,
    }


def create_app(
    container: AppContainer | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    cfg = settings or (container.settings if container else get_settings())
    configure_logging(cfg.log_level)
    box = container or create_container(settings=cfg)

    app = FastAPI(
        title="AI Image Authenticator",
        description="Local multi-signal forensic detector for AI-generated imagery",
        version="1.0.0",
    )
    app.state.analysis_service = box.analysis_service
    app.state.artifact_store = box.artifact_store
    app.state.analyzer_ids = box.analyzer_ids
    app.state.settings = box.settings

    # Middleware order: last added runs first on request.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(request, exc.status_code, exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_error_body(request, 422, exc.errors()),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=_error_body(request, 500, "Internal server error"),
        )

    # Versioned API routes BEFORE StaticFiles so /api/* is never swallowed by SPA mount.
    app.include_router(v1_router)

    frontend_dist = resolve_frontend_dist(cfg)
    if frontend_dist is not None:
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

    return app


app = create_app()


def run() -> None:
    import uvicorn

    cfg = get_settings()
    uvicorn.run(
        "ai_image_authenticator.main:app",
        host=cfg.host,
        port=cfg.port,
        reload=False,
        log_level=cfg.log_level.lower(),
    )


if __name__ == "__main__":
    run()
