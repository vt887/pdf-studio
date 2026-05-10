from __future__ import annotations

from types import SimpleNamespace

from worker import main as worker_main


def test_worker_main_uses_prefixed_queue(monkeypatch) -> None:
    seen: dict[str, object] = {}

    class FakeRedis:
        def __init__(self, url):
            seen["redis_url"] = url

        @classmethod
        def from_url(cls, url):
            return cls(url)

    class FakeConnection:
        def __init__(self, redis):
            seen["connection_redis"] = redis

        def __enter__(self):
            seen["connection_entered"] = True
            return self

        def __exit__(self, exc_type, exc, tb):
            seen["connection_exited"] = True
            return False

    class FakeWorker:
        def __init__(self, queues):
            seen["queues"] = queues

        def work(self, burst=False):
            seen["burst"] = burst

    monkeypatch.setattr(worker_main, "Redis", FakeRedis)
    monkeypatch.setattr(worker_main, "Connection", FakeConnection)
    monkeypatch.setattr(worker_main, "Worker", FakeWorker)
    monkeypatch.setattr(worker_main, "init_database", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        worker_main,
        "settings",
        SimpleNamespace(
            artifact_root=SimpleNamespace(mkdir=lambda *args, **kwargs: None),
            database_url="postgresql://example",
            redis_url="redis://example",
            redis_key_prefix="pdf-studio",
        ),
    )
    monkeypatch.setattr(worker_main.argparse.ArgumentParser, "parse_args", lambda self: SimpleNamespace(queue="default", burst=True))

    worker_main.main()

    assert seen["queues"] == ["pdf-studio:default"]
    assert seen["burst"] is True
