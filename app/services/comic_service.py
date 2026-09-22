"""End-to-end comic generation orchestration."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.schemas import ComicPanel, ComicPrompt, ComicResult, ProviderInfo
from app.services.images import ResilientImageService
from app.services.llm import ResilientStoryService
from app.services.pdf_service import PDFService
from app.services.repository import ComicRepository

logger = logging.getLogger(__name__)


class ComicService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.repository = ComicRepository(settings.storage_dir)
        self.story_service = ResilientStoryService(settings)
        self.image_service = ResilientImageService(settings)
        self.pdf_service = PDFService()

    def generate(self, prompt: ComicPrompt) -> ComicResult:
        if prompt.panel_count > self.settings.max_panel_count:
            raise ValueError(f"A maximum of {self.settings.max_panel_count} panels is allowed")
        comic_id, workspace = self.repository.create_workspace()
        try:
            story = self.story_service.generate(prompt)
            image_results = []
            for panel in story.script.panels:
                destination = workspace / "panels" / f"panel-{panel.panel_number}.png"
                image_results.append(
                    self.image_service.generate_panel(panel, destination, comic_id)
                )

            pdf_path = workspace / "comic.pdf"
            self.pdf_service.build(
                story.script,
                prompt,
                [item.path for item in image_results],
                pdf_path,
            )

            warnings = list(story.warnings)
            warnings.extend(item.warning for item in image_results if item.warning)
            image_providers = sorted({item.provider for item in image_results})
            panels = [
                ComicPanel(
                    panel_number=panel.panel_number,
                    title=panel.title,
                    scene_description=panel.scene_description,
                    caption=panel.caption,
                    narration=panel.narration,
                    dialogue=panel.dialogue,
                    image_prompt=panel.image_prompt,
                    image_url=f"/media/comics/{comic_id}/panels/panel-{panel.panel_number}.png",
                    image_provider=image_result.provider,
                )
                for panel, image_result in zip(story.script.panels, image_results, strict=True)
            ]
            result = ComicResult(
                comic_id=comic_id,
                title=story.script.title,
                created_at=datetime.now(UTC),
                prompt=prompt,
                panels=panels,
                pdf_url=f"/download/{comic_id}",
                preview_url=f"/comics/{comic_id}",
                provider_info=ProviderInfo(
                    text_provider=story.provider,
                    outline_model=story.outline_model,
                    story_model=story.story_model,
                    requested_image_provider=self.settings.image_provider,
                    image_providers_used=image_providers,
                    used_fallback=story.used_fallback or any(item.warning for item in image_results),
                    warnings=warnings,
                ),
            )
            self.repository.save(result)
            return result
        except Exception:
            logger.exception("Comic generation failed for workspace %s", comic_id)
            if not self.settings.keep_failed_workspaces:
                self.repository.delete_workspace(comic_id)
            raise

    def get(self, comic_id: str) -> ComicResult:
        return self.repository.load(comic_id)

    def pdf_path(self, comic_id: str) -> Path:
        return self.repository.pdf_path(comic_id)

    def test_image(self, prompt: str):
        return self.image_service.generate_test_image(
            prompt,
            self.settings.storage_dir / "test-images",
        )
