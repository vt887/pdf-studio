from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
API_SRC = ROOT / "apps" / "api"
WORKER_SRC = ROOT / "apps" / "worker"
DOCUMENT_MODEL_SRC = ROOT / "packages" / "document-model" / "src"
PDF_RENDERER_SRC = ROOT / "packages" / "pdf-renderer" / "src"

for path in (API_SRC, WORKER_SRC, DOCUMENT_MODEL_SRC, PDF_RENDERER_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.get_closest_marker("requires_tesseract") and shutil.which("tesseract") is None:
            item.add_marker(pytest.mark.skip(reason="tesseract binary not available on this host"))
