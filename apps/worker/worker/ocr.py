from __future__ import annotations

import csv
import io
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from document_model import DocumentModel, LayoutBlock, PageModel, PageQA, TextLine, Word


class OcrError(RuntimeError):
    pass


class OcrSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class OcrWord(OcrSchema):
    id: str
    text: str
    x: float
    y: float
    w: float
    h: float
    confidence: float | None = None


class OcrLine(OcrSchema):
    id: str
    text: str
    x: float
    y: float
    w: float
    h: float
    confidence: float | None = None
    words: list[OcrWord] = Field(default_factory=list)


class OcrPageResult(OcrSchema):
    page_number: int
    normalized_artifact: str
    engine: str
    language: str
    width_px: int
    height_px: int
    dpi: int
    lines: list[OcrLine] = Field(default_factory=list)


@runtime_checkable
class OcrEngine(Protocol):
    def recognize_page(self, image_path: Path, page_number: int, dpi: int, language: str) -> OcrPageResult: ...


def px_to_pt(value: float, dpi: int) -> float:
    return value * 72.0 / dpi


def _group_key(row: dict[str, str]) -> tuple[str, str, str]:
    return (row["block_num"], row["par_num"], row["line_num"])


def _row_to_float(row: dict[str, str], key: str) -> float:
    value = row.get(key, "").strip()
    if not value or value == "-1":
        return 0.0
    return float(value)


def _row_to_int(row: dict[str, str], key: str) -> int:
    value = row.get(key, "").strip()
    if not value:
        return 0
    return int(float(value))


def _parse_tesseract_tsv(*, text: str, image_path: Path, page_number: int, dpi: int, language: str) -> OcrPageResult:
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    line_groups: dict[tuple[str, str, str], dict[str, object]] = {}
    order: list[tuple[str, str, str]] = []

    for row in reader:
        if row.get("level") != "5":
            continue
        token = row.get("text", "").strip()
        if not token:
            continue
        key = _group_key(row)
        if key not in line_groups:
            line_groups[key] = {
                "words": [],
                "lefts": [],
                "tops": [],
                "rights": [],
                "bottoms": [],
                "confs": [],
            }
            order.append(key)
        group = line_groups[key]
        left = _row_to_int(row, "left")
        top = _row_to_int(row, "top")
        width = _row_to_int(row, "width")
        height = _row_to_int(row, "height")
        confidence = _row_to_float(row, "conf")
        word = OcrWord(
            id=uuid.uuid4().hex,
            text=token,
            x=left,
            y=top,
            w=width,
            h=height,
            confidence=confidence,
        )
        group["words"].append(word)
        group["lefts"].append(left)
        group["tops"].append(top)
        group["rights"].append(left + width)
        group["bottoms"].append(top + height)
        group["confs"].append(confidence)

    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover - depends on environment
        raise OcrError("Pillow is required to inspect OCR image dimensions.") from exc

    try:
        with Image.open(image_path) as image:
            width_px, height_px = image.size
    except Exception as exc:  # pragma: no cover - depends on image file availability
        raise OcrError(f"Failed to open OCR image: {image_path}") from exc

    lines: list[OcrLine] = []
    for key in order:
        group = line_groups[key]
        words = list(group["words"])
        if not words:
            continue
        lefts = list(group["lefts"])
        tops = list(group["tops"])
        rights = list(group["rights"])
        bottoms = list(group["bottoms"])
        confs = list(group["confs"])
        lines.append(
            OcrLine(
                id=uuid.uuid4().hex,
                text=" ".join(word.text for word in words),
                x=min(lefts),
                y=min(tops),
                w=max(rights) - min(lefts),
                h=max(bottoms) - min(tops),
                confidence=(sum(confs) / len(confs)) if confs else None,
                words=words,
            )
        )

    return OcrPageResult(
        page_number=page_number,
        normalized_artifact=str(image_path),
        engine="tesseract",
        language=language,
        width_px=width_px,
        height_px=height_px,
        dpi=dpi,
        lines=lines,
    )


@dataclass(slots=True)
class TesseractOcrEngine:
    executable: str | None = None

    def __post_init__(self) -> None:
        if self.executable is None:
            self.executable = shutil.which("tesseract")
        if not self.executable:
            raise OcrError("Tesseract executable was not found. Install `tesseract` to use OCR.")

    def recognize_page(self, image_path: Path, page_number: int, dpi: int, language: str) -> OcrPageResult:
        command = [
            self.executable or "tesseract",
            str(image_path),
            "stdout",
            "-l",
            language,
            "--dpi",
            str(dpi),
            "--psm",
            "6",
            "tsv",
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            raise OcrError(f"Tesseract OCR failed for {image_path}: {stderr or completed.returncode}")
        output = completed.stdout.strip()
        if not output:
            return OcrPageResult(
                page_number=page_number,
                normalized_artifact=str(image_path),
                engine="tesseract",
                language=language,
                width_px=0,
                height_px=0,
                dpi=dpi,
                lines=[],
            )
        return _parse_tesseract_tsv(text=output, image_path=image_path, page_number=page_number, dpi=dpi, language=language)


def apply_ocr_result(page: PageModel, ocr_result: OcrPageResult) -> PageModel:
    image_blocks = [block for block in page.blocks if block.block_type == "image"]
    text_lines: list[TextLine] = []
    words: list[Word] = []
    text_blocks: list[LayoutBlock] = []

    for reading_order, line in enumerate(ocr_result.lines):
        line_width_pt = px_to_pt(line.w, ocr_result.dpi)
        line_height_pt = px_to_pt(line.h, ocr_result.dpi)
        line_x_pt = px_to_pt(line.x, ocr_result.dpi)
        line_y_pt = px_to_pt(line.y, ocr_result.dpi)
        font_size = max(6.0, line_height_pt * 0.8)
        line_id = line.id
        block_id = uuid.uuid4().hex
        line_words: list[Word] = []
        for word in line.words:
            line_words.append(
                Word(
                    id=word.id,
                    line_id=line_id,
                    text=word.text,
                    x=px_to_pt(word.x, ocr_result.dpi),
                    y=px_to_pt(word.y, ocr_result.dpi),
                    w=px_to_pt(word.w, ocr_result.dpi),
                    h=px_to_pt(word.h, ocr_result.dpi),
                    confidence=word.confidence,
                )
            )
        words.extend(line_words)
        text_lines.append(
            TextLine(
                id=line_id,
                block_id=block_id,
                page_id=page.id,
                text=line.text,
                x=line_x_pt,
                y=line_y_pt,
                w=line_width_pt,
                h=line_height_pt,
                baseline_y=line_y_pt + line_height_pt * 0.8,
                font_family="sans-serif",
                font_size=font_size,
                font_weight="regular",
                font_style="roman",
                ocr_confidence=line.confidence,
                font_confidence=None,
                review_status="pending",
            )
        )
        text_blocks.append(
            LayoutBlock(
                id=block_id,
                page_id=page.id,
                block_type="text",
                x=line_x_pt,
                y=line_y_pt,
                w=line_width_pt,
                h=line_height_pt,
                reading_order=reading_order,
                confidence=line.confidence,
                review_status="pending",
            )
        )

    page.blocks = [*image_blocks, *text_blocks]
    page.text_lines = text_lines
    page.words = words
    page.qa.ocr_text_found = bool(text_lines)
    page.qa.notes["ocr_text_found"] = bool(text_lines)
    page.qa.notes["ocr_engine"] = ocr_result.engine
    page.qa.notes["ocr_language"] = ocr_result.language
    if not text_lines:
        page.qa.review_status = "pending"
    return page


def apply_ocr_results(document: DocumentModel, ocr_results: list[OcrPageResult]) -> DocumentModel:
    by_page = {page.page_number: page for page in document.pages}
    for ocr_result in ocr_results:
        page = by_page.get(ocr_result.page_number)
        if page is None:
            continue
        apply_ocr_result(page, ocr_result)
    return document
