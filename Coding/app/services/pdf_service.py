"""PDF export service using fpdf2 and bundled Unicode fonts."""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

from app.config import BASE_DIR
from app.schemas import ComicPrompt, ComicScript

FONT_DIR = BASE_DIR / "app" / "static" / "fonts"


class ComicPDF(FPDF):
    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("DejaVu", size=8)
        self.set_text_color(110, 114, 126)
        self.cell(0, 6, f"ComicCraft  •  Page {self.page_no()}", align="C")


class PDFService:
    def __init__(self) -> None:
        self.regular_font = FONT_DIR / "DejaVuSans.ttf"
        self.bold_font = FONT_DIR / "DejaVuSans-Bold.ttf"

    def build(
        self,
        script: ComicScript,
        prompt: ComicPrompt,
        image_paths: list[Path],
        destination: Path,
    ) -> Path:
        if len(image_paths) != len(script.panels):
            raise ValueError("Every panel must have an image before PDF export")

        pdf = ComicPDF(format="A4", unit="mm")
        pdf.set_auto_page_break(auto=True, margin=18)
        pdf.add_font("DejaVu", style="", fname=str(self.regular_font))
        pdf.add_font("DejaVu", style="B", fname=str(self.bold_font))
        pdf.set_title(script.title)
        pdf.set_author("ComicCraft")
        pdf.set_creator("ComicCraft AI Comic Story Creator")

        self._add_cover(pdf, script, prompt)
        for panel, image_path in zip(script.panels, image_paths, strict=True):
            self._add_panel(pdf, panel, image_path)

        destination.parent.mkdir(parents=True, exist_ok=True)
        pdf.output(str(destination))
        return destination

    def _add_cover(self, pdf: ComicPDF, script: ComicScript, prompt: ComicPrompt) -> None:
        pdf.add_page()
        pdf.set_fill_color(18, 27, 47)
        pdf.rect(0, 0, 210, 297, style="F")
        pdf.set_fill_color(45, 201, 190)
        pdf.rect(0, 0, 13, 297, style="F")
        pdf.set_xy(27, 54)
        pdf.set_text_color(246, 184, 70)
        pdf.set_font("DejaVu", "B", 13)
        pdf.cell(0, 10, "AN AI-ASSISTED COMIC", new_x="LMARGIN", new_y="NEXT")
        pdf.set_x(27)
        pdf.set_text_color(250, 250, 246)
        pdf.set_font("DejaVu", "B", 27)
        pdf.multi_cell(156, 13, script.title)
        pdf.ln(8)
        pdf.set_x(27)
        pdf.set_font("DejaVu", size=12)
        pdf.set_text_color(205, 216, 224)
        pdf.multi_cell(156, 7, f"Starring {prompt.character_name} • {prompt.tone} • {prompt.art_style}")
        pdf.ln(18)
        pdf.set_x(27)
        pdf.set_font("DejaVu", "B", 11)
        pdf.set_text_color(45, 201, 190)
        pdf.cell(0, 8, "STORY IDEA", new_x="LMARGIN", new_y="NEXT")
        pdf.set_x(27)
        pdf.set_font("DejaVu", size=11)
        pdf.set_text_color(238, 240, 242)
        pdf.multi_cell(156, 7, prompt.story_prompt)
        pdf.set_y(253)
        pdf.set_x(27)
        pdf.set_text_color(155, 170, 182)
        pdf.set_font("DejaVu", size=9)
        pdf.multi_cell(156, 6, "Created with ComicCraft. Review AI-generated content before publishing or sharing.")

    def _add_panel(self, pdf: ComicPDF, panel, image_path: Path) -> None:
        pdf.add_page()
        pdf.set_text_color(18, 27, 47)
        pdf.set_font("DejaVu", "B", 17)
        pdf.multi_cell(0, 9, f"Panel {panel.panel_number}: {panel.title}")
        pdf.ln(2)

        # Preserve the image aspect ratio within a 180 x 145 mm box.
        from PIL import Image

        with Image.open(image_path) as image:
            width_px, height_px = image.size
        max_width, max_height = 180.0, 145.0
        scale = min(max_width / width_px, max_height / height_px)
        width_mm, height_mm = width_px * scale, height_px * scale
        x = (210 - width_mm) / 2
        pdf.image(str(image_path), x=x, y=pdf.get_y(), w=width_mm, h=height_mm)
        pdf.set_y(pdf.get_y() + height_mm + 6)

        pdf.set_font("DejaVu", "B", 10)
        pdf.set_text_color(28, 141, 137)
        pdf.cell(0, 6, panel.caption, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("DejaVu", size=10)
        pdf.set_text_color(62, 68, 82)
        pdf.multi_cell(0, 5.5, panel.narration)
        if panel.dialogue:
            pdf.ln(1)
            for line in panel.dialogue:
                pdf.set_font("DejaVu", "B", 9.5)
                pdf.set_text_color(18, 27, 47)
                pdf.write(5.5, f"{line.speaker}: ")
                pdf.set_font("DejaVu", size=9.5)
                pdf.write(5.5, line.text)
                pdf.ln(6)
