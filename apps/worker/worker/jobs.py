from __future__ import annotations

from app.db import (
    fetch_document_source_path,
    fetch_job,
    init_database,
    persist_document_model,
    update_document_status,
    update_job_status,
)
from app.settings import settings
from document_model import load_document_model

from app.services.stub_pipeline import process_stub_image


def stub_render_job(job_id: str) -> None:
    init_database(settings.database_url)
    update_job_status(job_id, "running")
    job = fetch_job(job_id)
    if job is None:
        return

    document_id = job["document_id"]
    source_path = fetch_document_source_path(document_id)
    if source_path is None:
        update_job_status(job_id, "failed", "document source_path not found")
        return

    try:
        result = process_stub_image(document_id, source_path, settings.artifact_root)
        model = load_document_model(result["model_path"])
        persist_document_model(model, result["model_path"])
        update_document_status(
            document_id,
            "rendered",
            output_pdf_path=result["pdf_path"],
            model_path=result["model_path"],
        )
        update_job_status(job_id, "succeeded")
    except Exception as exc:
        update_document_status(document_id, "error")
        update_job_status(job_id, "failed", str(exc))
        raise
