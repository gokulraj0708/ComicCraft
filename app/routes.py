"""Web pages, compatibility routes, and versioned JSON API."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse

from app.dependencies import get_comic_service
from app.schemas import ComicPrompt, ComicResult, HealthResponse
from app.services.comic_service import ComicService

router = APIRouter()
ComicServiceDep = Annotated[ComicService, Depends(get_comic_service)]


def _templates(request: Request):
    return request.app.state.templates


@router.get("/", response_class=HTMLResponse, name="home")
async def home(request: Request):
    settings = request.app.state.settings
    return _templates(request).TemplateResponse(
        request=request,
        name="index.html",
        context={
            "settings": settings,
            "defaults": {
                "character_name": "Mira",
                "setting": "an enchanted forest",
                "tone": "Adventurous",
                "art_style": "Modern comic book",
                "panel_count": settings.default_panel_count,
            },
        },
    )


@router.post("/generate", response_class=HTMLResponse, name="generate_web")
async def generate_web(
    request: Request,
    story_prompt: Annotated[str, Form(min_length=10, max_length=1500)],
    character_name: Annotated[str, Form(min_length=1, max_length=80)],
    setting: Annotated[str, Form(min_length=1, max_length=100)],
    tone: Annotated[str, Form(min_length=1, max_length=50)],
    art_style: Annotated[str, Form(min_length=1, max_length=80)],
    service: ComicServiceDep,
    panel_count: Annotated[int, Form(ge=3, le=8)] = 5,
):
    payload = ComicPrompt(
        story_prompt=story_prompt,
        character_name=character_name,
        setting=setting,
        tone=tone,
        art_style=art_style,
        panel_count=panel_count,
    )
    result = await run_in_threadpool(service.generate, payload)
    return _templates(request).TemplateResponse(
        request=request,
        name="comic_preview.html",
        context={"comic": result},
    )


@router.get("/comics/{comic_id}", response_class=HTMLResponse, name="comic_preview")
async def comic_preview(
    request: Request,
    comic_id: str,
    service: ComicServiceDep,
):
    comic = await run_in_threadpool(service.get, comic_id)
    return _templates(request).TemplateResponse(
        request=request,
        name="comic_preview.html",
        context={"comic": comic},
    )


@router.get("/download/{comic_id}", name="download_comic")
async def download_comic(
    comic_id: str,
    service: ComicServiceDep,
):
    comic = await run_in_threadpool(service.get, comic_id)
    path = await run_in_threadpool(service.pdf_path, comic_id)
    safe_title = "".join(
        char if char.isalnum() or char in "-_" else "-" for char in comic.title
    ).strip("-")[:70]
    filename = f"{safe_title or 'comic'}.pdf"
    return FileResponse(path, media_type="application/pdf", filename=filename)


@router.get("/export-success", response_class=HTMLResponse, name="export_success")
async def export_success(
    request: Request,
    comic_id: Annotated[str, Query(min_length=32, max_length=32)],
    service: ComicServiceDep,
):
    comic = await run_in_threadpool(service.get, comic_id)
    return _templates(request).TemplateResponse(
        request=request,
        name="export_success.html",
        context={"comic": comic},
    )


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=settings.app_version,
        ai_mode=settings.resolved_ai_mode,
        image_provider=settings.image_provider,
    )


@router.get("/test-image", tags=["development"])
async def test_image(
    request: Request,
    service: ComicServiceDep,
    prompt: Annotated[str, Query(min_length=3, max_length=1000)] = (
        "A courageous explorer at sunset, dynamic modern comic-book illustration"
    ),
):
    settings = request.app.state.settings
    if not settings.enable_test_image_endpoint:
        raise HTTPException(status_code=404, detail="Image test endpoint is disabled")
    image = await run_in_threadpool(service.test_image, prompt)
    return {
        "message": "Image generated successfully",
        "provider": image.provider,
        "warning": image.warning,
        "image_url": f"/media/test-images/{image.path.name}",
    }


# Compatibility endpoint matching the supplied project documentation.
@router.post(
    "/generate-comic/json",
    response_model=ComicResult,
    tags=["comics"],
    name="generate_comic_json_compat",
)
async def generate_comic_json_compat(
    payload: ComicPrompt,
    service: ComicServiceDep,
) -> ComicResult:
    return await run_in_threadpool(service.generate, payload)


@router.post(
    "/api/v1/comics",
    response_model=ComicResult,
    status_code=201,
    tags=["comics"],
    name="api_create_comic",
)
async def api_create_comic(
    payload: ComicPrompt,
    service: ComicServiceDep,
) -> ComicResult:
    return await run_in_threadpool(service.generate, payload)


@router.get(
    "/api/v1/comics/{comic_id}",
    response_model=ComicResult,
    tags=["comics"],
    name="api_get_comic",
)
async def api_get_comic(
    comic_id: str,
    service: ComicServiceDep,
) -> ComicResult:
    return await run_in_threadpool(service.get, comic_id)
