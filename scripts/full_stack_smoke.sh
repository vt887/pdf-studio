#!/usr/bin/env bash
set -euo pipefail

BOOK_INPUT="${BOOK_INPUT:-book}"
BOOK_OUTPUT="${BOOK_OUTPUT:-output}"
SPREAD_MODE="${SPREAD_MODE:-single-page}"
API_BASE="${API_BASE:-http://localhost:8000}"
UI_BASE="${UI_BASE:-http://localhost:3000}"
REDIS_URL="${REDIS_URL:-redis://10.0.1.2:6379/0}"
REDIS_KEY_PREFIX="${REDIS_KEY_PREFIX:-pdf-studio}"

log() {
  printf '%s\n' "$*"
}

section() {
  printf '\n[%s]\n' "$1"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "[error] missing required command: $1"
    exit 1
  fi
}

wait_for_http() {
  local url="$1"
  local label="$2"
  local attempts="${3:-60}"
  local sleep_s="${4:-2}"
  for _ in $(seq 1 "$attempts"); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      log "[ok] $label"
      return 0
    fi
    sleep "$sleep_s"
  done
  log "[error] timed out waiting for $label at $url"
  return 1
}

wait_for_container_exec() {
  local service="$1"
  local label="$2"
  local command="$3"
  local attempts="${4:-60}"
  local sleep_s="${5:-2}"
  for _ in $(seq 1 "$attempts"); do
    if docker compose exec -T "$service" sh -lc "$command" >/dev/null 2>&1; then
      log "[ok] $label"
      return 0
    fi
    sleep "$sleep_s"
  done
  log "[error] timed out waiting for $label"
  return 1
}

ensure_poetry_env() {
  if ! poetry run python - <<'PY' >/dev/null 2>&1
import fitz
from PIL import Image
PY
  then
    section "Poetry install"
    poetry install
  else
    log "[ok] Poetry environment already ready"
  fi
}

ensure_sample_book() {
  mkdir -p "$BOOK_INPUT" "$BOOK_OUTPUT"
  if find "$BOOK_INPUT" -maxdepth 1 -type f ! -name 'spread-overrides.json' | grep -q .; then
    log "[ok] existing input files found in $BOOK_INPUT"
    return 0
  fi

  section "Create synthetic smoke input"
  poetry run python - "$BOOK_INPUT" <<'PY'
from __future__ import annotations

from pathlib import Path
import sys

from PIL import Image, ImageDraw

book = Path(sys.argv[1])
book.mkdir(parents=True, exist_ok=True)

samples = [
    ("smoke-01.png", (1000, 1500), "single"),
    ("smoke-02.png", (2000, 1000), "two"),
    ("smoke-03.png", (2000, 1000), "two"),
]

for filename, size, label in samples:
    image = Image.new("RGB", size, color="white")
    draw = ImageDraw.Draw(image)
    width, height = size
    draw.rectangle((20, 20, width - 20, height - 20), outline="black", width=4)
    if label == "two":
      draw.line((width // 2, 0, width // 2, height), fill="black", width=8)
      draw.text((80, 100), "LEFT", fill="black")
      draw.text((width // 2 + 80, 100), "RIGHT", fill="black")
    else:
      draw.text((80, 100), "PAGE", fill="black")
    image.save(book / filename, format="PNG")
PY
  log "[ok] synthetic smoke input created"
}

run_compose_build() {
  section "Build Docker services"
  docker compose build postgres api worker review-ui
}

start_compose() {
  section "Start Docker services"
  docker compose up -d --remove-orphans postgres api worker review-ui
}

wait_for_services() {
  section "Wait for services"
  wait_for_container_exec postgres "Postgres readiness" "pg_isready -U postgres -d pdf_studio"
  wait_for_container_exec api "API /health" "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read()\""
  wait_for_container_exec review-ui "Review UI" "node -e \"const http=require('node:http'); const req=http.get('http://127.0.0.1:3000', (res) => { res.resume(); process.exit(res.statusCode >= 200 && res.statusCode < 500 ? 0 : 1); }); req.on('error', () => process.exit(1));\""
}

run_migrations() {
  section "Run migrations"
  make migrate
}

verify_worker_environment() {
  section "Verify shared services"
  docker compose exec -T api python - <<'PY'
from app.db import init_database
from app.settings import settings

init_database(settings.database_url)
from redis import Redis

Redis.from_url(settings.redis_url).ping()
print("database-ok")
PY

  docker compose exec -T worker python - <<'PY'
from redis import Redis
from app.db import init_database
from app.settings import settings

Redis.from_url(settings.redis_url).ping()
init_database(settings.database_url)
print("worker-ok")
PY

  if docker compose exec -T worker tesseract --version >/dev/null 2>&1; then
    log "[ok] tesseract available in worker container"
  else
    log "[warn] tesseract not found in worker container — OCR jobs will fail. Rebuild the worker image."
  fi
}

run_api_smoke() {
  section "API document/job smoke"
  docker compose exec -T api python - <<'PY'
from __future__ import annotations

from pathlib import Path
import time
import uuid

import httpx
from PIL import Image, ImageDraw

base_dir = Path("/tmp/pdf-studio-smoke")
base_dir.mkdir(parents=True, exist_ok=True)
sample = base_dir / f"api-smoke-{uuid.uuid4().hex}.png"
image = Image.new("RGB", (1000, 1400), color="white")
draw = ImageDraw.Draw(image)
draw.rectangle((20, 20, 980, 1380), outline="black", width=4)
draw.text((80, 100), "API SMOKE", fill="black")
image.save(sample, format="PNG")

with httpx.Client(base_url="http://127.0.0.1:8000", timeout=30.0) as client:
    response = client.post("/v1/documents", files={"file": (sample.name, sample.read_bytes(), "image/png")})
    response.raise_for_status()
    payload = response.json()
    document_id = payload["document_id"]
    job_id = payload["job_id"]
    print(f"[ok] uploaded document_id={document_id} job_id={job_id}")

    status = ""
    for _ in range(120):
        job = client.get(f"/v1/jobs/{job_id}")
        job.raise_for_status()
        job_payload = job.json()
        status = job_payload.get("status", "")
        print(f"[job] status={status}")
        if status == "succeeded":
            break
        if status == "failed":
            raise SystemExit(f"[error] job failed: {job_payload.get('error_message')}")
        time.sleep(1)

    if status != "succeeded":
        raise SystemExit("[error] timed out waiting for job success")

    document = client.get(f"/v1/documents/{document_id}")
    document.raise_for_status()
    model = client.get(f"/v1/documents/{document_id}/model")
    model.raise_for_status()
    pdf = client.get(f"/v1/documents/{document_id}/pdf")
    pdf.raise_for_status()

    smoke_dir = base_dir / "api-smoke"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    (smoke_dir / "document.json").write_text(document.text, encoding="utf-8")
    (smoke_dir / "model.json").write_bytes(model.content)
    (smoke_dir / "pdf.pdf").write_bytes(pdf.content)

    if not (smoke_dir / "model.json").is_file() or (smoke_dir / "model.json").stat().st_size == 0:
        raise SystemExit("[error] empty model artifact")
    if not (smoke_dir / "pdf.pdf").is_file() or (smoke_dir / "pdf.pdf").stat().st_size == 0:
        raise SystemExit("[error] empty PDF artifact")

    print("[ok] API returned model and PDF")
PY
}

run_local_ingestion() {
  section "Local book ingestion"
  export PYTHONPATH="apps/worker:packages/document-model/src:packages/pdf-renderer/src"
  poetry run python -m worker.ingest_book --input "$BOOK_INPUT" --output "$BOOK_OUTPUT" --force --spread-mode "$SPREAD_MODE"
}

verify_outputs() {
  section "Verify generated outputs"
  for path in \
    "$BOOK_OUTPUT/book.manifest.json" \
    "$BOOK_OUTPUT/book.model.json" \
    "$BOOK_OUTPUT/book.pdf" \
    "$BOOK_OUTPUT/book.summary.json"; do
    if [[ ! -s "$path" ]]; then
      log "[error] missing or empty output: $path"
      exit 1
    fi
    log "[ok] $(basename "$path")"
  done

  if ! find "$BOOK_OUTPUT/artifacts/pages" -maxdepth 1 -type f -name '*.normalized.png' | grep -q .; then
    log "[error] normalized page artifacts missing"
    exit 1
  fi
  log "[ok] normalized page artifacts present"

  local pdf_count=""
  if pdf_count="$(poetry run python - "$BOOK_OUTPUT/book.pdf" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

import fitz

pdf_path = Path(sys.argv[1])
with fitz.open(pdf_path) as pdf:
    print(pdf.page_count)
PY
)"; then
    log "[ok] PDF page count=${pdf_count}"
  else
    log "[warn] PyMuPDF not available for PDF page count verification"
  fi
}

run_tests() {
  section "Run test slices"
  poetry run pytest packages/document-model/tests packages/pdf-renderer/tests apps/worker/tests apps/api/tests -q
}

print_summary() {
  section "Summary"
  log "services started: postgres api worker review-ui"
  log "shared services: local Postgres + Redis at ${REDIS_URL}"
  log "redis key prefix: ${REDIS_KEY_PREFIX}"
  log "migrations: run via make migrate"
  log "ingestion spread mode: ${SPREAD_MODE}"
  log "outputs: ${BOOK_OUTPUT}/book.manifest.json ${BOOK_OUTPUT}/book.model.json ${BOOK_OUTPUT}/book.pdf ${BOOK_OUTPUT}/book.summary.json"
  log "inspect: make inspect-output"
}

main() {
  require_cmd docker
  require_cmd poetry

  section "Setup"
  ensure_poetry_env
  ensure_sample_book

  run_compose_build
  start_compose
  wait_for_services
  run_migrations
  verify_worker_environment
  run_api_smoke
  run_local_ingestion
  verify_outputs
  run_tests
  print_summary
}

main "$@"
