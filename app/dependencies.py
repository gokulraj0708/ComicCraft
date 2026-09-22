"""FastAPI dependencies."""
from fastapi import Request

from app.services.comic_service import ComicService


def get_comic_service(request: Request) -> ComicService:
    return request.app.state.comic_service
