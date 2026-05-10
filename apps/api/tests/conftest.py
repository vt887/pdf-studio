from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
API_SRC = ROOT / "apps" / "api"
DOCUMENT_MODEL_SRC = ROOT / "packages" / "document-model" / "src"
PDF_RENDERER_SRC = ROOT / "packages" / "pdf-renderer" / "src"

for path in (API_SRC, DOCUMENT_MODEL_SRC, PDF_RENDERER_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
