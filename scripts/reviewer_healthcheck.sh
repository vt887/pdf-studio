#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_INPUT="$(mktemp)"
trap 'rm -f "$TMP_INPUT"' EXIT
cat > "$TMP_INPUT" <<'MD'
# Reviewer Healthcheck Input

Please review this tiny plan for missing assumptions and test gaps.
MD

status_line() {
  echo "[reviewer-healthcheck] $1: $2"
}

log_line() {
  echo "[reviewer-healthcheck] $1"
}

run_gemini() {
  local log_file="/tmp/gemini-health.log"
  log_line "Gemini: checking CLI availability"
  if ! command -v gemini >/dev/null 2>&1; then
    status_line "Gemini" "FAIL (cli not found)"
    return 1
  fi
  log_line "Gemini: running scripted review on temp markdown: $TMP_INPUT"
  log_line "Gemini: log file: $log_file"
  if bash "$ROOT_DIR/scripts/gemini_review.sh" "$TMP_INPUT" "Healthcheck review" >"$log_file" 2>&1; then
    status_line "Gemini" "PASS"
    tail -n 3 "$log_file" | sed 's/^/[reviewer-healthcheck] Gemini log: /'
    return 0
  fi
  reason="$(tail -n 4 "$log_file" | tr '\n' ' ')"
  status_line "Gemini" "FAIL ($reason)"
  return 1
}

run_claude() {
  local log_file="/tmp/claude-health.log"
  log_line "Claude: checking CLI availability"
  if ! command -v claude >/dev/null 2>&1; then
    status_line "Claude" "FAIL (cli not found)"
    return 1
  fi
  log_line "Claude: running scripted review on temp markdown: $TMP_INPUT"
  log_line "Claude: log file: $log_file"
  if bash "$ROOT_DIR/scripts/claude_review.sh" "$TMP_INPUT" "Healthcheck review" >"$log_file" 2>&1; then
    status_line "Claude" "PASS"
    tail -n 3 "$log_file" | sed 's/^/[reviewer-healthcheck] Claude log: /'
    return 0
  fi
  reason="$(tail -n 4 "$log_file" | tr '\n' ' ')"
  status_line "Claude" "FAIL ($reason)"
  return 1
}

run_opencode() {
  local log_file="/tmp/opencode-health.log"
  log_line "OpenCode: checking CLI availability"
  if ! command -v opencode >/dev/null 2>&1; then
    status_line "OpenCode" "FAIL (cli not found)"
    return 1
  fi
  log_line "OpenCode: running scripted review on temp markdown: $TMP_INPUT"
  log_line "OpenCode: log file: $log_file"
  if bash "$ROOT_DIR/scripts/opencode_review.sh" "$TMP_INPUT" "Healthcheck review" >"$log_file" 2>&1; then
    status_line "OpenCode" "PASS"
    tail -n 3 "$log_file" | sed 's/^/[reviewer-healthcheck] OpenCode log: /'
    return 0
  fi
  reason="$(tail -n 4 "$log_file" | tr '\n' ' ')"
  status_line "OpenCode" "MANUAL-FIRST ($reason)"
  return 0
}

run_ollama() {
  host="${OLLAMA_HOST:-http://10.0.1.2:11434}"
  log_line "Ollama: checking remote host $host"
  if ! command -v curl >/dev/null 2>&1; then
    status_line "Ollama" "SKIPPED (curl not found)"
    return 0
  fi
  if curl -fsS "$host/api/tags" >/dev/null 2>&1; then
    status_line "Ollama" "PASS"
    return 0
  fi
  status_line "Ollama" "FAIL (remote not reachable: $host)"
  return 1
}

echo "[reviewer-healthcheck] note: run this in normal shell outside Codex sandbox for representative results."
log_line "Temporary review input file: $TMP_INPUT"
run_gemini || true
run_claude || true
run_opencode || true
run_ollama || true
