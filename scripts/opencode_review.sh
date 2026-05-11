#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: scripts/opencode_review.sh <input-file> [review-instructions]" >&2
  exit 1
fi

if ! command -v opencode >/dev/null 2>&1; then
  echo "error: opencode CLI not found in PATH" >&2
  exit 1
fi

VERSION="$(HOME=/private/tmp opencode -v 2>/dev/null || true)"
if [[ -n "$VERSION" ]]; then
  echo "opencode version: $VERSION"
fi

INPUT="$1"
INSTRUCTIONS="${2:-Review this file. Focus on OCR-path correctness, edge cases, missing tests, and unsafe assumptions.}"
if [[ ! -f "$INPUT" ]]; then
  echo "error: input file not found: $INPUT" >&2
  exit 1
fi

OUT_DIR="tmp/opencode-reviews"
mkdir -p "$OUT_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
BASE="$(basename "$INPUT")"
BASE="${BASE%.*}"
OUT_FILE="$OUT_DIR/${TS}-${BASE}-review.md"
TMP_OUT="$(mktemp)"

MODEL="${OPENCODE_MODEL:-}"
PROMPT_FILE="$(mktemp)"
trap 'rm -f "$PROMPT_FILE" "$TMP_OUT"' EXIT

cat > "$PROMPT_FILE" <<PROMPT
You are an external reviewer.
Provide review feedback only.
Do not claim files were modified.

Focus on:
- OCR pipeline correctness;
- missing tests;
- edge cases;
- hidden assumptions;
- unclear acceptance criteria.

Review instructions:
$INSTRUCTIONS

File path:
$INPUT

File content:
PROMPT
cat "$INPUT" >> "$PROMPT_FILE"

set +e
if [[ -n "$MODEL" ]]; then
  HOME=/private/tmp opencode run --model "$MODEL" "$(cat "$PROMPT_FILE")" > "$TMP_OUT" 2>"$OUT_FILE.stderr"
  RC=$?
else
  HOME=/private/tmp opencode run "$(cat "$PROMPT_FILE")" > "$TMP_OUT" 2>"$OUT_FILE.stderr"
  RC=$?
fi
set -e
if [[ $RC -ne 0 ]]; then
  echo "error: OpenCode review failed with exit code $RC" >&2
  cat "$OUT_FILE.stderr" >&2 || true
  echo "note: OpenCode model configuration is independent from Ollama." >&2
  FAIL_FILE="$OUT_DIR/${TS}-${BASE}-failed.md"
  {
    echo "# failed"
    echo
    echo "status: failed"
    echo "reason: opencode command returned non-zero exit code"
  } > "$FAIL_FILE"
  echo "failure artifact: $FAIL_FILE" >&2
  exit $RC
fi
if [[ ! -s "$TMP_OUT" ]]; then
  echo "error: OpenCode returned empty review output" >&2
  echo "note: OpenCode model configuration is independent from Ollama." >&2
  FAIL_FILE="$OUT_DIR/${TS}-${BASE}-failed.md"
  {
    echo "# failed"
    echo
    echo "status: failed"
    echo "reason: opencode output is empty"
  } > "$FAIL_FILE"
  echo "failure artifact: $FAIL_FILE" >&2
  exit 1
fi
rm -f "$OUT_FILE.stderr"
mv "$TMP_OUT" "$OUT_FILE"
echo "review written: $OUT_FILE"
echo "status: success (meaningful review content)"
echo "warning: advisory output only; Codex or a human must review before applying changes."
