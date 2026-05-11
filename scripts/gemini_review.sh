#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: scripts/gemini_review.sh <input-file> [review-instructions]" >&2
  exit 1
fi

if ! command -v gemini >/dev/null 2>&1; then
  echo "error: gemini CLI not found in PATH" >&2
  exit 1
fi

VERSION="$(gemini --version)"
echo "gemini version: $VERSION"

INPUT="$1"
INSTRUCTIONS="${2:-Review this file. Focus on missing tests, assumptions, edge cases, and unclear decisions.}"

if [[ ! -f "$INPUT" ]]; then
  echo "error: input file not found: $INPUT" >&2
  exit 1
fi

OUT_DIR="tmp/gemini-reviews"
mkdir -p "$OUT_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
BASE="$(basename "$INPUT")"
BASE="${BASE%.*}"
OUT_FILE="$OUT_DIR/${TS}-${BASE}-review.md"
MODEL="${GEMINI_MODEL:-}"

PROMPT_FILE="$(mktemp)"
trap 'rm -f "$PROMPT_FILE"' EXIT

cat > "$PROMPT_FILE" <<PROMPT
You are an external reviewer.
Provide review feedback only.
Do not claim files were modified.

Focus on:
- correctness risks;
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

if [[ -n "$MODEL" ]]; then
  OUTPUT="$(gemini -m "$MODEL" -p "$(cat "$PROMPT_FILE")" 2>&1 || true)"
else
  OUTPUT="$(gemini -p "$(cat "$PROMPT_FILE")" 2>&1 || true)"
fi

LOWER="$(printf '%s' "$OUTPUT" | tr '[:upper:]' '[:lower:]')"
if [[ -z "${OUTPUT//[[:space:]]/}" ]] || \
   [[ "$LOWER" == *"not logged in"* ]] || \
   [[ "$LOWER" == *"opening authentication page"* ]] || \
   [[ "$LOWER" == *"do you want to continue? [y/n]"* ]] || \
   [[ "$LOWER" == *"/auth"* ]]; then
  FAIL_FILE="$OUT_DIR/${TS}-${BASE}-failed.md"
  {
    echo "# failed"
    echo
    echo "status: failed"
    echo "reason: gemini output was empty or auth/login prompt"
  } > "$FAIL_FILE"
  echo "error: Gemini did not produce a valid review." >&2
  echo "failure artifact: $FAIL_FILE" >&2
  exit 1
fi

printf '%s\n' "$OUTPUT" > "$OUT_FILE"
if [[ ! -s "$OUT_FILE" ]]; then
  FAIL_FILE="$OUT_DIR/${TS}-${BASE}-failed.md"
  {
    echo "# failed"
    echo
    echo "status: failed"
    echo "reason: gemini output file is empty"
  } > "$FAIL_FILE"
  echo "error: Gemini produced empty review output." >&2
  echo "failure artifact: $FAIL_FILE" >&2
  exit 1
fi

echo "review written: $OUT_FILE"
echo "status: success (meaningful review content)"
echo "warning: advisory output only; Codex or a human must review before applying changes."
