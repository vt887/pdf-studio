#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: scripts/claude_review.sh <input-file> [review-instructions]" >&2
  exit 1
fi

if ! command -v claude >/dev/null 2>&1; then
  echo "error: claude CLI not found in PATH" >&2
  exit 1
fi

VERSION="$(claude --version 2>/dev/null || true)"
if [[ -n "$VERSION" ]]; then
  echo "claude version: $VERSION"
fi

INPUT="$1"
INSTRUCTIONS="${2:-Review this file. Focus on architecture risks, missing tests, edge cases, and unclear assumptions.}"

if [[ ! -f "$INPUT" ]]; then
  echo "error: input file not found: $INPUT" >&2
  exit 1
fi

OUT_DIR="tmp/claude-reviews"
mkdir -p "$OUT_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
BASE="$(basename "$INPUT")"
BASE="${BASE%.*}"
OUT_FILE="$OUT_DIR/${TS}-${BASE}-review.md"
MODEL="${CLAUDE_MODEL:-}"

PROMPT_FILE="$(mktemp)"
trap 'rm -f "$PROMPT_FILE"' EXIT

cat > "$PROMPT_FILE" <<PROMPT
You are an external reviewer.
Provide review feedback only.
Do not claim files were modified.

Focus on:
- architecture risks;
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
  OUTPUT="$(claude --print --model "$MODEL" "$(cat "$PROMPT_FILE")" 2>&1 || true)"
else
  OUTPUT="$(claude --print "$(cat "$PROMPT_FILE")" 2>&1 || true)"
fi

LOWER="$(printf '%s' "$OUTPUT" | tr '[:upper:]' '[:lower:]')"
if [[ -z "${OUTPUT//[[:space:]]/}" ]] || \
   [[ "$LOWER" == *"not logged in"* ]] || \
   [[ "$LOWER" == *"opening authentication page"* ]] || \
   [[ "$LOWER" == *"/login"* ]] || \
   [[ "$LOWER" == *"please run /login"* ]]; then
  FAIL_FILE="$OUT_DIR/${TS}-${BASE}-failed.md"
  {
    echo "# failed"
    echo
    echo "status: failed"
    echo "reason: claude output was empty or auth/login prompt"
  } > "$FAIL_FILE"
  echo "error: Claude did not produce a valid review." >&2
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
    echo "reason: claude output file is empty"
  } > "$FAIL_FILE"
  echo "error: Claude produced empty review output." >&2
  echo "failure artifact: $FAIL_FILE" >&2
  exit 1
fi

echo "review written: $OUT_FILE"
echo "status: success (meaningful review content)"
echo "warning: advisory output only; Codex or a human must review before applying changes."
