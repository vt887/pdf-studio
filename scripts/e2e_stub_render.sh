#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <sample-input-path>"
  exit 1
fi

SAMPLE="$1"
API_BASE="${API_BASE:-http://localhost:8000}"
OUT_DIR="${OUT_DIR:-/tmp/pdf-studio-e2e}"
mkdir -p "$OUT_DIR"

echo "[1/5] Run migrations"
docker compose run --rm api alembic -c /app/apps/api/alembic.ini upgrade head

echo "[2/5] Upload sample image"
UPLOAD_JSON="$OUT_DIR/upload.json"
curl -sS -X POST -F "file=@${SAMPLE}" "${API_BASE}/v1/documents" > "$UPLOAD_JSON"

read -r DOCUMENT_ID JOB_ID < <(python - "$UPLOAD_JSON" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
print(p["document_id"], p["job_id"])
PY
)

echo "document_id=${DOCUMENT_ID}"
echo "job_id=${JOB_ID}"

echo "[3/5] Poll job"
for _ in $(seq 1 120); do
  JOB_JSON="$OUT_DIR/job.json"
  curl -sS "${API_BASE}/v1/jobs/${JOB_ID}" > "$JOB_JSON"
  STATUS=$(python - "$JOB_JSON" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
print(p.get("status",""))
PY
)
  echo "status=${STATUS}"
  if [[ "$STATUS" == "succeeded" ]]; then
    break
  fi
  if [[ "$STATUS" == "failed" ]]; then
    python - "$JOB_JSON" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
print("Job failed:", p.get("error_message"))
PY
    exit 2
  fi
  sleep 1
done

if [[ "${STATUS:-}" != "succeeded" ]]; then
  echo "Timed out waiting for job success"
  exit 3
fi

echo "[4/5] Download model and PDF"
MODEL_FILE="$OUT_DIR/${DOCUMENT_ID}.model.json"
PDF_FILE="$OUT_DIR/${DOCUMENT_ID}.pdf"
curl -sS "${API_BASE}/v1/documents/${DOCUMENT_ID}/model" > "$MODEL_FILE"
curl -sS "${API_BASE}/v1/documents/${DOCUMENT_ID}/pdf" > "$PDF_FILE"

echo "[5/5] Validate artifacts"
test -s "$MODEL_FILE"
test -s "$PDF_FILE"
echo "OK: model and PDF are non-empty"
