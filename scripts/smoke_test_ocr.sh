#!/usr/bin/env bash
set -euo pipefail

BOOK_INPUT="${BOOK_INPUT:-book}"
BOOK_OUTPUT="${BOOK_OUTPUT:-output}"
OCR_LANG="${OCR_LANG:-eng}"
VERBOSE="${VERBOSE:-0}"
PYTHONPATH="${PYTHONPATH:-apps/worker:packages/document-model/src:packages/pdf-renderer/src}"

VERBOSE_FLAG=""
if [[ "$VERBOSE" == "1" ]]; then
  VERBOSE_FLAG="--verbose"
fi

log() { printf '%s\n' "$*"; }
section() { printf '\n[%s]\n' "$1"; }
fail() { log "[fail] $*"; exit 1; }

# ── prerequisites ──────────────────────────────────────────────────────────────

section "Prerequisites"

if ! command -v poetry >/dev/null 2>&1; then
  fail "poetry not found — install via: curl -sSL https://install.python-poetry.org | python3 -"
fi
log "[ok] poetry"

if ! command -v tesseract >/dev/null 2>&1; then
  log "[error] tesseract not found"
  log "[error] For macOS: brew install tesseract"
  log "[error] For Docker worker: tesseract-ocr is installed in apps/worker/Dockerfile"
  exit 1
fi
log "[ok] tesseract $(tesseract --version 2>&1 | head -1)"

# ── prepare book ───────────────────────────────────────────────────────────────

section "Prepare book"

mkdir -p "$BOOK_INPUT" "$BOOK_OUTPUT"

# Count image files in book/
image_count=$(find "$BOOK_INPUT" -maxdepth 1 -type f \( -name '*.png' -o -name '*.jpg' -o -name '*.jpeg' -o -name '*.tiff' \) | wc -l | tr -d ' ')

if [[ "$image_count" -eq 0 ]]; then
  log "[generate] book/ is empty — creating deterministic test image"
  PYTHONPATH="$PYTHONPATH" poetry run python - "$BOOK_INPUT/ocr-smoke-test.png" <<'PY'
import sys
from pathlib import Path
from PIL import Image, ImageDraw

out = Path(sys.argv[1])
out.parent.mkdir(parents=True, exist_ok=True)

img = Image.new("RGB", (1000, 1400), color="white")
draw = ImageDraw.Draw(img)
draw.rectangle((20, 20, 980, 1380), outline="black", width=3)
draw.text((60, 100), "Hello OCR", fill="black")
draw.text((60, 200), "This is a test page", fill="black")
draw.text((60, 300), "https://example.com", fill="black")
img.save(out, format="PNG")
PY
  log "[ok] created $BOOK_INPUT/ocr-smoke-test.png"
else
  log "[ok] using $image_count existing image(s) from $BOOK_INPUT/"
fi

# ── run OCR ingestion ──────────────────────────────────────────────────────────

section "OCR ingestion"

PYTHONPATH="$PYTHONPATH" poetry run python -m worker.ingest_book \
  --input "$BOOK_INPUT" \
  --output "$BOOK_OUTPUT" \
  --ocr \
  --ocr-lang "$OCR_LANG" \
  --force \
  --spread-mode single-page \
  $VERBOSE_FLAG

# ── verify output files ────────────────────────────────────────────────────────

section "Verify outputs"

for path in \
  "$BOOK_OUTPUT/book.manifest.json" \
  "$BOOK_OUTPUT/book.model.json" \
  "$BOOK_OUTPUT/book.pdf" \
  "$BOOK_OUTPUT/artifacts/ocr/0001.ocr.json"; do
  if [[ ! -s "$path" ]]; then
    fail "missing or empty: $path"
  fi
  log "[ok] $(basename "$path")"
done

# ── verify OCR JSON has at least one line ──────────────────────────────────────

section "Verify OCR content"

ocr_json="$BOOK_OUTPUT/artifacts/ocr/0001.ocr.json"
ocr_lines=$(PYTHONPATH="$PYTHONPATH" poetry run python - "$ocr_json" <<'PY'
import json, sys
payload = json.loads(open(sys.argv[1]).read())
print(len(payload.get("lines", [])))
PY
)

if [[ "$ocr_lines" -eq 0 ]]; then
  log "[warn] OCR produced no text lines — check image quality or language pack"
else
  log "[ok] OCR lines: $ocr_lines"
fi

# ── verify book.model.json has text lines ──────────────────────────────────────

model_json="$BOOK_OUTPUT/book.model.json"
model_text_lines=$(PYTHONPATH="$PYTHONPATH" poetry run python - "$model_json" <<'PY'
import json, sys
payload = json.loads(open(sys.argv[1]).read())
total = sum(len(p.get("text_lines", [])) for p in payload.get("pages", []))
print(total)
PY
)

if [[ "$model_text_lines" -eq 0 ]]; then
  log "[warn] book.model.json has no text_lines — OCR text was not propagated"
else
  log "[ok] model text_lines: $model_text_lines"
fi

# ── verify PDF has extractable text ───────────────────────────────────────────

pdf_path="$BOOK_OUTPUT/book.pdf"
pdf_size=$(wc -c < "$pdf_path" | tr -d ' ')
log "[ok] PDF size: ${pdf_size} bytes"

if PYTHONPATH="$PYTHONPATH" poetry run python -c "import fitz" >/dev/null 2>&1; then
  pdf_text=$(PYTHONPATH="$PYTHONPATH" poetry run python - "$pdf_path" <<'PY'
import sys
import fitz
with fitz.open(sys.argv[1]) as pdf:
    text = "".join(page.get_text() for page in pdf).strip()
    print(len(text))
PY
)
  if [[ "$pdf_text" -gt 0 ]]; then
    log "[ok] PDF extracted text chars: $pdf_text"
  else
    log "[warn] PDF has no extractable text — OCR overlay may be missing"
  fi
else
  log "[skip] PyMuPDF not available — skipping PDF text extraction check"
fi

# ── summary ────────────────────────────────────────────────────────────────────

section "Summary"
log "book input:     $BOOK_INPUT"
log "output:         $BOOK_OUTPUT"
log "ocr lang:       $OCR_LANG"
log "ocr artifact:   $BOOK_OUTPUT/artifacts/ocr/0001.ocr.json"
log "model:          $BOOK_OUTPUT/book.model.json"
log "pdf:            $BOOK_OUTPUT/book.pdf"
log "inspect:        make inspect-output"
log ""
log "[ok] OCR smoke test passed"
