from __future__ import annotations

from pathlib import Path


def document_dir(root: str | Path, document_id: str) -> Path:
    return Path(root) / document_id


def source_path(document_root: str | Path, suffix: str) -> Path:
    return Path(document_root) / f"source{suffix}"


def page_dir(document_root: str | Path) -> Path:
    return Path(document_root) / "pages"


def normalized_image_path(document_root: str | Path, page_number: int, suffix: str = ".png") -> Path:
    return page_dir(document_root) / f"{page_number:04d}.normalized{suffix}"


def model_path(document_root: str | Path) -> Path:
    return Path(document_root) / "document-model.json"


def pdf_path(document_root: str | Path) -> Path:
    return Path(document_root) / "output.pdf"
