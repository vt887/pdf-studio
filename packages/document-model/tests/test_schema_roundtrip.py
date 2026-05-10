from __future__ import annotations

from pathlib import Path

from document_model import (
    DocumentModel,
    DocumentQA,
    DocumentReconstructionModel,
    ImageAsset,
    LayoutBlock,
    Link,
    PageModel,
    PageQA,
    TextLine,
    Word,
    load_document_model,
    save_document_model,
)
import pytest


def build_sample_document() -> DocumentModel:
    page_id = "page-1"
    block_id = "block-1"
    line_id = "line-1"
    word_id = "word-1"
    asset_id = "asset-1"
    link_id = "link-1"

    page = PageModel(
        id=page_id,
        page_number=1,
        width_px=2550,
        height_px=3300,
        width_pt=612.0,
        height_pt=792.0,
        dpi=300,
        rotation=0,
        original_image_path="/artifacts/doc-1/source.png",
        normalized_image_path="/artifacts/doc-1/pages/0001.normalized.png",
        blocks=[
            LayoutBlock(
                id=block_id,
                page_id=page_id,
                block_type="text",
                x=36,
                y=48,
                w=540,
                h=72,
                reading_order=1,
                confidence=0.98,
                review_status="approved",
            )
        ],
        text_lines=[
            TextLine(
                id=line_id,
                block_id=block_id,
                page_id=page_id,
                text="Hello, reconstructed page.",
                x=36,
                y=48,
                w=240,
                h=18,
                baseline_y=62,
                font_family="serif",
                font_size=12,
                font_weight="regular",
                font_style="roman",
                color="#111111",
                ocr_confidence=0.97,
                font_confidence=0.83,
                review_status="approved",
            )
        ],
        words=[
            Word(
                id=word_id,
                line_id=line_id,
                text="Hello,",
                x=36,
                y=48,
                w=48,
                h=18,
                confidence=0.99,
            )
        ],
        assets=[
            ImageAsset(
                id=asset_id,
                page_id=page_id,
                source_block_id=None,
                asset_path="/artifacts/doc-1/assets/image-1.png",
                x=300,
                y=420,
                w=180,
                h=120,
                asset_type="image",
                confidence=0.91,
                review_status="pending",
            )
        ],
        links=[
            Link(
                id=link_id,
                page_id=page_id,
                source_type="explicit-url",
                source_text="https://example.com",
                x=36,
                y=84,
                w=160,
                h=18,
                target_type="external",
                target_uri="https://example.com",
                confidence=0.99,
                review_status="approved",
            )
        ],
        qa=PageQA(
            pixel_diff=0.12,
            structural_similarity=0.98,
            text_coverage=0.99,
            link_coverage=1.0,
            unresolved_items=0,
            review_status="approved",
            notes={"checked_by": "tester"},
        ),
    )

    return DocumentModel(
        id="doc-1",
        source_file="/input/source.pdf",
        output_pdf_path="/artifacts/doc-1/output.pdf",
        status="rendered",
        pages=[page],
        qa=DocumentQA(
            overall_score=0.97,
            pixel_diff=0.12,
            structural_similarity=0.98,
            text_coverage=0.99,
            link_coverage=1.0,
            unresolved_items=0,
            review_status="approved",
            notes={"pipeline": "stub"},
        ),
    )


def test_model_json_round_trip() -> None:
    model = build_sample_document()
    json_text = model.model_dump_json(indent=2)
    restored = DocumentReconstructionModel.model_validate_json(json_text)

    assert restored == model
    assert restored.pages[0].text_lines[0].text == "Hello, reconstructed page."
    assert restored.qa.overall_score == 0.97


def test_model_file_round_trip(tmp_path: Path) -> None:
    model = build_sample_document()
    path = tmp_path / "document-model.json"

    save_document_model(model, path)
    restored = load_document_model(path)

    assert restored == model
    assert restored.pages[0].links[0].target_uri == "https://example.com"


def test_schema_required_fields_and_coordinates() -> None:
    model = build_sample_document()
    page = model.pages[0]
    line = page.text_lines[0]
    word = page.words[0]
    asset = page.assets[0]
    link = page.links[0]

    assert page.width_pt > 0
    assert page.height_pt > 0
    assert page.width_px > 0
    assert page.height_px > 0
    assert line.x >= 0 and line.y >= 0 and line.w > 0 and line.h > 0
    assert word.x >= 0 and word.y >= 0 and word.w > 0 and word.h > 0
    assert asset.x >= 0 and asset.y >= 0 and asset.w > 0 and asset.h > 0
    assert link.x >= 0 and link.y >= 0 and link.w > 0 and link.h > 0
    assert model.id
    assert model.source_file
    assert line.text
    assert word.text


def test_schema_missing_required_fields_fails() -> None:
    payload = {
        "id": "doc-invalid",
        "status": "draft",
        "pages": [],
    }
    with pytest.raises(Exception):
        DocumentReconstructionModel.model_validate(payload)
