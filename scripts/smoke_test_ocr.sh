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
  log "[generate] book/ is empty — creating deterministic mixed spread test images"
  PYTHONPATH="$PYTHONPATH" poetry run python - "$BOOK_INPUT" <<'PY'
import sys
from pathlib import Path
from PIL import Image, ImageDraw

book = Path(sys.argv[1])
book.mkdir(parents=True, exist_ok=True)

# single-page sample
single = Image.new("RGB", (1000, 1400), color="white")
draw = ImageDraw.Draw(single)
draw.rectangle((20, 20, 980, 1380), outline="black", width=3)
draw.text((60, 100), "Single page one", fill="black")
draw.text((60, 180), "Hello OCR", fill="black")
single.save(book / "001-single.png", format="PNG")

# two-page spread sample
spread = Image.new("RGB", (2200, 1400), color=(30, 30, 30))
left = Image.new("RGB", (980, 1300), color="white")
right = Image.new("RGB", (980, 1300), color="white")
draw_left = ImageDraw.Draw(left)
draw_right = ImageDraw.Draw(right)
draw_left.text((50, 120), "Left page text", fill="black")
draw_left.text((50, 200), "Spread sample A", fill="black")
draw_right.text((50, 120), "Right page text", fill="black")
draw_right.text((50, 200), "Spread sample B", fill="black")
spread.paste(left, (80, 50))
spread.paste(right, (1140, 50))
spread.save(book / "002-spread.png", format="PNG")
PY
  log "[ok] created mixed sample images in $BOOK_INPUT"
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
  --spread-mode auto-mixed \
  $VERBOSE_FLAG

# ── verify output files ────────────────────────────────────────────────────────

section "Verify outputs"

for path in \
  "$BOOK_OUTPUT/book.manifest.json" \
  "$BOOK_OUTPUT/book.model.json" \
  "$BOOK_OUTPUT/book.pdf"; do
  if [[ ! -s "$path" ]]; then
    fail "missing or empty: $path"
  fi
  log "[ok] $(basename "$path")"
done

# ── verify OCR JSON has at least one line ──────────────────────────────────────

section "Verify OCR content"

counts_json=$(PYTHONPATH="$PYTHONPATH" poetry run python - "$BOOK_OUTPUT/book.manifest.json" "$BOOK_OUTPUT/artifacts/ocr" <<'PY'
import json, sys
from pathlib import Path
manifest = json.loads(Path(sys.argv[1]).read_text())
derived = len(manifest.get("pages", []))
ocr_count = len(list(Path(sys.argv[2]).glob("*.ocr.json")))
print(json.dumps({"derived_pages": derived, "ocr_artifacts": ocr_count}))
PY
)
derived_pages=$(PYTHONPATH="$PYTHONPATH" poetry run python - "$counts_json" <<'PY'
import json, sys
print(json.loads(sys.argv[1])["derived_pages"])
PY
)
ocr_artifacts=$(PYTHONPATH="$PYTHONPATH" poetry run python - "$counts_json" <<'PY'
import json, sys
print(json.loads(sys.argv[1])["ocr_artifacts"])
PY
)
if [[ "$derived_pages" -ne "$ocr_artifacts" ]]; then
  fail "ocr artifacts count ($ocr_artifacts) does not match derived pages count ($derived_pages)"
fi
log "[ok] derived pages: $derived_pages"
log "[ok] ocr artifacts: $ocr_artifacts"

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
  pdf_stats=$(PYTHONPATH="$PYTHONPATH" poetry run python - "$pdf_path" <<'PY'
import sys
import fitz
with fitz.open(sys.argv[1]) as pdf:
    text = "".join(page.get_text() for page in pdf).strip()
    images = sum(len(page.get_images()) for page in pdf)
    print(f"{len(text)}|{pdf.page_count}|{images}")
PY
)
  pdf_text="${pdf_stats%%|*}"
  remainder="${pdf_stats#*|}"
  pdf_pages="${remainder%%|*}"
  pdf_images="${pdf_stats##*|}"
  if [[ "$pdf_text" -gt 0 ]]; then
    log "[ok] PDF extracted text chars: $pdf_text"
  else
    log "[warn] PDF has no extractable text — OCR overlay may be missing"
  fi
  if [[ "$pdf_images" -eq 0 ]]; then
    log "[ok] PDF has no embedded page images"
  else
    fail "PDF contains embedded images: $pdf_images"
  fi
  if [[ "$pdf_pages" -eq "$derived_pages" ]]; then
    log "[ok] PDF pages match derived pages: $pdf_pages"
  else
    fail "PDF page count ($pdf_pages) does not match derived pages count ($derived_pages)"
  fi
else
  log "[skip] PyMuPDF not available — skipping PDF text extraction check"
fi

# ── summary ────────────────────────────────────────────────────────────────────

section "Summary"
log "book input:     $BOOK_INPUT"
log "output:         $BOOK_OUTPUT"
log "ocr lang:       $OCR_LANG"
log "ocr artifacts:  $BOOK_OUTPUT/artifacts/ocr/*.ocr.json"
log "model:          $BOOK_OUTPUT/book.model.json"
log "pdf:            $BOOK_OUTPUT/book.pdf"
log "inspect:        make inspect-output"
log ""
log "[ok] OCR smoke test passed"
