from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("sqlalchemy")

from app import main as api_main


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/vW0AAAAASUVORK5CYII="
)


def test_v1_create_document_enqueues_job(monkeypatch):
    monkeypatch.setattr(api_main, "init_database", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(api_main, "create_document_row", lambda *args, **kwargs: None)
    monkeypatch.setattr(api_main, "create_job_row", lambda *args, **kwargs: None)
    monkeypatch.setattr(api_main, "enqueue_stub_render", lambda *args, **kwargs: "rq-123")
    monkeypatch.setattr(
        api_main,
        "store_source_file",
        lambda document_id, source_path, artifact_root: {
            "document_id": document_id,
            "source_path": "/artifacts/source.png",
        },
    )

    with TestClient(api_main.app) as client:
        response = client.post("/v1/documents", files={"file": ("sample.png", PNG_BYTES, "image/png")})
        assert response.status_code == 200
        payload = response.json()
        assert "document_id" in payload
        assert "job_id" in payload


def test_health(monkeypatch):
    monkeypatch.setattr(api_main, "init_database", lambda *_args, **_kwargs: None)
    with TestClient(api_main.app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_v1_get_job(monkeypatch):
    monkeypatch.setattr(api_main, "init_database", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        api_main,
        "fetch_job",
        lambda job_id: {
            "id": job_id,
            "document_id": "doc-1",
            "status": "queued",
            "job_type": "stub_render",
            "queue_name": "default",
            "error_message": None,
            "created_at": None,
            "updated_at": None,
        },
    )

    with TestClient(api_main.app) as client:
        response = client.get("/v1/jobs/job-1")
        assert response.status_code == 200
        assert response.json()["status"] == "queued"


def test_v1_documents_list(monkeypatch):
    monkeypatch.setattr(api_main, "init_database", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        api_main,
        "fetch_documents_summary",
        lambda: [
            {
                "document_id": "doc-1",
                "source_filename": "sample.png",
                "status": "processing",
                "created_at": None,
                "updated_at": None,
                "latest_job_id": "job-1",
                "latest_job_status": "running",
                "has_model": False,
                "has_pdf": False,
            }
        ],
    )
    with TestClient(api_main.app) as client:
        response = client.get("/v1/documents")
        assert response.status_code == 200
        payload = response.json()
        assert payload[0]["document_id"] == "doc-1"
        assert payload[0]["latest_job_status"] == "running"


def test_v1_get_document(monkeypatch):
    monkeypatch.setattr(api_main, "init_database", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        api_main,
        "fetch_document",
        lambda _document_id: {"document": {"id": "doc-1", "status": "processing", "output_pdf_path": None}, "pages": []},
    )
    with TestClient(api_main.app) as client:
        response = client.get("/v1/documents/doc-1")
        assert response.status_code == 200
        assert response.json()["document"]["id"] == "doc-1"


def test_v1_document_artifacts_not_ready(monkeypatch):
    monkeypatch.setattr(api_main, "init_database", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        api_main,
        "fetch_document",
        lambda _document_id: {
            "document": {"id": "doc-1", "output_pdf_path": None, "status": "processing"},
            "pages": [],
        },
    )
    with TestClient(api_main.app) as client:
        model_response = client.get("/v1/documents/doc-1/model")
        assert model_response.status_code == 409
        assert "not ready" in model_response.json()["detail"].lower()

        pdf_response = client.get("/v1/documents/doc-1/pdf")
        assert pdf_response.status_code == 409
        assert "not ready" in pdf_response.json()["detail"].lower()


def test_v1_document_pdf_metadata_exists_but_file_missing(monkeypatch):
    monkeypatch.setattr(api_main, "init_database", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        api_main,
        "fetch_document",
        lambda _document_id: {
            "document": {
                "id": "doc-2",
                "status": "rendered",
                "output_pdf_path": "/tmp/definitely-missing-file.pdf",
            },
            "pages": [],
        },
    )
    with TestClient(api_main.app) as client:
        response = client.get("/v1/documents/doc-2/pdf")
        assert response.status_code == 409


def test_v1_document_model_missing_returns_404(monkeypatch):
    monkeypatch.setattr(api_main, "init_database", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(api_main, "fetch_document", lambda _document_id: None)
    with TestClient(api_main.app) as client:
        response = client.get("/v1/documents/missing/model")
        assert response.status_code == 404


def test_v1_document_pdf_content_type(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(api_main, "init_database", lambda *_args, **_kwargs: None)
    pdf_path = tmp_path / "out.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF")
    monkeypatch.setattr(
        api_main,
        "fetch_document",
        lambda _document_id: {
            "document": {"id": "doc-3", "output_pdf_path": str(pdf_path), "status": "rendered"},
            "pages": [],
        },
    )
    with TestClient(api_main.app) as client:
        response = client.get("/v1/documents/doc-3/pdf")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/pdf")


def test_v1_create_document_rejects_unsupported_file(monkeypatch):
    monkeypatch.setattr(api_main, "init_database", lambda *_args, **_kwargs: None)
    with TestClient(api_main.app) as client:
        response = client.post("/v1/documents", files={"file": ("bad.txt", b"hello", "text/plain")})
        assert response.status_code == 400
        assert "unsupported file type" in response.json()["detail"].lower()
