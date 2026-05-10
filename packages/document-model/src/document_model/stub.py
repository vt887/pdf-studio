from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from .schema import DocumentModel, DocumentQA, ImageAsset, LayoutBlock, PageModel, PageQA, TextLine, Word


def _read_image_size(image_path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(image_path) as image:
        return image.size


@dataclass(slots=True)
class StubPageInput:
    page_number: int
    width_px: int
    height_px: int
    width_pt: float
    height_pt: float
    dpi: int
    original_image_path: str
    normalized_image_path: str
    rotation: float = 0.0


def build_stub_document_model_from_pages(
    source_path: str | Path,
    pages: list[StubPageInput],
    output_pdf_path: str | Path | None = None,
    document_id: str | None = None,
) -> DocumentModel:
    source_path = Path(source_path)
    doc_id = document_id or uuid.uuid4().hex
    page_models: list[PageModel] = []
    for page_input in pages:
        page_id = uuid.uuid4().hex
        image_block_id = uuid.uuid4().hex
        text_block_id = uuid.uuid4().hex
        line_id = uuid.uuid4().hex
        stub_text = f"Page {page_input.page_number}"
        words = [
            Word(
                id=uuid.uuid4().hex,
                line_id=line_id,
                text=token,
                x=36 + index * 52,
                y=36,
                w=48,
                h=18,
                confidence=1.0,
            )
            for index, token in enumerate(stub_text.split())
        ]
        text_line = TextLine(
            id=line_id,
            block_id=text_block_id,
            page_id=page_id,
            text=stub_text,
            x=36,
            y=36,
            w=max(page_input.width_pt - 72, 120),
            h=24,
            baseline_y=52,
            font_family="sans-serif",
            font_size=14,
            font_weight="regular",
            font_style="roman",
            ocr_confidence=1.0,
            font_confidence=0.5,
            review_status="approved",
        )
        page_models.append(
            PageModel(
                id=page_id,
                page_number=page_input.page_number,
                width_px=page_input.width_px,
                height_px=page_input.height_px,
                width_pt=page_input.width_pt,
                height_pt=page_input.height_pt,
                dpi=page_input.dpi,
                rotation=page_input.rotation,
                original_image_path=page_input.original_image_path,
                normalized_image_path=page_input.normalized_image_path,
                blocks=[
                    LayoutBlock(
                        id=image_block_id,
                        page_id=page_id,
                        block_type="image",
                        x=0,
                        y=0,
                        w=page_input.width_pt,
                        h=page_input.height_pt,
                        reading_order=0,
                        confidence=1.0,
                        review_status="approved",
                    ),
                    LayoutBlock(
                        id=text_block_id,
                        page_id=page_id,
                        block_type="text",
                        x=text_line.x,
                        y=text_line.y,
                        w=text_line.w,
                        h=text_line.h,
                        reading_order=1,
                        confidence=1.0,
                        review_status="approved",
                    ),
                ],
                text_lines=[text_line],
                words=words,
                assets=[
                    ImageAsset(
                        id=uuid.uuid4().hex,
                        page_id=page_id,
                        source_block_id=image_block_id,
                        asset_path=page_input.normalized_image_path,
                        x=0,
                        y=0,
                        w=page_input.width_pt,
                        h=page_input.height_pt,
                        asset_type="page-image",
                        confidence=1.0,
                        review_status="approved",
                    )
                ],
                qa=PageQA(notes={"mode": "stub", "status": "not_run"}),
            )
        )
    return DocumentModel(
        id=doc_id,
        source_file=str(source_path),
        output_pdf_path=str(output_pdf_path) if output_pdf_path else None,
        status="draft",
        pages=page_models,
        qa=DocumentQA(notes={"mode": "stub", "status": "not_run"}),
    )


def build_stub_document_model(
    source_path: str | Path,
    normalized_image_path: str | Path,
    output_pdf_path: str | Path | None = None,
    document_id: str | None = None,
) -> DocumentModel:
    source_path = Path(source_path)
    normalized_image_path = Path(normalized_image_path)
    doc_id = document_id or uuid.uuid4().hex
    width_px, height_px = _read_image_size(normalized_image_path)
    dpi = 300
    width_pt = width_px * 72.0 / dpi
    height_pt = height_px * 72.0 / dpi

    return build_stub_document_model_from_pages(
        source_path=source_path,
        pages=[
            StubPageInput(
                page_number=1,
                width_px=width_px,
                height_px=height_px,
                width_pt=width_pt,
                height_pt=height_pt,
                dpi=dpi,
                original_image_path=str(source_path),
                normalized_image_path=str(normalized_image_path),
            )
        ],
        output_pdf_path=output_pdf_path,
        document_id=doc_id,
    )
