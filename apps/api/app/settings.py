from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    database_url: str = os.environ.get("DATABASE_URL", "postgresql+psycopg://postgres:postgres@postgres:5432/pdf_studio")
    redis_url: str = os.environ.get("REDIS_URL", "redis://10.0.1.2:6379/0")
    redis_key_prefix: str = os.environ.get("REDIS_KEY_PREFIX", "pdf-studio")
    artifact_root: Path = Path(os.environ.get("ARTIFACT_ROOT", "./artifacts"))
    app_env: str = os.environ.get("APP_ENV", "development")


settings = Settings()
