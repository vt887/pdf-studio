from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy")
Image = pytest.importorskip("PIL.Image")
from worker import jobs as worker_jobs


def _create_sample_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (40, 40), color=(255, 255, 255))
    image.save(path, format="PNG")


def test_job_status_transition_success(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    _create_sample_image(source)
    states: list[tuple[str, str, str | None]] = []

    monkeypatch.setattr(worker_jobs, "init_database", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(worker_jobs, "fetch_job", lambda _job_id: {"document_id": "doc-1"})
    monkeypatch.setattr(worker_jobs, "fetch_document_source_path", lambda _doc_id: str(source))
    monkeypatch.setattr(
        worker_jobs,
        "process_stub_image",
        lambda _doc_id, _source, _root: {
            "model_path": str(tmp_path / "m.json"),
            "pdf_path": str(tmp_path / "p.pdf"),
        },
    )
    monkeypatch.setattr(worker_jobs, "load_document_model", lambda _p: object())
    monkeypatch.setattr(worker_jobs, "persist_document_model", lambda _m, _p: None)
    monkeypatch.setattr(worker_jobs, "update_document_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        worker_jobs,
        "update_job_status",
        lambda job_id, status, error_message=None: states.append((job_id, status, error_message)),
    )

    worker_jobs.stub_render_job("job-1")

    assert states[0][1] == "running"
    assert states[-1][1] == "succeeded"


def test_job_status_transition_failed_stores_error(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    _create_sample_image(source)
    states: list[tuple[str, str, str | None]] = []

    monkeypatch.setattr(worker_jobs, "init_database", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(worker_jobs, "fetch_job", lambda _job_id: {"document_id": "doc-2"})
    monkeypatch.setattr(worker_jobs, "fetch_document_source_path", lambda _doc_id: str(source))
    monkeypatch.setattr(worker_jobs, "process_stub_image", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(worker_jobs, "update_document_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        worker_jobs,
        "update_job_status",
        lambda job_id, status, error_message=None: states.append((job_id, status, error_message)),
    )

    try:
        worker_jobs.stub_render_job("job-2")
    except RuntimeError:
        pass

    assert states[0][1] == "running"
    assert states[-1][1] == "failed"
    assert "boom" in (states[-1][2] or "")


def test_worker_job_handler_runs_stub_pipeline(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    _create_sample_image(source)
    artifact_root = tmp_path / "artifacts"

    monkeypatch.setattr(worker_jobs, "init_database", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(worker_jobs, "fetch_job", lambda _job_id: {"document_id": "doc-3"})
    monkeypatch.setattr(worker_jobs, "fetch_document_source_path", lambda _doc_id: str(source))
    monkeypatch.setattr(
        worker_jobs,
        "settings",
        SimpleNamespace(database_url="postgresql://unused", artifact_root=artifact_root),
    )

    seen: dict[str, str] = {}

    def _persist(_model, model_path: str) -> None:
        seen["model_path"] = model_path

    def _update_doc(_doc_id: str, _status: str, output_pdf_path=None, model_path=None):
        if output_pdf_path:
            seen["pdf_path"] = output_pdf_path
        if model_path:
            seen["model_path"] = model_path

    monkeypatch.setattr(worker_jobs, "persist_document_model", _persist)
    monkeypatch.setattr(worker_jobs, "update_document_status", _update_doc)
    monkeypatch.setattr(worker_jobs, "update_job_status", lambda *_args, **_kwargs: None)

    worker_jobs.stub_render_job("job-3")

    assert Path(seen["model_path"]).exists()
    assert Path(seen["pdf_path"]).exists()
