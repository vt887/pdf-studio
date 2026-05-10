from __future__ import annotations

from redis import Redis
from rq import Queue


def get_redis(redis_url: str) -> Redis:
    return Redis.from_url(redis_url)


def redis_queue_name(name: str, prefix: str = "pdf-studio") -> str:
    return f"{prefix}:{name}" if prefix else name


def get_queue(redis_url: str, name: str = "default", prefix: str = "pdf-studio") -> Queue:
    return Queue(name=redis_queue_name(name, prefix), connection=get_redis(redis_url))


def enqueue_stub_render(
    redis_url: str,
    job_id: str,
    queue_name: str = "default",
    prefix: str = "pdf-studio",
) -> str:
    queue = get_queue(redis_url, queue_name, prefix)
    rq_job = queue.enqueue("worker.jobs.stub_render_job", job_id)
    return rq_job.id
