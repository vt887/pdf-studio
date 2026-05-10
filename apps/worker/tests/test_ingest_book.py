from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import fitz
import pytest

Image = pytest.importorskip("PIL.Image")

from document_model import load_document_model
from worker.ingest_book import IngestError, ingest_book, main as ingest_main


def _create_png(path: Path, size: tuple[int, int] = (20, 20)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color=(255, 255, 255))
    img.save(path, format="PNG")


def _create_jpeg(path: Path, size: tuple[int, int] = (24, 16)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color=(240, 240, 240))
    img.save(path, format="JPEG")


def _create_tiff(path: Path, sizes: tuple[tuple[int, int], tuple[int, int]] = ((18, 18), (22, 22))) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    first = Image.new("RGB", sizes[0], color=(255, 255, 255))
    second = Image.new("RGB", sizes[1], color=(200, 200, 200))
    first.save(path, format="TIFF", save_all=True, append_images=[second])


def _set_mtime(path: Path, ts: float) -> None:
    os.utime(path, (ts, ts))


def _run_cli(monkeypatch: pytest.MonkeyPatch, args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[str, str]:
    monkeypatch.setattr(sys, "argv", ["worker.ingest_book", *args])
    ingest_main()
    captured = capsys.readouterr()
    return captured.out, captured.err


def test_oldest_becomes_first_newest_last(tmp_path: Path) -> None:
    book = tmp_path / "book"
    out = tmp_path / "output"
    a = book / "a.png"
    b = book / "b.png"
    c = book / "c.png"
    _create_png(a)
    _create_png(b)
    _create_png(c)
    _set_mtime(a, 1000)
    _set_mtime(b, 2000)
    _set_mtime(c, 3000)

    result = ingest_book(book, out)
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert "created_at" in manifest
    assert Path(manifest["pages"][0]["source_file"]).name == "a.png"
    assert Path(manifest["pages"][-1]["source_file"]).name == "c.png"


def test_modified_time_fallback_works(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book = tmp_path / "book"
    out = tmp_path / "output"
    x = book / "x.png"
    y = book / "y.png"
    _create_png(x)
    _create_png(y)
    _set_mtime(x, 1000)
    _set_mtime(y, 2000)

    orig_stat = Path.stat

    def stat_no_birth(self: Path, *args, **kwargs):
        st = orig_stat(self)
        class StatProxy:
            st_birthtime = None

            def __getattr__(self, name: str):
                return getattr(st, name)

        return StatProxy()

    monkeypatch.setattr(Path, "stat", stat_no_birth)
    result = ingest_book(book, out)
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["ordering_strategy"] == "mtime->natural_filename"
    assert Path(manifest["pages"][0]["source_file"]).name == "x.png"


def test_natural_filename_fallback_when_timestamps_equal(tmp_path: Path) -> None:
    book = tmp_path / "book"
    out = tmp_path / "output"
    p10 = book / "page10.png"
    p2 = book / "page2.png"
    _create_png(p10)
    _create_png(p2)
    _set_mtime(p10, 2000)
    _set_mtime(p2, 2000)

    result = ingest_book(book, out)
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["warning_identical_timestamps"] is True
    assert Path(manifest["pages"][0]["source_file"]).name == "page2.png"
    assert Path(manifest["pages"][1]["source_file"]).name == "page10.png"


def test_manifest_order_used_by_stub_renderer(tmp_path: Path) -> None:
    book = tmp_path / "book"
    out = tmp_path / "output"
    first = book / "01.png"
    second = book / "02.png"
    _create_png(first, size=(20, 30))
    _create_png(second, size=(40, 50))
    _set_mtime(first, 1000)
    _set_mtime(second, 2000)

    result = ingest_book(book, out)
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    model = load_document_model(result["model_path"])
    assert len(model.pages) == len(manifest["pages"]) == 2
    assert model.pages[0].original_image_path == manifest["pages"][0]["original_artifact"]
    assert model.pages[1].original_image_path == manifest["pages"][1]["original_artifact"]
    assert model.pages[0].normalized_image_path == manifest["pages"][0]["normalized_artifact"]
    assert model.pages[1].normalized_image_path == manifest["pages"][1]["normalized_artifact"]
    assert model.pages[0].text_lines[0].text == "Page 1"
    assert model.pages[1].text_lines[0].text == "Page 2"
    assert Path(result["model_path"]).exists()
    assert Path(result["pdf_path"]).exists()
    with fitz.open(result["pdf_path"]) as pdf:
        assert pdf.page_count == 2


def test_default_cli_output_contains_stage_prefixes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    book = tmp_path / "book"
    out = tmp_path / "output"
    source = book / "scan.png"
    _create_png(source)
    _set_mtime(source, 1111)

    stdout, stderr = _run_cli(monkeypatch, ["--input", str(book), "--output", str(out)], capsys)
    assert "[ingest]" in stdout
    assert "[manifest]" in stdout
    assert "[preprocess]" in stdout
    assert "[model]" in stdout
    assert "[render]" in stdout
    assert "[summary]" in stdout
    assert "[spread-detect]" in stdout
    assert stderr == ""


def test_verbose_output_contains_page_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    book = tmp_path / "book"
    out = tmp_path / "output"
    source = book / "scan.png"
    _create_png(source)
    _set_mtime(source, 1111)

    stdout, _ = _run_cli(monkeypatch, ["--input", str(book), "--output", str(out), "--verbose"], capsys)
    assert "1 of 1" in stdout
    assert "original_artifact" in stdout
    assert "normalized_artifact" in stdout
    assert "autorotate_applied" in stdout


def test_progress_output_shows_page_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    book = tmp_path / "book"
    out = tmp_path / "output"
    first = book / "a.png"
    second = book / "b.png"
    _create_png(first)
    _create_png(second)
    _set_mtime(first, 1000)
    _set_mtime(second, 2000)

    stdout, _ = _run_cli(monkeypatch, ["--input", str(book), "--output", str(out)], capsys)
    assert "1 of 2" in stdout
    assert "2 of 2" in stdout


def test_auto_mixed_creates_expected_page_count(tmp_path: Path) -> None:
    book = tmp_path / "book"
    out = tmp_path / "output"
    first = book / "01.png"
    second = book / "02.png"
    third = book / "03.png"
    _create_png(first, size=(1000, 1500))
    _create_png(second, size=(2000, 1000))
    _create_png(third, size=(2000, 1000))
    _set_mtime(first, 1000)
    _set_mtime(second, 2000)
    _set_mtime(third, 3000)

    result = ingest_book(book, out, spread_mode="auto-mixed")
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["spread_mode"] == "auto-mixed"
    assert manifest["source_files_count"] == 3
    assert manifest["pages_count"] == 5
    assert manifest["spread_detection"]["single_page_count"] == 1
    assert manifest["spread_detection"]["two_page_count"] == 2
    assert len(manifest["pages"]) == 5
    assert Path(result["pdf_path"]).exists()
    with fitz.open(result["pdf_path"]) as pdf:
        assert pdf.page_count == 5
    model = load_document_model(result["model_path"])
    assert len(model.pages) == 5


def test_page_order_preserved_across_single_and_two_page_sources(tmp_path: Path) -> None:
    book = tmp_path / "book"
    out = tmp_path / "output"
    first = book / "01.png"
    second = book / "02.png"
    third = book / "03.png"
    _create_png(first, size=(1000, 1500))
    _create_png(second, size=(2000, 1000))
    _create_png(third, size=(2000, 1000))
    _set_mtime(first, 1000)
    _set_mtime(second, 2000)
    _set_mtime(third, 3000)

    result = ingest_book(book, out, spread_mode="auto-mixed")
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    pages = manifest["pages"]
    assert [page["page_number"] for page in pages] == [1, 2, 3, 4, 5]
    assert [page["side"] for page in pages] == ["single", "left", "right", "left", "right"]
    assert manifest["sources"][0]["effective_type"] == "single-page"
    assert manifest["sources"][1]["effective_type"] == "two-page"
    assert manifest["sources"][2]["effective_type"] == "two-page"
    assert manifest["sources"][0]["derived_pages"][0]["page_number"] == 1
    assert manifest["sources"][1]["derived_pages"][0]["page_number"] == 2
    assert manifest["sources"][1]["derived_pages"][1]["page_number"] == 3
    assert manifest["sources"][2]["derived_pages"][0]["page_number"] == 4
    assert manifest["sources"][2]["derived_pages"][1]["page_number"] == 5


def test_override_file_forces_classification(tmp_path: Path) -> None:
    book = tmp_path / "book"
    out = tmp_path / "output"
    source = book / "IMG_0001.jpg"
    _create_png(source, size=(2000, 1000))
    _set_mtime(source, 1111)
    overrides = book / "spread-overrides.json"
    overrides.write_text(json.dumps({"files": {"IMG_0001.jpg": "single-page"}}), encoding="utf-8")

    result = ingest_book(book, out, spread_mode="auto-mixed")
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["pages_count"] == 1
    assert manifest["sources"][0]["classification_source"] == "override"
    assert manifest["sources"][0]["effective_type"] == "single-page"
    assert manifest["sources"][0]["detected_type"] == "two-page"


def test_override_missing_source_fails(tmp_path: Path) -> None:
    book = tmp_path / "book"
    out = tmp_path / "output"
    source = book / "IMG_0001.jpg"
    _create_png(source, size=(2000, 1000))
    _set_mtime(source, 1111)
    overrides = book / "spread-overrides.json"
    overrides.write_text(json.dumps({"files": {"IMG_9999.jpg": "single-page"}}), encoding="utf-8")

    with pytest.raises(IngestError, match="spread override references missing file"):
        ingest_book(book, out, spread_mode="auto-mixed")


def test_uncertain_file_fails_clearly(tmp_path: Path) -> None:
    book = tmp_path / "book"
    out = tmp_path / "output"
    source = book / "IMG_0001.jpg"
    _create_png(source, size=(1400, 1000))
    _set_mtime(source, 1111)

    with pytest.raises(IngestError, match="uncertain source"):
        ingest_book(book, out, spread_mode="auto-mixed")


def test_manifest_records_classification_and_flat_pages_match_derived_pages(tmp_path: Path) -> None:
    book = tmp_path / "book"
    out = tmp_path / "output"
    first = book / "01.png"
    second = book / "02.png"
    _create_png(first, size=(1000, 1500))
    _create_png(second, size=(2000, 1000))
    _set_mtime(first, 1000)
    _set_mtime(second, 2000)

    result = ingest_book(book, out, spread_mode="auto-mixed")
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    flat_pages = manifest["pages"]
    derived_pages = [item for source in manifest["sources"] for item in source["derived_pages"]]
    assert len(flat_pages) == len(derived_pages) == 3
    assert [page["page_number"] for page in flat_pages] == [page["page_number"] for page in derived_pages]
    assert flat_pages[0]["detected_type"] == "single-page"
    assert flat_pages[1]["detected_type"] == "two-page"
    assert flat_pages[1]["classification_source"] == "detector"
    assert flat_pages[1]["side"] == "left"
    assert flat_pages[2]["side"] == "right"
    assert Path(result["pdf_path"]).exists()


def test_quiet_output_suppresses_stage_details(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    book = tmp_path / "book"
    out = tmp_path / "output"
    source = book / "scan.png"
    _create_png(source)
    _set_mtime(source, 1111)

    stdout, _ = _run_cli(monkeypatch, ["--input", str(book), "--output", str(out), "--quiet"], capsys)
    assert "[ingest]" not in stdout
    assert "[manifest]" not in stdout
    assert "[preprocess]" not in stdout
    assert "[summary]" not in stdout
    assert "document_id" in stdout


def test_original_and_normalized_artifacts_are_copied(tmp_path: Path) -> None:
    book = tmp_path / "book"
    out = tmp_path / "output"
    source = book / "scan.png"
    _create_png(source, size=(31, 29))
    _set_mtime(source, 1111)

    result = ingest_book(book, out)
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    page = manifest["pages"][0]
    assert {"original_artifact", "normalized_artifact", "width_px", "height_px", "normalized_width_px", "normalized_height_px", "dpi"} <= page.keys()
    original = Path(page["original_artifact"])
    normalized = Path(page["normalized_artifact"])
    assert original.exists()
    assert normalized.exists()
    assert original.read_bytes() == source.read_bytes()
    with Image.open(normalized) as image:
        assert image.format == "PNG"
        assert image.mode == "RGB"


def test_summary_and_preprocess_metadata_are_created(tmp_path: Path) -> None:
    book = tmp_path / "book"
    out = tmp_path / "output"
    source = book / "scan.png"
    _create_png(source, size=(31, 29))
    _set_mtime(source, 1111)

    result = ingest_book(book, out)
    summary_path = Path(result["summary_path"])
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["document_id"] == result["document_id"]
    assert summary["pages_count"] == 1
    assert summary["manifest_path"] == result["manifest_path"]
    assert summary["model_path"] == result["model_path"]
    assert summary["pdf_path"] == result["pdf_path"]
    assert summary["artifacts_dir"].endswith("artifacts")
    assert summary["stages"][0]["name"] == "ingest"
    assert summary["stages"][-1]["name"] == "summary"
    assert summary["render"]["pages_rendered"] == 1
    assert summary["render"]["image_assets_rendered"] == 1
    assert summary["render"]["text_lines_rendered"] == 1
    assert summary["render"]["links_rendered"] == 0
    preprocess = Path(out / "artifacts" / "pages" / "0001.preprocess.json")
    assert preprocess.exists()
    preprocess_payload = json.loads(preprocess.read_text(encoding="utf-8"))
    assert preprocess_payload["page_number"] == 1
    assert preprocess_payload["source_artifact"].endswith("0001.source.png")
    assert preprocess_payload["normalized_artifact"].endswith("0001.normalized.png")
    assert preprocess_payload["mode"] == "RGB"
    assert preprocess_payload["autorotate_applied"] is False
    assert preprocess_payload["deskew_applied"] is False


def test_jpeg_input_creates_normalized_png(tmp_path: Path) -> None:
    book = tmp_path / "book"
    out = tmp_path / "output"
    source = book / "scan.jpg"
    _create_jpeg(source, size=(19, 23))
    _set_mtime(source, 1111)

    result = ingest_book(book, out)
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    page = manifest["pages"][0]
    assert page["source_artifact"].endswith(".source.jpg")
    assert page["normalized_artifact"].endswith(".normalized.png")
    with Image.open(page["normalized_artifact"]) as image:
        assert image.format == "PNG"
        assert image.mode == "RGB"


def test_renderer_counts_are_included_in_summary(tmp_path: Path) -> None:
    book = tmp_path / "book"
    out = tmp_path / "output"
    source = book / "scan.png"
    _create_png(source)
    _set_mtime(source, 1111)

    result = ingest_book(book, out)
    summary = json.loads(Path(result["summary_path"]).read_text(encoding="utf-8"))
    assert summary["render"]["pages_rendered"] == 1
    assert summary["render"]["image_assets_rendered"] == 1
    assert summary["render"]["text_lines_rendered"] == 1
    assert summary["render"]["links_rendered"] == 0


def test_tiff_input_creates_multiple_pages(tmp_path: Path) -> None:
    book = tmp_path / "book"
    out = tmp_path / "output"
    source = book / "scan.tiff"
    _create_tiff(source)
    _set_mtime(source, 1111)

    result = ingest_book(book, out)
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    model = load_document_model(result["model_path"])
    assert len(manifest["pages"]) == 2
    assert len(model.pages) == 2
    assert Path(result["pdf_path"]).exists()


def test_existing_manifest_preserves_page_order_on_rerun(tmp_path: Path) -> None:
    book = tmp_path / "book"
    out = tmp_path / "output"
    first = book / "01.png"
    second = book / "02.png"
    third = book / "03.png"
    _create_png(first)
    _create_png(second)
    _set_mtime(first, 1000)
    _set_mtime(second, 2000)

    initial = ingest_book(book, out)
    initial_manifest = json.loads(Path(initial["manifest_path"]).read_text(encoding="utf-8"))
    assert [Path(page["source_file"]).name for page in initial_manifest["pages"]] == ["01.png", "02.png"]

    _create_png(third)
    _set_mtime(third, 3000)

    rerun = ingest_book(book, out)
    rerun_manifest = json.loads(Path(rerun["manifest_path"]).read_text(encoding="utf-8"))
    assert [Path(page["source_file"]).name for page in rerun_manifest["pages"]] == ["01.png", "02.png"]


def test_force_rebuilds_manifest(tmp_path: Path) -> None:
    book = tmp_path / "book"
    out = tmp_path / "output"
    first = book / "01.png"
    second = book / "02.png"
    third = book / "03.png"
    _create_png(first)
    _create_png(second)
    _set_mtime(first, 1000)
    _set_mtime(second, 2000)

    initial = ingest_book(book, out)
    initial_manifest = json.loads(Path(initial["manifest_path"]).read_text(encoding="utf-8"))

    _create_png(third)
    _set_mtime(third, 3000)

    forced = ingest_book(book, out, force=True)
    forced_manifest = json.loads(Path(forced["manifest_path"]).read_text(encoding="utf-8"))
    assert initial_manifest["document_id"] != forced_manifest["document_id"]
    assert [Path(page["source_file"]).name for page in forced_manifest["pages"]] == ["01.png", "02.png", "03.png"]
    assert len(load_document_model(forced["model_path"]).pages) == 3
    assert Path(forced["pdf_path"]).exists()


def test_missing_input_directory_rejected(tmp_path: Path) -> None:
    out = tmp_path / "output"
    with pytest.raises(Exception):
        ingest_book(tmp_path / "book-missing", out)
