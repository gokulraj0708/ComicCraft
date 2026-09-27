"""Pluggable comic-panel image generation."""
from __future__ import annotations

import hashlib
import logging
import random
import textwrap
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageDraw, ImageFont

from app.config import BASE_DIR, Settings
from app.exceptions import ConfigurationError, GenerationError
from app.schemas import ScriptPanel

logger = logging.getLogger(__name__)
FONT_DIR = BASE_DIR / "app" / "static" / "fonts"


@dataclass
class GeneratedImage:
    path: Path
    provider: str
    warning: str | None = None


class ImageProvider(Protocol):
    name: str

    def generate(self, prompt: str, destination: Path, seed: int, panel: ScriptPanel) -> None: ...


class PlaceholderImageProvider:
    """Produces attractive deterministic panel art for offline/demo operation."""

    name = "placeholder"

    def __init__(self, settings: Settings) -> None:
        self.width = settings.image_width
        self.height = settings.image_height
        self.regular = FONT_DIR / "DejaVuSans.ttf"
        self.bold = FONT_DIR / "DejaVuSans-Bold.ttf"

    def generate(self, prompt: str, destination: Path, seed: int, panel: ScriptPanel) -> None:
        rng = random.Random(seed)
        palettes = [
            ((16, 24, 48), (47, 201, 191), (250, 184, 73)),
            ((43, 24, 68), (237, 99, 142), (250, 211, 94)),
            ((18, 52, 62), (91, 192, 235), (255, 127, 80)),
            ((52, 31, 18), (241, 146, 50), (255, 226, 138)),
            ((17, 47, 34), (105, 210, 140), (239, 111, 108)),
        ]
        background, accent, highlight = palettes[(panel.panel_number - 1) % len(palettes)]
        image = Image.new("RGB", (self.width, self.height), background)
        draw = ImageDraw.Draw(image)

        # Gradient sky/background.
        for y in range(self.height):
            factor = y / max(1, self.height - 1)
            color = tuple(
                int(background[i] * (1 - factor * 0.45) + accent[i] * factor * 0.45)
                for i in range(3)
            )
            draw.line((0, y, self.width, y), fill=color)

        # Halftone dots and energetic comic rays.
        for _ in range(160):
            radius = rng.randint(2, 8)
            x, y = rng.randrange(self.width), rng.randrange(self.height)
            dot = tuple(min(255, c + 25) for c in accent)
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=dot)
        center = (self.width // 2, int(self.height * 0.42))
        for _angle_index in range(18):
            x = rng.choice([0, self.width])
            y = rng.randrange(self.height)
            draw.line((*center, x, y), fill=highlight, width=3)

        # Stylized hero silhouette to make demo output visibly panel-like.
        hero_x = int(self.width * (0.28 + 0.1 * ((panel.panel_number - 1) % 3)))
        hero_y = int(self.height * 0.52)
        head_r = int(self.width * 0.07)
        outline_width = max(4, self.width // 100)
        draw.ellipse(
            (hero_x - head_r, hero_y - 2 * head_r, hero_x + head_r, hero_y),
            fill=(244, 196, 157),
            outline=(10, 13, 24),
            width=outline_width,
        )
        draw.rounded_rectangle(
            (hero_x - int(self.width * 0.08), hero_y, hero_x + int(self.width * 0.09), hero_y + int(self.height * 0.24)),
            radius=18,
            fill=(24, 155, 166),
            outline=(10, 13, 24),
            width=outline_width,
        )
        draw.polygon(
            [
                (hero_x - int(self.width * 0.08), hero_y + 15),
                (hero_x + int(self.width * 0.1), hero_y + int(self.height * 0.1)),
                (hero_x + int(self.width * 0.08), hero_y + int(self.height * 0.14)),
            ],
            fill=(240, 169, 46),
        )

        # White caption card inside the art (not pretending to be AI imagery).
        margin = int(self.width * 0.055)
        card_top = int(self.height * 0.68)
        draw.rounded_rectangle(
            (margin, card_top, self.width - margin, self.height - margin),
            radius=22,
            fill=(249, 247, 239),
            outline=(12, 15, 27),
            width=outline_width,
        )
        number_font = ImageFont.truetype(str(self.bold), max(24, self.width // 16))
        title_font = ImageFont.truetype(str(self.bold), max(22, self.width // 25))
        body_font = ImageFont.truetype(str(self.regular), max(18, self.width // 35))
        badge = f"{panel.panel_number:02d}"
        draw.rounded_rectangle(
            (margin + 18, card_top + 18, margin + 105, card_top + 98),
            radius=15,
            fill=highlight,
            outline=(12, 15, 27),
            width=3,
        )
        draw.text((margin + 31, card_top + 21), badge, font=number_font, fill=(12, 15, 27))
        draw.text((margin + 125, card_top + 20), panel.title[:34], font=title_font, fill=(12, 15, 27))
        wrapped = textwrap.wrap(panel.scene_description, width=62)[:3]
        draw.multiline_text(
            (margin + 125, card_top + 75),
            "\n".join(wrapped),
            font=body_font,
            fill=(53, 57, 69),
            spacing=8,
        )

        # Heavy comic frame.
        draw.rectangle(
            (8, 8, self.width - 9, self.height - 9),
            outline=(8, 10, 18),
            width=max(8, self.width // 70),
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, format="PNG", optimize=True)


class HuggingFaceImageProvider:
    name = "huggingface"

    def __init__(self, settings: Settings) -> None:
        if not settings.huggingface_token:
            raise ConfigurationError(
                "HF_TOKEN is required for IMAGE_PROVIDER=huggingface. Add it to .env."
            )
        try:
            from huggingface_hub import InferenceClient
        except ImportError as exc:  # pragma: no cover
            raise ConfigurationError("Install the huggingface-hub package") from exc

        kwargs: dict[str, object] = {
            "api_key": settings.huggingface_token,
            "timeout": settings.hf_timeout_seconds,
        }
        if settings.hf_provider:
            kwargs["provider"] = settings.hf_provider
        self.client = InferenceClient(**kwargs)
        self.model = settings.hf_model
        self.width = settings.image_width
        self.height = settings.image_height

    def generate(self, prompt: str, destination: Path, seed: int, panel: ScriptPanel) -> None:
        try:
            image = self.client.text_to_image(
                prompt,
                negative_prompt=(
                    "words, text, letters, speech bubbles, watermark, logo, blurry, low resolution, "
                    "extra fingers, duplicate character, inconsistent clothing"
                ),
                width=self.width,
                height=self.height,
                num_inference_steps=28,
                guidance_scale=7.0,
                seed=seed,
                model=self.model,
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            image.convert("RGB").save(destination, format="PNG", optimize=True)
        except Exception as exc:
            raise GenerationError(f"Hugging Face image generation failed: {exc}") from exc


class DiffusersImageProvider:
    """Lazy local Stable Diffusion provider; loaded only when selected."""

    name = "diffusers"
    _load_lock = threading.Lock()

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._pipeline = None
        self._torch = None
        self._device = "cpu"

    def _load(self) -> None:
        if self._pipeline is not None:
            return
        with self._load_lock:
            if self._pipeline is not None:
                return
            try:
                import torch
                from diffusers import AutoPipelineForText2Image
            except ImportError as exc:
                raise ConfigurationError(
                    "Local image generation packages are missing. Run: "
                    "pip install -r requirements-local-diffusion.txt"
                ) from exc

            requested = self.settings.local_sd_device
            if requested == "auto":
                if torch.cuda.is_available():
                    device = "cuda"
                elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                    device = "mps"
                else:
                    device = "cpu"
            else:
                device = requested
            dtype = torch.float16 if device in {"cuda", "mps"} else torch.float32
            try:
                pipeline = AutoPipelineForText2Image.from_pretrained(
                    self.settings.local_sd_model,
                    torch_dtype=dtype,
                    use_safetensors=True,
                )
                pipeline = pipeline.to(device)
                pipeline.enable_attention_slicing()
            except Exception as exc:
                raise ConfigurationError(f"Could not load local diffusion model: {exc}") from exc
            self._pipeline = pipeline
            self._torch = torch
            self._device = device

    def generate(self, prompt: str, destination: Path, seed: int, panel: ScriptPanel) -> None:
        self._load()
        try:
            generator_device = "cpu" if self._device == "mps" else self._device
            generator = self._torch.Generator(device=generator_device).manual_seed(seed)
            result = self._pipeline(
                prompt=prompt,
                negative_prompt=(
                    "text, caption, watermark, logo, blurry, deformed hands, duplicate person, "
                    "inconsistent costume, low quality"
                ),
                width=self.settings.image_width,
                height=self.settings.image_height,
                num_inference_steps=self.settings.local_sd_steps,
                guidance_scale=self.settings.local_sd_guidance,
                generator=generator,
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            result.images[0].convert("RGB").save(destination, format="PNG", optimize=True)
        except Exception as exc:
            raise GenerationError(f"Local Stable Diffusion generation failed: {exc}") from exc


class ResilientImageService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.fallback = PlaceholderImageProvider(settings)
        self.primary = self._build_primary(settings)

    @staticmethod
    def _build_primary(settings: Settings) -> ImageProvider:
        if settings.image_provider == "placeholder":
            return PlaceholderImageProvider(settings)
        if settings.image_provider == "huggingface":
            return HuggingFaceImageProvider(settings)
        if settings.image_provider == "diffusers":
            return DiffusersImageProvider(settings)
        raise ConfigurationError(f"Unknown image provider: {settings.image_provider}")

    def generate_panel(self, panel: ScriptPanel, destination: Path, comic_id: str) -> GeneratedImage:
        seed_material = f"{comic_id}:{panel.panel_number}:{panel.image_prompt}".encode()
        seed = int(hashlib.sha256(seed_material).hexdigest()[:8], 16)
        try:
            self.primary.generate(panel.image_prompt, destination, seed, panel)
            return GeneratedImage(path=destination, provider=self.primary.name)
        except Exception as exc:
            if self.primary.name == "placeholder" or not self.settings.allow_image_fallback:
                raise
            logger.warning("Panel %s image fallback: %s", panel.panel_number, exc)
            self.fallback.generate(panel.image_prompt, destination, seed, panel)
            return GeneratedImage(
                path=destination,
                provider=self.fallback.name,
                warning=f"Panel {panel.panel_number}: {self.primary.name} failed; placeholder used ({exc})",
            )

    def generate_test_image(self, prompt: str, destination_dir: Path) -> GeneratedImage:
        panel = ScriptPanel(
            panel_number=1,
            title="Image Test",
            scene_description=prompt[:500],
            caption="Provider test",
            narration="Generated by the configured image provider.",
            dialogue=[],
            image_prompt=prompt,
        )
        destination = destination_dir / f"test-{uuid.uuid4().hex}.png"
        return self.generate_panel(panel, destination, uuid.uuid4().hex)
