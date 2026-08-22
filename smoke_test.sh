#!/usr/bin/env bash
# Quick end-to-end check against a running router: submit -> poll -> download.
#
# Usage:
#   ROUTER_URL=http://localhost:8080 ROUTER_KEY=test-key-123 \
#   MODEL=bytedance/seedance-2.5 PROMPT="a cat surfing, cinematic" \
#   RESOLUTION=720p DURATION=25 ./smoke_test.sh
#
# Defaults are deliberately the cheapest real generation (2.0 mini at 480p/4s):
# this test is about proving the round-trip works, not about output quality.
# Leaving RESOLUTION/DURATION unset would inherit the model's defaults, which on
# Seedance 2.5 means duration=-1 — the model picks any length up to 30s.
#
# Duration is per-model: 2.5 accepts 4-30s, the 2.0 series 4-15s, 1.5 pro 4-12s.
# Ask for more than the model allows and BytePlus returns a precise 400.
set -euo pipefail

ROUTER_URL="${ROUTER_URL:-http://localhost:8080}"
ROUTER_KEY="${ROUTER_KEY:-test-key-123}"
MODEL="${MODEL:-bytedance/seedance-2.0-mini}"
PROMPT="${PROMPT:-a cat surfing a big wave, cinematic, golden hour}"
RESOLUTION="${RESOLUTION:-480p}"
DURATION="${DURATION:-4}"
OUT_DIR="${OUT_DIR:-./smoke-output}"
AUTH="Authorization: Bearer ${ROUTER_KEY}"

echo "1) health"
curl -sf "${ROUTER_URL}/healthz" | jq .

echo "2) submit  (${MODEL}, ${RESOLUTION}, ${DURATION}s)"
echo "   prompt: ${PROMPT}"
JOB=$(jq -n --arg m "$MODEL" --arg p "$PROMPT" --arg r "$RESOLUTION" --argjson d "$DURATION" \
        '{model:$m, prompt:$p, resolution:$r, duration:$d}' \
      | curl -sf -X POST "${ROUTER_URL}/api/v1/videos" -H "$AUTH" -H "Content-Type: application/json" -d @-)
echo "$JOB" | jq .
ID=$(echo "$JOB" | jq -r .id)

echo "3) poll until terminal"
START=$(date +%s)
while true; do
  S=$(curl -sf "${ROUTER_URL}/api/v1/videos/${ID}" -H "$AUTH")
  STATUS=$(echo "$S" | jq -r .status)
  echo "   status=${STATUS}  (t+$(( $(date +%s) - START ))s)"
  case "$STATUS" in
    completed) echo "$S" | jq 'del(.unsigned_urls, .output)'; break ;;
    failed|cancelled|expired) echo "$S" | jq .; echo "terminal failure"; exit 1 ;;
    *) sleep 5 ;;
  esac
done

echo "4) download through the router (no upstream key reaches the CDN)"
mkdir -p "$OUT_DIR"
FILE="${OUT_DIR}/$(date +%Y%m%d-%H%M%S).mp4"
curl -sf -o "$FILE" -w '   HTTP %{http_code}  %{size_download} bytes  %{content_type}\n' \
  "${ROUTER_URL}/api/v1/videos/${ID}/content" -H "$AUTH"
echo "done -> ${FILE}"
