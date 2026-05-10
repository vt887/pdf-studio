from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PDF_RENDERER_SRC = ROOT / "packages" / "pdf-renderer" / "src"
DOCUMENT_MODEL_SRC = ROOT / "packages" / "document-model" / "src"

for path in (PDF_RENDERER_SRC, DOCUMENT_MODEL_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
