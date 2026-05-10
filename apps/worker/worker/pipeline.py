from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from document_model import build_stub_document_model, save_document_model
from pdf_renderer import render_document


def process_stub_image(source_path: str | Path, storage_root: str | Path) -> dict[str, str]:
    source_path = Path(source_path)
    storage_root = Path(storage_root)
    document_id = uuid.uuid4().hex
    document_dir = storage_root / document_id
    pages_dir = document_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    source_copy_path = document_dir / f"source{source_path.suffix or '.png'}"
    shutil.copy2(source_path, source_copy_path)
    normalized_image_path = pages_dir / "0001.normalized.png"
    shutil.copy2(source_copy_path, normalized_image_path)

    document = build_stub_document_model(
        source_path=source_copy_path,
        normalized_image_path=normalized_image_path,
        output_pdf_path=document_dir / "output.pdf",
        document_id=document_id,
    )
    model_path = document_dir / "document-model.json"
    save_document_model(document, model_path)
    render_document(document, document.output_pdf_path)

    return {
        "document_id": document.id,
        "document_dir": str(document_dir),
        "model_path": str(model_path),
        "pdf_path": str(document.output_pdf_path),
    }
