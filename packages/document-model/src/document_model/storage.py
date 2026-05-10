from __future__ import annotations

from pathlib import Path

from .schema import DocumentModel


def save_document_model(document: DocumentModel, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_document_model(path: str | Path) -> DocumentModel:
    path = Path(path)
    return DocumentModel.model_validate_json(path.read_text(encoding="utf-8"))
