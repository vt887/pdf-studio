from __future__ import annotations

from pathlib import Path

import fitz

from document_model import DocumentModel, ImageAsset, Link, PageModel, TextLine
from pdf_renderer import render_document

def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 200), False)
    pix.clear_with(255)
    pix.save(path)


def _build_document(image_path: Path) -> DocumentModel:
    page = PageModel(
        id="page-1",
        page_number=1,
        width_px=833,
        height_px=833,
        width_pt=200,
        height_pt=200,
        dpi=300,
        original_image_path=str(image_path),
        normalized_image_path=str(image_path),
        text_lines=[
            TextLine(
                id="line-1",
                block_id="block-1",
                page_id="page-1",
                text="Hello PDF",
                x=20,
                y=20,
                w=120,
                h=20,
                font_size=12,
            )
        ],
        assets=[
            ImageAsset(
                id="asset-1",
                page_id="page-1",
                asset_path=str(image_path),
                x=0,
                y=0,
                w=200,
                h=200,
            )
        ],
        links=[
            Link(
                id="link-1",
                page_id="page-1",
                source_type="explicit-url",
                source_text="example",
                x=20,
                y=20,
                w=80,
                h=20,
                target_type="external",
                target_uri="https://example.com",
            )
        ],
    )
    return DocumentModel(id="doc-1", source_file="input.png", pages=[page])


def test_render_pdf_contains_text_and_dimensions(tmp_path: Path) -> None:
    image_path = tmp_path / "img.png"
    _make_image(image_path)
    model = _build_document(image_path)
    output = tmp_path / "out.pdf"

    result = render_document(model, output)

    assert result.exists()
    assert result.stat().st_size > 0
    with fitz.open(result) as pdf:
        assert pdf.page_count == 1
        page = pdf[0]
        assert round(page.rect.width, 2) == 200
        assert round(page.rect.height, 2) == 200
        text = page.get_text("text")
        assert "Hello PDF" in text


def test_render_pdf_contains_link_annotation(tmp_path: Path) -> None:
    image_path = tmp_path / "img.png"
    _make_image(image_path)
    model = _build_document(image_path)
    output = tmp_path / "out-links.pdf"
    render_document(model, output)

    with fitz.open(output) as pdf:
        page = pdf[0]
        links = page.get_links()
        assert len(links) >= 1
        assert any(link.get("uri") == "https://example.com" for link in links)
