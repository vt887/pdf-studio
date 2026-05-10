from __future__ import annotations

from types import SimpleNamespace

from app import queue as queue_mod


def test_redis_queue_name_applies_prefix() -> None:
    assert queue_mod.redis_queue_name("default", "pdf-studio") == "pdf-studio:default"
    assert queue_mod.redis_queue_name("default", "") == "default"


def test_enqueue_stub_render_uses_prefixed_queue(monkeypatch) -> None:
    seen: dict[str, object] = {}

    class FakeQueue:
        def __init__(self, name, connection):
            seen["name"] = name
            seen["connection"] = connection

        def enqueue(self, target, job_id):
            seen["target"] = target
            seen["job_id"] = job_id
            return SimpleNamespace(id="rq-123")

    monkeypatch.setattr(queue_mod, "Queue", FakeQueue)
    monkeypatch.setattr(queue_mod, "get_redis", lambda url: SimpleNamespace(url=url))

    rq_job_id = queue_mod.enqueue_stub_render("redis://example", "job-1", queue_name="default", prefix="pdf-studio")

    assert rq_job_id == "rq-123"
    assert seen["name"] == "pdf-studio:default"
    assert seen["target"] == "worker.jobs.stub_render_job"
    assert seen["job_id"] == "job-1"
