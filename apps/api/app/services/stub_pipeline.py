from __future__ import annotations

from pathlib import Path

from .documents import run_stub_render_for_document


def process_stub_image(document_id: str, source_path: str | Path, artifact_root: str | Path) -> dict[str, str]:
    return run_stub_render_for_document(document_id, source_path, artifact_root)
