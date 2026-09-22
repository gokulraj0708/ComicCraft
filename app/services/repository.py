"""Safe filesystem persistence for generated comics."""
from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path

from app.exceptions import ComicNotFoundError
from app.schemas import ComicResult

_COMIC_ID = re.compile(r"^[a-f0-9]{32}$")


class ComicRepository:
    def __init__(self, storage_dir: Path) -> None:
        self.root = storage_dir / "comics"
        self.root.mkdir(parents=True, exist_ok=True)

    def create_workspace(self) -> tuple[str, Path]:
        comic_id = uuid.uuid4().hex
        path = self.root / comic_id
        (path / "panels").mkdir(parents=True, exist_ok=False)
        return comic_id, path

    def workspace(self, comic_id: str) -> Path:
        if not _COMIC_ID.fullmatch(comic_id):
            raise ComicNotFoundError("Comic not found")
        path = self.root / comic_id
        if not path.is_dir():
            raise ComicNotFoundError("Comic not found")
        return path

    def save(self, result: ComicResult) -> None:
        workspace = self.workspace(result.comic_id)
        target = workspace / "comic.json"
        temporary = workspace / "comic.json.tmp"
        temporary.write_text(
            json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(target)

    def load(self, comic_id: str) -> ComicResult:
        manifest = self.workspace(comic_id) / "comic.json"
        if not manifest.is_file():
            raise ComicNotFoundError("Comic metadata not found")
        return ComicResult.model_validate_json(manifest.read_text(encoding="utf-8"))

    def pdf_path(self, comic_id: str) -> Path:
        path = self.workspace(comic_id) / "comic.pdf"
        if not path.is_file():
            raise ComicNotFoundError("Comic PDF not found")
        return path

    def delete_workspace(self, comic_id: str) -> None:
        if _COMIC_ID.fullmatch(comic_id):
            shutil.rmtree(self.root / comic_id, ignore_errors=True)
