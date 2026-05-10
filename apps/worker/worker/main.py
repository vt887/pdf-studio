from __future__ import annotations

import argparse
from pathlib import Path

from redis import Redis
from rq import Connection, Worker

from app.db import init_database
from app.queue import redis_queue_name
from app.settings import settings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="pdf-studio worker")
    parser.add_argument("--queue", default="default", help="RQ queue name")
    parser.add_argument("--burst", action="store_true", help="Run in burst mode")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    settings.artifact_root.mkdir(parents=True, exist_ok=True)
    init_database(settings.database_url)

    redis = Redis.from_url(settings.redis_url)
    queue_name = redis_queue_name(args.queue, settings.redis_key_prefix)
    with Connection(redis):
        worker = Worker([queue_name])
        worker.work(burst=args.burst)


if __name__ == "__main__":
    main()
