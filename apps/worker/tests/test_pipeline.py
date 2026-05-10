from __future__ import annotations

import shutil
from pathlib import Path
import pytest
from PIL import Image

from worker.pipeline import process_stub_image

def test_process_stub_image_creates_artifacts(tmp_path: Path):
    # Create a valid PNG image
    source = tmp_path / "source.png"
    image = Image.new("RGB", (10, 10), color=(255, 255, 255))
    image.save(source, format="PNG")
    storage_root = tmp_path / "artifacts"
    result = process_stub_image(source, storage_root)
    document_dir = Path(result["document_dir"])
    assert document_dir.exists()
    assert (document_dir / "source.png").exists()
    assert (document_dir / "pages/0001.normalized.png").exists()
    assert Path(result["model_path"]).exists()
    assert Path(result["pdf_path"]).exists()

def test_process_stub_image_missing_source(tmp_path: Path):
    storage_root = tmp_path / "artifacts"
    with pytest.raises(FileNotFoundError):
        process_stub_image(tmp_path / "missing.png", storage_root)
