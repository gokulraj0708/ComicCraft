"""ComicCraft FastAPI application factory and ASGI entry point."""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR, Settings, get_settings
from app.exceptions import ComicCraftError
from app.routes import router
from app.services.comic_service import ComicService

logger = logging.getLogger("comiccraft")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.prepare_directories()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info(
            "Starting %s %s (AI=%s, images=%s)",
            settings.app_name,
            settings.app_version,
            settings.resolved_ai_mode,
            settings.image_provider,
        )
        yield
        logger.info("Stopping %s", settings.app_name)

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Generate structured comic stories, panel images, previews, and downloadable PDFs. "
            "Use POST /api/v1/comics or the browser interface."
        ),
        debug=settings.debug,
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.state.templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")
    application.state.comic_service = ComicService(settings)

    application.mount(
        "/static",
        StaticFiles(directory=BASE_DIR / "app" / "static"),
        name="static",
    )
    application.mount(
        "/media",
        StaticFiles(directory=settings.storage_dir),
        name="media",
    )

    if settings.cors_origin_list:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )

    @application.middleware("http")
    async def security_and_timing_headers(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Process-Time"] = f"{time.perf_counter() - started:.4f}"
        return response

    @application.exception_handler(ComicCraftError)
    async def comiccraft_error(request: Request, exc: ComicCraftError):
        if request.url.path.startswith("/api/") or "application/json" in request.headers.get("accept", ""):
            return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})
        return application.state.templates.TemplateResponse(
            request=request,
            name="error.html",
            context={"message": str(exc), "status_code": exc.status_code},
            status_code=exc.status_code,
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        if request.url.path.startswith("/api/") or request.url.path == "/generate-comic/json":
            return JSONResponse(status_code=422, content={"detail": exc.errors()})
        messages = "; ".join(
            f"{' → '.join(str(part) for part in item['loc'][1:])}: {item['msg']}"
            for item in exc.errors()
        )
        return application.state.templates.TemplateResponse(
            request=request,
            name="error.html",
            context={"message": messages, "status_code": 422},
            status_code=422,
        )

    application.include_router(router)
    return application


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logging.getLogger("fontTools").setLevel(logging.WARNING)
app = create_app()
