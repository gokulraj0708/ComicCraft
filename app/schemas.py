"""Pydantic request, AI-output, and API-response models."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class ComicPrompt(BaseModel):
    """User-supplied comic preferences."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)

    story_prompt: str = Field(
        min_length=10,
        max_length=1500,
        validation_alias=AliasChoices("story_prompt", "prompt"),
        description="The core story idea.",
    )
    character_name: str = Field(min_length=1, max_length=80)
    setting: str = Field(min_length=1, max_length=100)
    tone: str = Field(min_length=1, max_length=50)
    art_style: str = Field(
        min_length=1,
        max_length=80,
        validation_alias=AliasChoices("art_style", "style"),
    )
    panel_count: int = Field(default=5, ge=3, le=8)

    @field_validator("story_prompt", "character_name", "setting", "tone", "art_style")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        if any(ord(char) < 32 and char not in "\n\t" for char in value):
            raise ValueError("Control characters are not allowed")
        return value


class OutlinePanel(BaseModel):
    panel_number: int = Field(ge=1, le=12)
    title: ShortText
    scene_description: LongText
    image_prompt: LongText


class ComicOutline(BaseModel):
    title: ShortText
    character_bible: LongText = Field(
        description="Stable visual description of the main character, including clothes and colors."
    )
    panels: list[OutlinePanel] = Field(min_length=3, max_length=12)

    def validate_panel_sequence(self, expected_count: int) -> None:
        if len(self.panels) != expected_count:
            raise ValueError(f"Expected {expected_count} panels, received {len(self.panels)}")
        actual = [panel.panel_number for panel in self.panels]
        expected = list(range(1, expected_count + 1))
        if actual != expected:
            raise ValueError(f"Panel numbers must be sequential: {expected}")


class DialogueLine(BaseModel):
    speaker: ShortText
    text: LongText


class ScriptPanel(BaseModel):
    panel_number: int = Field(ge=1, le=12)
    title: ShortText
    scene_description: LongText
    caption: LongText
    narration: LongText
    dialogue: list[DialogueLine] = Field(default_factory=list, max_length=8)
    image_prompt: LongText


class ComicScript(BaseModel):
    title: ShortText
    character_bible: LongText
    panels: list[ScriptPanel] = Field(min_length=3, max_length=12)

    def validate_against(self, prompt: ComicPrompt) -> None:
        if len(self.panels) != prompt.panel_count:
            raise ValueError(
                f"Expected {prompt.panel_count} script panels, received {len(self.panels)}"
            )
        expected = list(range(1, prompt.panel_count + 1))
        actual = [panel.panel_number for panel in self.panels]
        if actual != expected:
            raise ValueError(f"Script panel numbers must be sequential: {expected}")


class ComicPanel(BaseModel):
    panel_number: int
    title: str
    scene_description: str
    caption: str
    narration: str
    dialogue: list[DialogueLine]
    image_prompt: str
    image_url: str
    image_provider: str


class ProviderInfo(BaseModel):
    text_provider: str
    outline_model: str
    story_model: str
    requested_image_provider: str
    image_providers_used: list[str]
    used_fallback: bool = False
    warnings: list[str] = Field(default_factory=list)


class ComicResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comic_id: str
    title: str
    created_at: datetime
    prompt: ComicPrompt
    panels: list[ComicPanel]
    pdf_url: str
    preview_url: str
    provider_info: ProviderInfo

    @model_validator(mode="after")
    def panel_count_matches_request(self) -> ComicResult:
        if len(self.panels) != self.prompt.panel_count:
            raise ValueError("Result panel count does not match the request")
        return self


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    ai_mode: str
    image_provider: str
