from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz
from PIL import Image, ImageOps

from .. import artifacts

TARGET_DPI = 300


class UnsupportedInputError(ValueError):
    pass


@dataclass(slots=True)
class ExtractedPage:
    page_number: int
    width_px: int
    height_px: int
    width_pt: float
    height_pt: float
    dpi: int
    rotation: float
    normalized_image_path: str
    original_image_path: str


def detect_input_type(source_path: str | Path) -> str:
    source_path = Path(source_path)
    header = source_path.read_bytes()[:16]
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(header) >= 3 and header[0:3] == b"\xff\xd8\xff":
        return "jpeg"
    if header.startswith(b"II*\x00") or header.startswith(b"MM\x00*"):
        return "tiff"
    if header.startswith(b"%PDF-"):
        return "pdf"
    raise UnsupportedInputError("Unsupported file type. Supported types: PNG, JPEG, TIFF, PDF.")


def _deskew_placeholder(image: Image.Image) -> Image.Image:
    return image


def _normalize_image(image: Image.Image, contrast: bool) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    image = image.convert("RGB")
    image = _deskew_placeholder(image)
    if contrast:
        image = ImageOps.autocontrast(image)
    return image


def _save_normalized_page(
    image: Image.Image,
    document_root: str | Path,
    page_number: int,
    original_image_path: str,
    rotation: float = 0.0,
) -> ExtractedPage:
    normalized_path = artifacts.normalized_image_path(document_root, page_number)
    normalized_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(normalized_path, format="PNG", dpi=(TARGET_DPI, TARGET_DPI))
    width_px, height_px = image.size
    return ExtractedPage(
        page_number=page_number,
        width_px=width_px,
        height_px=height_px,
        width_pt=width_px * 72.0 / TARGET_DPI,
        height_pt=height_px * 72.0 / TARGET_DPI,
        dpi=TARGET_DPI,
        rotation=rotation,
        normalized_image_path=str(normalized_path),
        original_image_path=original_image_path,
    )


def extract_and_normalize_pages(
    source_path: str | Path,
    document_root: str | Path,
    *,
    normalize_contrast: bool = False,
) -> list[ExtractedPage]:
    source_path = Path(source_path)
    input_type = detect_input_type(source_path)
    pages: list[ExtractedPage] = []

    if input_type in {"png", "jpeg"}:
        with Image.open(source_path) as image:
            normalized = _normalize_image(image, normalize_contrast)
            pages.append(
                _save_normalized_page(normalized, document_root, 1, str(source_path)),
            )
        return pages

    if input_type == "tiff":
        with Image.open(source_path) as image:
            frame_index = 0
            while True:
                image.seek(frame_index)
                normalized = _normalize_image(image, normalize_contrast)
                pages.append(
                    _save_normalized_page(normalized, document_root, frame_index + 1, str(source_path)),
                )
                frame_index += 1
                if frame_index >= getattr(image, "n_frames", frame_index):
                    break
        return pages

    with fitz.open(source_path) as document:
        matrix = fitz.Matrix(TARGET_DPI / 72.0, TARGET_DPI / 72.0)
        for index, page in enumerate(document, start=1):
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
            normalized = _normalize_image(image, normalize_contrast)
            pages.append(
                _save_normalized_page(normalized, document_root, index, str(source_path), rotation=float(page.rotation)),
            )
    return pages
