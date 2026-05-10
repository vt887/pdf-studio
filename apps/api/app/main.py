from __future__ import annotations

import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from document_model import load_document_model
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .artifacts import document_dir, model_path
from .db import (
    create_document_row,
    create_job_row,
    fetch_document,
    fetch_documents_summary,
    fetch_job,
    init_database,
)
from .queue import enqueue_stub_render, redis_queue_name
from .services.documents import store_source_file
from .services.preprocessing import UnsupportedInputError, detect_input_type
from .settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.artifact_root.mkdir(parents=True, exist_ok=True)
    init_database(settings.database_url)
    yield


app = FastAPI(title="pdf-studio api", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/documents")
async def create_document(file: Annotated[UploadFile, File(...)]) -> dict[str, str]:
    suffix = Path(file.filename or "input.png").suffix or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        temp_path = Path(handle.name)
        handle.write(await file.read())
    try:
        detect_input_type(temp_path)
    except UnsupportedInputError as exc:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    document_id = uuid.uuid4().hex
    job_id = uuid.uuid4().hex
    try:
        stored = store_source_file(document_id, temp_path, settings.artifact_root)
    finally:
        temp_path.unlink(missing_ok=True)

    create_document_row(document_id, stored["source_path"], status="uploaded")
    queue_name = redis_queue_name("default", settings.redis_key_prefix)
    create_job_row(job_id, document_id, job_type="stub_render", status="queued", queue_name=queue_name)
    enqueue_stub_render(settings.redis_url, job_id, prefix=settings.redis_key_prefix)
    return {"document_id": document_id, "job_id": job_id}


@app.get("/v1/documents")
def list_documents() -> list[dict[str, object]]:
    return fetch_documents_summary()


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, object]:
    job = fetch_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/v1/documents/{document_id}")
def get_document(document_id: str) -> dict[str, object]:
    document = fetch_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@app.get("/v1/documents/{document_id}/model")
def get_document_model(document_id: str) -> dict[str, object]:
    root = document_dir(settings.artifact_root, document_id)
    model_file = model_path(root)
    if model_file.exists():
        return JSONResponse(content=load_document_model(model_file).model_dump(), media_type="application/json")
    document = fetch_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    raise HTTPException(status_code=409, detail="Document model is not ready yet")


@app.get("/v1/documents/{document_id}/pdf")
def get_document_pdf(document_id: str):
    document = fetch_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    output_pdf = document["document"]["output_pdf_path"]
    if not output_pdf:
        raise HTTPException(status_code=409, detail="Document PDF is not ready yet")
    output_pdf_path = Path(output_pdf)
    if not output_pdf_path.exists():
        raise HTTPException(status_code=409, detail="Document PDF is not ready yet")
    return FileResponse(
        output_pdf_path,
        media_type="application/pdf",
        filename=f"{document_id}.pdf",
        headers={"Content-Disposition": f'inline; filename="{document_id}.pdf"'},
    )
