from __future__ import annotations

import base64
from pathlib import Path

import fitz
import pytest

from document_model import StubPageInput, build_stub_document_model_from_pages
from worker.ingest_book import _build_parser
from worker.ocr import (
    OcrError,
    OcrLine,
    OcrPageResult,
    OcrWord,
    TesseractOcrEngine,
    apply_ocr_results,
    px_to_pt,
)
from pdf_renderer import render_document


TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/m9kAAAAASUVORK5CYII="
)


def _write_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(TINY_PNG)


def test_ocr_schema_roundtrip() -> None:
    payload = OcrPageResult(
        page_number=1,
        normalized_artifact="output/artifacts/pages/0001.normalized.png",
        engine="tesseract",
        language="eng",
        width_px=2480,
        height_px=3508,
        dpi=300,
        lines=[
            OcrLine(
                id="line-1",
                text="Example line",
                x=100,
                y=200,
                w=800,
                h=40,
                confidence=0.95,
                words=[
                    OcrWord(
                        id="word-1",
                        text="Example",
                        x=100,
                        y=200,
                        w=320,
                        h=40,
                        confidence=0.96,
                    )
                ],
            )
        ],
    )

    roundtrip = OcrPageResult.model_validate_json(payload.model_dump_json())
    assert roundtrip.page_number == 1
    assert roundtrip.normalized_artifact.endswith("0001.normalized.png")
    assert roundtrip.lines[0].text == "Example line"
    assert roundtrip.lines[0].words[0].text == "Example"


def test_px_to_pt_conversion() -> None:
    assert px_to_pt(300, 300) == pytest.approx(72.0)
    assert px_to_pt(150, 300) == pytest.approx(36.0)


def test_apply_ocr_results_updates_document_model(tmp_path: Path) -> None:
    document = build_stub_document_model_from_pages(
        source_path=tmp_path / "book",
        pages=[
            StubPageInput(
                page_number=1,
                width_px=300,
                height_px=300,
                width_pt=72.0,
                height_pt=72.0,
                dpi=300,
                original_image_path=str(tmp_path / "0001.original.png"),
                normalized_image_path=str(tmp_path / "0001.normalized.png"),
            )
        ],
        document_id="doc-1",
    )
    apply_ocr_results(
        document,
        [
            OcrPageResult(
                page_number=1,
                normalized_artifact=str(tmp_path / "0001.normalized.png"),
                engine="tesseract",
                language="eng",
                width_px=300,
                height_px=300,
                dpi=300,
                lines=[
                    OcrLine(
                        id="line-1",
                        text="Example line",
                        x=30,
                        y=40,
                        w=120,
                        h=20,
                        confidence=0.93,
                        words=[
                            OcrWord(id="word-1", text="Example", x=30, y=40, w=70, h=20, confidence=0.96),
                            OcrWord(id="word-2", text="line", x=104, y=40, w=46, h=20, confidence=0.91),
                        ],
                    )
                ],
            )
        ],
    )

    page = document.pages[0]
    assert page.text_lines[0].text == "Example line"
    assert page.words[0].text == "Example"
    assert page.words[0].x == pytest.approx(7.2)
    assert page.blocks[-1].block_type == "text"
    assert page.qa.ocr_text_found is True


def test_apply_ocr_results_with_no_text_leaves_no_stub_lines(tmp_path: Path) -> None:
    document = build_stub_document_model_from_pages(
        source_path=tmp_path / "book",
        pages=[
            StubPageInput(
                page_number=1,
                width_px=300,
                height_px=300,
                width_pt=72.0,
                height_pt=72.0,
                dpi=300,
                original_image_path=str(tmp_path / "0001.original.png"),
                normalized_image_path=str(tmp_path / "0001.normalized.png"),
            )
        ],
        document_id="doc-1",
    )
    apply_ocr_results(
        document,
        [
            OcrPageResult(
                page_number=1,
                normalized_artifact=str(tmp_path / "0001.normalized.png"),
                engine="tesseract",
                language="eng",
                width_px=300,
                height_px=300,
                dpi=300,
                lines=[],
            )
        ],
    )

    page = document.pages[0]
    assert page.text_lines == []
    assert page.words == []
    assert [block.block_type for block in page.blocks] == ["image"]
    assert page.qa.ocr_text_found is False


def test_renderer_uses_page_text_lines(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    pdf_path = tmp_path / "rendered.pdf"
    _write_png(image_path)
    document = build_stub_document_model_from_pages(
        source_path=tmp_path / "book",
        pages=[
            StubPageInput(
                page_number=1,
                width_px=300,
                height_px=300,
                width_pt=72.0,
                height_pt=72.0,
                dpi=300,
                original_image_path=str(image_path),
                normalized_image_path=str(image_path),
            )
        ],
        document_id="doc-1",
    )
    apply_ocr_results(
        document,
        [
            OcrPageResult(
                page_number=1,
                normalized_artifact=str(image_path),
                engine="tesseract",
                language="eng",
                width_px=300,
                height_px=300,
                dpi=300,
                lines=[
                    OcrLine(
                        id="line-1",
                        text="Selectable OCR text",
                        x=12,
                        y=14,
                        w=120,
                        h=18,
                        confidence=0.99,
                        words=[
                            OcrWord(id="word-1", text="Selectable", x=12, y=14, w=64, h=18, confidence=0.99),
                            OcrWord(id="word-2", text="OCR", x=79, y=14, w=30, h=18, confidence=0.98),
                            OcrWord(id="word-3", text="text", x=113, y=14, w=19, h=18, confidence=0.97),
                        ],
                    )
                ],
            )
        ],
    )
    render_document(document, pdf_path)

    with fitz.open(pdf_path) as pdf:
        assert pdf.page_count == 1
        extracted = pdf[0].get_text()
        assert "Selectable OCR text" in extracted


def test_tesseract_engine_fails_clearly_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("worker.ocr.shutil.which", lambda _: None)
    with pytest.raises(OcrError, match="Tesseract executable was not found"):
        TesseractOcrEngine()


def test_cli_accepts_ocr_flags() -> None:
    parser = _build_parser()
    args = parser.parse_args(["--input", "book", "--output", "output", "--ocr", "--ocr-lang", "deu"])
    assert args.ocr is True
    assert args.ocr_lang == "deu"
