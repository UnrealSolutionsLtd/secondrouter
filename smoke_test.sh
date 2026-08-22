#!/usr/bin/env bash
# Quick end-to-end check against a running router.
# Usage:
#   ROUTER_URL=http://localhost:8080 ROUTER_KEY=test-key-123 \
#   MODEL=bytedance/seedance-2.5 PROMPT="a cat surfing, cinematic" ./smoke_test.sh
#
# Defaults are deliberately the cheapest real generation (2.0 mini at 480p/4s):
# this test is about proving the round-trip works, not about output quality.
# Leaving RESOLUTION/DURATION unset would inherit the model's defaults, which on
# Seedance 2.5 means duration=-1 — the model picks any length up to 30s.
set -euo pipefail

ROUTER_URL="${ROUTER_URL:-http://localhost:8080}"
ROUTER_KEY="${ROUTER_KEY:-test-key-123}"
MODEL="${MODEL:-bytedance/seedance-2.0-mini}"
PROMPT="${PROMPT:-a cat surfing a big wave, cinematic, golden hour}"
RESOLUTION="${RESOLUTION:-480p}"
DURATION="${DURATION:-4}"
AUTH="Authorization: Bearer ${ROUTER_KEY}"

echo "1) health"
curl -sf "${ROUTER_URL}/healthz" | jq .

echo "2) submit  (${MODEL}, ${RESOLUTION}, ${DURATION}s)"
JOB=$(curl -sf -X POST "${ROUTER_URL}/api/v1/videos" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"model\":\"${MODEL}\",\"prompt\":\"${PROMPT}\",\"resolution\":\"${RESOLUTION}\",\"duration\":${DURATION}}")
echo "$JOB" | jq .
ID=$(echo "$JOB" | jq -r .id)

echo "3) poll until terminal"
while true; do
  S=$(curl -sf "${ROUTER_URL}/api/v1/videos/${ID}" -H "$AUTH")
  STATUS=$(echo "$S" | jq -r .status)
  echo "   status=${STATUS}"
  case "$STATUS" in
    completed) echo "$S" | jq .; break ;;
    failed|cancelled|expired) echo "$S" | jq .; echo "terminal failure"; exit 1 ;;
    *) sleep 5 ;;
  esac
done

echo "4) download through the router (no upstream key reaches the CDN)"
curl -sf -o /tmp/video-router-smoke.mp4 -w '   HTTP %{http_code}  %{size_download} bytes  %{content_type}\n' \
  "${ROUTER_URL}/api/v1/videos/${ID}/content" -H "$AUTH"
echo "done -> /tmp/video-router-smoke.mp4"
