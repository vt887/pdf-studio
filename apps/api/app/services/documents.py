from __future__ import annotations

import shutil
from pathlib import Path

from document_model import StubPageInput, build_stub_document_model_from_pages, load_document_model, save_document_model
from pdf_renderer import render_document

from .. import artifacts
from ..db import persist_document_model
from .preprocessing import extract_and_normalize_pages


def store_source_file(document_id: str, source_path: str | Path, artifact_root: str | Path) -> dict[str, str]:
    source_path = Path(source_path)
    document_root = artifacts.document_dir(artifact_root, document_id)
    artifacts.page_dir(document_root).mkdir(parents=True, exist_ok=True)

    source_copy_path = artifacts.source_path(document_root, source_path.suffix or ".png")
    shutil.copy2(source_path, source_copy_path)
    return {
        "document_id": document_id,
        "document_root": str(document_root),
        "source_path": str(source_copy_path),
        "model_path": str(artifacts.model_path(document_root)),
        "pdf_path": str(artifacts.pdf_path(document_root)),
    }


def run_stub_render_for_document(
    document_id: str,
    source_path: str | Path,
    artifact_root: str | Path,
) -> dict[str, str]:
    document_root = artifacts.document_dir(artifact_root, document_id)
    artifacts.page_dir(document_root).mkdir(parents=True, exist_ok=True)
    extracted_pages = extract_and_normalize_pages(
        source_path=source_path,
        document_root=document_root,
    )
    document = build_stub_document_model_from_pages(
        source_path=source_path,
        pages=[
            StubPageInput(
                page_number=page.page_number,
                width_px=page.width_px,
                height_px=page.height_px,
                width_pt=page.width_pt,
                height_pt=page.height_pt,
                dpi=page.dpi,
                rotation=page.rotation,
                original_image_path=page.original_image_path,
                normalized_image_path=page.normalized_image_path,
            )
            for page in extracted_pages
        ],
        output_pdf_path=artifacts.pdf_path(document_root),
        document_id=document_id,
    )
    model_file = artifacts.model_path(document_root)
    save_document_model(document, model_file)
    output_pdf = artifacts.pdf_path(document_root)
    render_document(document, output_pdf)
    save_document_model(document, model_file)
    return {
        "document_id": document.id,
        "document_root": str(document_root),
        "model_path": str(model_file),
        "pdf_path": str(output_pdf),
    }


def render_document_from_artifacts(document_id: str, storage_root: str | Path, database_url: str) -> dict[str, str]:
    document_root = artifacts.document_dir(storage_root, document_id)
    model_file = artifacts.model_path(document_root)
    if not model_file.exists():
        raise FileNotFoundError(f"Document model not found for {document_id}")

    document = load_document_model(model_file)
    output_pdf = artifacts.pdf_path(document_root)
    render_document(document, output_pdf)
    save_document_model(document, model_file)
    persist_document_model(document, str(model_file))
    return {
        "document_id": document.id,
        "document_root": str(document_root),
        "model_path": str(model_file),
        "pdf_path": str(output_pdf),
    }
