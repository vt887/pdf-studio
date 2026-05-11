#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: scripts/ollama_doc_draft.sh <markdown-file-or-text-file>" >&2
  exit 1
fi

INPUT="$1"
if [[ ! -f "$INPUT" ]]; then
  echo "error: input file not found: $INPUT" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "[ollama:error] curl is required" >&2
  exit 1
fi

HOST="${OLLAMA_HOST:-http://10.0.1.2:11434}"
MODEL="${OLLAMA_MODEL:-}"
OUT_DIR="tmp/ollama-drafts"
mkdir -p "$OUT_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
OUT_FILE="$OUT_DIR/${TS}-draft.md"
TAGS_FILE="$(mktemp)"
PAYLOAD_FILE="$(mktemp)"
RESP_FILE="$(mktemp)"
trap 'rm -f "$TAGS_FILE" "$PAYLOAD_FILE" "$RESP_FILE"' EXIT

PROMPT_HEADER="You are helping with a documentation draft. Produce a suggested Markdown draft only. Do not claim final authority."

if ! curl -fsS "$HOST/api/tags" > "$TAGS_FILE"; then
  echo "[ollama:error] remote Ollama is not reachable: $HOST" >&2
  echo "[ollama:error] verify from this host: curl $HOST/api/tags" >&2
  exit 1
fi

if [[ -z "$MODEL" ]]; then
  MODEL="$(python3 - <<'PY' "$TAGS_FILE"
import json,sys
data=json.load(open(sys.argv[1], encoding="utf-8"))
models=data.get("models", [])
print(models[0]["name"] if models else "")
PY
)"
  if [[ -z "$MODEL" ]]; then
    echo "[ollama:error] no models available on remote host: $HOST" >&2
    exit 1
  fi
fi

python3 - <<'PY' "$TAGS_FILE" "$MODEL" "$HOST"
import json,sys
data=json.load(open(sys.argv[1], encoding="utf-8"))
name=sys.argv[2]
models={m.get("name") for m in data.get("models", [])}
if name not in models:
    print(f"[ollama:error] model not found on remote host: {name}", file=sys.stderr)
    print(f"[ollama:error] check available models via: curl {sys.argv[3]}/api/tags", file=sys.stderr)
    raise SystemExit(1)
PY

PROMPT_BODY="$(cat <<PROMPT
$PROMPT_HEADER

Source file: $INPUT

$(cat "$INPUT")
PROMPT
)"

python3 - <<'PY' "$PAYLOAD_FILE" "$MODEL" "$PROMPT_BODY"
import json,sys
payload={"model":sys.argv[2], "prompt":sys.argv[3], "stream":False}
open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(payload))
PY

curl -fsS "$HOST/api/generate" -H "Content-Type: application/json" --data-binary @"$PAYLOAD_FILE" > "$RESP_FILE"
TMP_OUT="$(mktemp)"
python3 - <<'PY' "$RESP_FILE" "$TMP_OUT"
import json,sys
data=json.load(open(sys.argv[1], encoding="utf-8"))
open(sys.argv[2], "w", encoding="utf-8").write(data.get("response",""))
PY
LOWER="$(tr '[:upper:]' '[:lower:]' < "$TMP_OUT")"
if [[ ! -s "$TMP_OUT" ]] || [[ "$LOWER" == *"not logged in"* ]] || [[ "$LOWER" == *"opening authentication page"* ]]; then
  FAIL_FILE="$OUT_DIR/${TS}-failed.md"
  {
    echo "# failed"
    echo
    echo "status: failed"
    echo "reason: ollama draft output is empty or invalid"
  } > "$FAIL_FILE"
  rm -f "$TMP_OUT"
  echo "[ollama:error] draft generation failed or returned invalid content" >&2
  echo "failure artifact: $FAIL_FILE" >&2
  exit 1
fi
mv "$TMP_OUT" "$OUT_FILE"

echo "draft written: $OUT_FILE"
echo "remote host: $HOST"
echo "model: $MODEL"
echo "status: success (meaningful draft content)"
echo "warning: advisory draft only; review manually before applying to source files."
