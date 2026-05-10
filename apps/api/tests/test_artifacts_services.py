from __future__ import annotations

import base64
from pathlib import Path

import fitz
import pytest

pytest.importorskip("sqlalchemy")
Image = pytest.importorskip("PIL.Image")

from app.services.documents import run_stub_render_for_document, store_source_file

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAIAAAAlC+aJAAAAY0lEQVR4nO3PQQ0AIBDAsAP/nkEEj4ZkVbCtOfO1rQNeNaAqQFWgKkBVoCpAVaAqQFWgKkBVoCpAVaAqQFWgKkBVoCpAVaAqQFWgKkBVoCpAVaAqQFWgKkBVoCpAVaAqQFWgKkBV4AH2VwF/8QkoGAAAAABJRU5ErkJggg=="
)


def _create_sample_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG_BYTES)


def _create_sample_jpeg(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (24, 16), color=(255, 255, 255))
    image.save(path, format="JPEG")


def _create_sample_tiff(path: Path, pages: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = [Image.new("RGB", (20 + idx, 30 + idx), color=(255, 255, 255)) for idx in range(pages)]
    frames[0].save(path, format="TIFF", save_all=True, append_images=frames[1:])


def test_store_source_file_under_artifact_root(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    _create_sample_image(source)
    artifact_root = tmp_path / "artifacts"

    result = store_source_file("doc-1", source, artifact_root)

    assert Path(result["source_path"]).exists()
    assert str(Path(result["source_path"])).startswith(str(artifact_root))


def test_stub_render_writes_model_and_pdf(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    _create_sample_image(source)
    artifact_root = tmp_path / "artifacts"

    result = run_stub_render_for_document("doc-2", source, artifact_root)

    model_path = Path(result["model_path"])
    pdf_path = Path(result["pdf_path"])
    assert model_path.exists()
    assert model_path.stat().st_size > 0
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0


def test_stub_render_png_creates_single_page_pdf(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    _create_sample_image(source)
    artifact_root = tmp_path / "artifacts"
    result = run_stub_render_for_document("doc-png", source, artifact_root)
    with fitz.open(result["pdf_path"]) as pdf:
        assert pdf.page_count == 1


def test_stub_render_jpeg_creates_single_page_pdf(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    _create_sample_jpeg(source)
    artifact_root = tmp_path / "artifacts"
    result = run_stub_render_for_document("doc-jpg", source, artifact_root)
    with fitz.open(result["pdf_path"]) as pdf:
        assert pdf.page_count == 1


def test_stub_render_multipage_tiff_creates_multipage_pdf(tmp_path: Path) -> None:
    source = tmp_path / "source.tiff"
    _create_sample_tiff(source, pages=3)
    artifact_root = tmp_path / "artifacts"
    result = run_stub_render_for_document("doc-tiff", source, artifact_root)
    with fitz.open(result["pdf_path"]) as pdf:
        assert pdf.page_count == 3
